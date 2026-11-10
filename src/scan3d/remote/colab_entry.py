import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
import hashlib
import glob
import shlex
from collections import deque

JOB = "/content/job.json"
RESULT = "/content/result.json"
LOG = "/content/dense.log"
MM = "/content/bin/micromamba"

PARSER_TEST = '''
import json, sys
from datasets.colmap import Parser
p = Parser(data_dir=sys.argv[1], factor=1, normalize=True, test_every=8)
print(json.dumps({"parser_images": len(p.image_names), "parser_points": int(len(getattr(p, "points", [])))}))
'''


def patch_pycolmap():
    """NumPy 2 rejects np.uint64(-1); express the sentinel explicitly. Reports exactly what was changed."""
    import importlib
    import importlib.util
    import pathlib

    importlib.invalidate_caches()
    spec = importlib.util.find_spec("pycolmap")
    if spec is None:
        return {"error": "pycolmap is not importable"}
    roots = list(spec.submodule_search_locations or [os.path.dirname(spec.origin)])
    patched = []
    for root in roots:
        for p in pathlib.Path(root).rglob("*.py"):
            text = p.read_text()
            new = re.sub(r"\b(np|numpy)\.uint64\(\s*-1\s*\)", "np.uint64(0xFFFFFFFFFFFFFFFF)", text)
            if new != text:
                p.write_text(new)
                patched.append(str(p))
    return {"roots": roots, "patched_files": patched}


def sh(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def stream(cmd, cwd=None, env=None, every=1):
    print("$", " ".join(cmd), flush=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            bufsize=1, cwd=cwd, env=env)
    tail = deque(maxlen=30)
    n = 0
    with open(LOG, "a") as fh:
        for line in proc.stdout:
            fh.write(line)
            tail.append(line)
            n += 1
            if every == 1 or n % every == 0 or "rror" in line:
                print(line, end="", flush=True)
    return proc.wait(), "".join(tail)


def probe(job):
    info = {"python": sys.version.split()[0], "cpu_count": os.cpu_count()}
    for line in open("/proc/meminfo"):
        if line.startswith("MemTotal"):
            info["ram_gb"] = round(int(line.split()[1]) / 1024 / 1024, 1)
            break
    info["disk_free_gb"] = round(shutil.disk_usage("/content").free / 1e9, 1)
    info["os"] = sh("grep PRETTY_NAME /etc/os-release")
    info["gpu"] = sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader")
    info["nvcc"] = sh("nvcc --version | tail -1")
    return info


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def assemble(job):
    parts = sorted(f for f in os.listdir("/content") if f.startswith(job["parts_prefix"]))
    if len(parts) != job["num_parts"]:
        raise RuntimeError(f"Expected {job['num_parts']} upload parts, found {len(parts)}")
    with open(job["workspace_tar"], "wb") as out:
        for p in parts:
            with open(f"/content/{p}", "rb") as fh:
                shutil.copyfileobj(fh, out)
    if sha256(job["workspace_tar"]) != job["sha256"]:
        raise RuntimeError("Uploaded workspace failed its checksum")


def split_result(path, prefix, chunk):
    n = 0
    with open(path, "rb") as fh:
        while True:
            data = fh.read(chunk)
            if not data:
                break
            with open(f"/content/{prefix}{n:03d}", "wb") as out:
                out.write(data)
            n += 1
    return n


def dense(job):
    assemble(job)
    work = "/content/work"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    with tarfile.open(job["workspace_tar"]) as tar:
        tar.extractall(work)
    ws = f"{work}/workspace"

    if not ensure_micromamba():
        raise RuntimeError("micromamba could not be downloaded")
    gpu = sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader")

    attempts = []
    for i, spec in enumerate(job["colmap_specs"]):
        env = f"/content/cm{i}"
        att = {"spec": spec}
        attempts.append(att)

        t0 = time.time()
        rc, tail = stream([MM, "create", "-y", "-p", env, "-c", "conda-forge", spec])
        att["install_seconds"] = round(time.time() - t0, 1)
        if rc != 0:
            att["failed"] = "install: " + tail[-600:]
            continue

        colmap = [MM, "run", "-p", env, "colmap"]
        att["banner"] = sh(" ".join(colmap) + " -h 2>&1 | head -3")
        if "without GPU" in att["banner"]:
            att["failed"] = "this build has no GPU support"
            continue

        t0 = time.time()
        rc, tail = stream(colmap + ["patch_match_stereo", "--workspace_path", ws, "--workspace_format", "COLMAP",
                                    "--PatchMatchStereo.geom_consistency",
                                    "true" if job["geom_consistency"] else "false"])
        t_pm = round(time.time() - t0, 1)
        if rc != 0:
            att["failed"] = "patch_match_stereo: " + tail[-600:]
            continue

        t0 = time.time()
        rc, tail = stream(colmap + ["stereo_fusion", "--workspace_path", ws, "--workspace_format", "COLMAP",
                                    "--input_type", "geometric", "--output_path", f"{ws}/fused.ply"])
        t_fu = round(time.time() - t0, 1)
        if rc != 0:
            att["failed"] = "stereo_fusion: " + tail[-600:]
            continue

        result_tar = "/content/dense_result.tar.gz"
        with tarfile.open(result_tar, "w:gz") as tar:
            tar.add(f"{ws}/fused.ply", arcname="fused.ply")
            tar.add(LOG, arcname="remote_dense.log")
        n_parts = split_result(result_tar, "dense_result.part", job["chunk_bytes"])
        return {"gpu": gpu, "colmap_spec": spec, "banner": att["banner"], "seconds_patch_match": t_pm,
                "seconds_fusion": t_fu, "attempts": attempts,
                "result_parts": n_parts, "result_sha256": sha256(result_tar)}

    raise RuntimeError("All COLMAP CUDA attempts failed:\n" + json.dumps(attempts, indent=2))

def ensure_micromamba():
    def works():
        return os.path.exists(MM) and subprocess.run([MM, "--version"], capture_output=True).returncode == 0

    if works():
        return True
    os.makedirs("/content/bin", exist_ok=True)
    for cmd in (
        "curl -fsSL --retry 3 https://micro.mamba.pm/api/micromamba/linux-64/latest "
        "| tar -xj -C /content bin/micromamba",
        f"curl -fsSL --retry 3 -o {MM} "
        f"https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-linux-64 "
        f"&& chmod +x {MM}",
    ):
        out = sh(cmd, timeout=300)
        if works():
            return True
        print("micromamba download failed:", out[-200:], flush=True)
    return False


FUSED_SSIM_SHIM = '''
import torch
import torch.nn.functional as F


def _window(C, device, dtype, win=11, sigma=1.5):
    x = torch.arange(win, dtype=torch.float32) - win // 2
    g = torch.exp(-(x ** 2) / (2 * sigma ** 2))
    g = g / g.sum()
    return (g[:, None] @ g[None, :]).to(device=device, dtype=dtype).expand(C, 1, win, win).contiguous()


def fused_ssim(img1, img2, padding="same", train=True):
    """Pure-PyTorch SSIM (mean over image). img*: (B, C, H, W)."""
    C = img1.shape[1]
    w = _window(C, img1.device, img1.dtype)
    pad = 5 if padding == "same" else 0
    mu1 = F.conv2d(img1, w, padding=pad, groups=C)
    mu2 = F.conv2d(img2, w, padding=pad, groups=C)
    mu1_sq, mu2_sq, mu12 = mu1 * mu1, mu2 * mu2, mu1 * mu2
    s1 = F.conv2d(img1 * img1, w, padding=pad, groups=C) - mu1_sq
    s2 = F.conv2d(img2 * img2, w, padding=pad, groups=C) - mu2_sq
    s12 = F.conv2d(img1 * img2, w, padding=pad, groups=C) - mu12
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    ssim_map = ((2 * mu12 + c1) * (2 * s12 + c2)) / ((mu1_sq + mu2_sq + c1) * (s1 + s2 + c2))
    return ssim_map.mean()
'''


SMOKE = '''
import torch
from gsplat import rasterization
dev = "cuda"
N = 100
means = torch.randn(N, 3, device=dev)
means[:, 2] += 3
quats = torch.nn.functional.normalize(torch.randn(N, 4, device=dev), dim=-1)
scales = torch.rand(N, 3, device=dev) * 0.1 + 0.02
opac = torch.rand(N, device=dev)
colors = torch.rand(N, 3, device=dev)
K = torch.tensor([[100.0, 0, 64], [0, 100.0, 64], [0, 0, 1]], device=dev)[None]
view = torch.eye(4, device=dev)[None]
img, alpha, _ = rasterization(means, quats, scales, opac, colors, view, K, 128, 128)
torch.cuda.synchronize()
print("rasterization OK", tuple(img.shape))
'''


def install_gsplat():
    import torch
    tv = torch.__version__.split("+")[0].split(".")
    tag = f"pt{tv[0]}{tv[1]}cu{(torch.version.cuda or '').replace('.', '')}"
    pip = [sys.executable, "-m", "pip", "install", "-q"]
    attempts, ok = [], False
    for label, cmd in (
        (f"prebuilt wheel {tag}", pip + ["gsplat", "--index-url", f"https://docs.gsplat.studio/whl/{tag}",
                                         "--extra-index-url", "https://pypi.org/simple"]),
        ("pypi source build", pip + ["gsplat"]),
    ):
        rc, tail = stream(cmd)
        attempts.append({"method": label, "rc": rc, "tail": tail[-300:] if rc else ""})
        if rc == 0:
            ok = True
            break
    if not ok:
        raise RuntimeError("gsplat install failed: " + json.dumps(attempts, indent=2))
    ver = sh(f"{sys.executable} -m pip show gsplat | grep -i '^Version'").split(":")[-1].strip().split("+")[0]

    src = "/content/gsplat_src"
    shutil.rmtree(src, ignore_errors=True)
    url = "https://github.com/nerfstudio-project/gsplat"
    rc, _ = stream(["git", "clone", "--depth", "1", "--branch", f"v{ver}", url, src])
    if rc != 0:
        rc, _ = stream(["git", "clone", "--depth", "1", url, src])
        if rc != 0:
            raise RuntimeError("could not clone the gsplat examples")

    failed = []
    for line in open(f"{src}/examples/requirements.txt"):
        req = line.strip()
        if not req or req.startswith("#") or req.lower().startswith("numpy"):
            continue
        extra = ["--no-build-isolation"] if "fused" in req.lower() else []
        rc, tail = stream(pip + extra + shlex.split(req))
        if rc != 0:
            failed.append({"requirement": req, "tail": tail[-400:]})

    patch = patch_pycolmap()
    env = dict(os.environ)
    used_shim = False
    if subprocess.run([sys.executable, "-c", "import fused_ssim"], capture_output=True).returncode != 0:
        os.makedirs("/content/shims", exist_ok=True)
        open("/content/shims/fused_ssim.py", "w").write(FUSED_SSIM_SHIM)
        env["PYTHONPATH"] = "/content/shims:" + env.get("PYTHONPATH", "")
        used_shim = True


    ds = f"{src}/examples/datasets"
    if os.path.isdir(ds) and not os.path.exists(f"{ds}/__init__.py"):
        open(f"{ds}/__init__.py", "w").close()

    trainer = f"{src}/examples/simple_trainer.py"
    renames = {"cv2": "opencv-python", "sklearn": "scikit-learn", "yaml": "pyyaml", "PIL": "Pillow"}
    help_rc, help_tail = 1, ""
    for _ in range(4):
        help_rc, help_tail = stream([sys.executable, trainer, "default", "--help"], env=env, every=100)
        if help_rc == 0:
            break
        m = re.search(r"No module named '([\w.]+)'", help_tail)
        if not m:
            break
        mod = m.group(1).split(".")[0]
        already_installed = subprocess.run(
            [sys.executable, "-c", f"import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('{mod}') else 1)"],
            capture_output=True).returncode == 0
        if already_installed:
            break            # present but failing to import (a conflict): pip cannot fix this
        rc2, _ = stream(pip + [renames.get(mod, mod)])
        if rc2 != 0:
            break
    if help_rc != 0:
        diag = sh(f"ls -la {ds}; {sys.executable} -c \"import datasets; print(datasets.__file__)\"")
        raise RuntimeError("the gsplat trainer cannot start:\n" + help_tail[-1500:] +
                           "\n--- diagnostics ---\n" + diag +
                           "\nfailed requirements: " + json.dumps([f["requirement"] for f in failed]))

    rc, tail = stream([sys.executable, "-c", SMOKE], env=env)
    if rc != 0:
        raise RuntimeError("GPU rasterization smoke test failed:\n" + tail[-1200:])

    return ({"gsplat_version": ver, "torch": torch.__version__, "install_attempts": attempts,
             "failed_requirements": [f["requirement"] for f in failed],
             "pycolmap_patch": patch,
             "numpy": sh(f"{sys.executable} -c 'import numpy; print(numpy.__version__)'"),
             "fused_ssim": "pytorch shim" if used_shim else "cuda"}, src, env)

def compress_splat(ply, out_dir, formats):
    results = {}
    try:
        if not ensure_micromamba():
            return {"error": "micromamba could not be downloaded"}
        node = "/content/node"
        if not os.path.exists(f"{node}/bin/npx"):
            rc, tail = stream([MM, "create", "-y", "-p", node, "-c", "conda-forge", "nodejs"])
            if rc != 0:
                return {"error": "nodejs install failed: " + tail[-300:]}
        env = dict(os.environ, PATH=f"{node}/bin:" + os.environ.get("PATH", ""))
        for fmt in formats:
            dst = f"{out_dir}/scene.{fmt}"
            rc, tail = stream([f"{node}/bin/npx", "--yes", "@playcanvas/splat-transform", ply, dst], env=env)
            results[fmt] = True if (rc == 0 and os.path.exists(dst)) else "failed: " + tail[-300:]
    except Exception as exc:
        results["error"] = f"{type(exc).__name__}: {exc}"
    return results


def clean_ply(src, dst, min_opacity=0.3, max_scale_frac=0.05, crop_factor=1.5):
    """Drop likely floaters from a 3DGS PLY: near-transparent, oversized, and far-away Gaussians."""
    import numpy as np

    read = {"float": "<f4", "float32": "<f4", "double": "<f8", "uchar": "u1", "uint8": "u1",
            "int": "<i4", "int32": "<i4", "uint": "<u4", "short": "<i2", "ushort": "<u2",
            "char": "i1"}
    write = {"<f4": "float", "<f8": "double", "u1": "uchar", "<i4": "int", "<u4": "uint",
             "<i2": "short", "<u2": "ushort", "i1": "char"}
    props, n, in_vertex = [], None, False
    with open(src, "rb") as fh:
        while True:
            line = fh.readline().decode("ascii").strip()
            if line.startswith("format") and "binary_little_endian" not in line:
                raise ValueError("Only binary little-endian PLY files are supported")
            if line.startswith("element"):
                parts = line.split()
                in_vertex = parts[1] == "vertex"
                if in_vertex:
                    n = int(parts[2])
            elif line.startswith("property") and in_vertex:
                _, typ, name = line.split()
                props.append((name, read[typ]))
            elif line == "end_header":
                break
        d = np.fromfile(fh, dtype=np.dtype(props), count=n)

    xyz = np.stack([d["x"], d["y"], d["z"]], axis=1).astype(np.float64)
    opacity = 1 / (1 + np.exp(-d["opacity"].astype(np.float64)))
    size = np.exp(np.max(np.stack([d["scale_0"], d["scale_1"], d["scale_2"]], axis=1)
                         .astype(np.float64), axis=1))
    solid = opacity > 0.5
    if not solid.any():
        raise ValueError("Cannot clean PLY: no Gaussians have opacity greater than 0.5")
    center = np.median(xyz[solid], axis=0)
    dist = np.linalg.norm(xyz - center, axis=1)
    radius = float(np.percentile(dist[solid], 90))
    keep, removed = np.ones(len(d), bool), {}
    for label, mask in (("low_opacity", opacity >= min_opacity),
                        ("oversized", size <= max_scale_frac * radius if max_scale_frac else keep),
                        ("far_away", dist <= crop_factor * radius if crop_factor else keep)):
        before = int(keep.sum())
        keep &= mask
        removed[label] = before - int(keep.sum())

    out = d[keep]
    header = "ply\nformat binary_little_endian 1.0\nelement vertex %d\n" % len(out)
    header += "".join(f"property {write[t]} {name}\n" for name, t in props) + "end_header\n"
    with open(dst, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(out.tobytes())
    return {"before": int(len(d)), "after": int(len(out)), "scene_radius": round(radius, 4), "removed": removed}


def splat(job):
    assemble(job)
    work = "/content/work"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    with tarfile.open(job["workspace_tar"]) as tar:
        tar.extractall(work)
    ws = f"{work}/workspace"
    gpu = sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader")

    t0 = time.time()
    info, src, train_env = install_gsplat()
    t_install = round(time.time() - t0, 1)
    help_txt = subprocess.run([sys.executable, f"{src}/examples/simple_trainer.py", "default", "--help"],
                              capture_output=True, text=True, env=train_env).stdout

    steps = int(job["max_steps"])
    res = "/content/splat_run"
    shutil.rmtree(res, ignore_errors=True)
    t0 = time.time()
    rc, tail = stream([sys.executable, f"{src}/examples/simple_trainer.py", "default",
                       "--data_dir", ws, "--data_factor", str(job["data_factor"]), "--result_dir", res,
                       "--max_steps", str(steps), "--disable_viewer", "--eval_steps", str(steps),
                       "--save_ply", "--ply_steps", str(steps)] +
                      [str(a) for a in job.get("extra_args") or []],
                      env=train_env, every=200)
    t_train = round(time.time() - t0, 1)
    if rc != 0:
        raise RuntimeError("training failed:\n" + tail[-1500:])

    plys = sorted(glob.glob(f"{res}/ply/*.ply"))
    if not plys:
        raise RuntimeError("training finished but no PLY was found:\n" + sh(f"find {res} -maxdepth 2 | head -40"))
    stats_files = sorted(glob.glob(f"{res}/stats/val_step*.json"))
    stats = json.load(open(stats_files[-1])) if stats_files else {}

    ply_out, clean_stats = plys[-1], None
    if job.get("clean"):
        try:
            clean_stats = clean_ply(plys[-1], "/content/splat_clean.ply", **job["clean"])
            ply_out = "/content/splat_clean.ply"
        except Exception as exc:
            clean_stats = {"error": f"{type(exc).__name__}: {exc}"}

    out_dir = "/content/splat_out"
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    open(f"{out_dir}/trainer_help.txt", "w").write(help_txt)
    comp = compress_splat(ply_out, out_dir, job["compress"])
    if job["download_ply"] or not any(comp.get(f) is True for f in job["compress"]):
        shutil.copy(ply_out, f"{out_dir}/scene.ply")
    shutil.copy(LOG, f"{out_dir}/splat_train.log")
    json.dump(stats, open(f"{out_dir}/stats.json", "w"), indent=2)

    result_tar = "/content/splat_result.tar.gz"
    with tarfile.open(result_tar, "w:gz") as tar:
        for name in os.listdir(out_dir):
            tar.add(f"{out_dir}/{name}", arcname=name)
    n_parts = split_result(result_tar, "splat_result.part", job["chunk_bytes"])
    return {**info, "gpu": gpu, "seconds_install": t_install, "seconds_train": t_train,
            "psnr": stats.get("psnr"), "ssim": stats.get("ssim"), "lpips": stats.get("lpips"),
            "num_gaussians": stats.get("num_GS"), "clean": clean_stats, "compress": comp,
            "ply_mb": round(os.path.getsize(plys[-1]) / 1e6, 1),
            "result_parts": n_parts, "result_sha256": sha256(result_tar)}


def gsplat_check(job):
    t0 = time.time()
    info, src, env = install_gsplat()
    result = {**info}
    if job.get("num_parts"):
        assemble(job)
        work = "/content/work_check"
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        with tarfile.open(job["workspace_tar"]) as tar:
            tar.extractall(work)
        ws = f"{work}/workspace"
        from PIL import Image

        for name in open(f"{ws}/image_names.txt").read().split("\n"):
            if name:
                path = f"{ws}/images/{name}"
                os.makedirs(os.path.dirname(path), exist_ok=True)
                Image.new("RGB", (64, 48)).save(path)
        rc, tail = stream([sys.executable, "-c", PARSER_TEST, ws], cwd=f"{src}/examples", env=env)
        if rc != 0:
            roots = " ".join(info.get("pycolmap_patch", {}).get("roots", []))
            diag = sh(f"grep -rn 'uint64' {roots} | head -20") if roots else ""
            raise RuntimeError("COLMAP parser check failed:\n" + tail[-1500:] +
                               "\n--- uint64 occurrences in pycolmap ---\n" + diag)
        result["parser"] = tail.strip().splitlines()[-1]
    result["seconds"] = round(time.time() - t0, 1)
    return result


ACTIONS = {"probe": probe, "dense": dense, "splat": splat, "gsplat_check": gsplat_check}


def main():
    for f in (RESULT, LOG):
        if os.path.exists(f):
            os.remove(f)
    job = json.load(open(JOB))
    t0 = time.time()
    try:
        result = {"ok": True, "action": job["action"], "data": ACTIONS[job["action"]](job)}
    except Exception:
        result = {"ok": False, "action": job.get("action"), "error": traceback.format_exc()}
    result["seconds"] = round(time.time() - t0, 2)
    result["job_id"] = job.get("job_id")
    with open(RESULT + ".tmp", "w") as fh:
        json.dump(result, fh, indent=2)
    os.replace(RESULT + ".tmp", RESULT)
    print(json.dumps({k: v for k, v in result.items() if k != "data"}, indent=2))


if __name__ == "__main__":
    main()