import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
import hashlib
from collections import deque

JOB = "/content/job.json"
RESULT = "/content/result.json"
LOG = "/content/dense.log"
MM = "/content/bin/micromamba"


def sh(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def stream(cmd):
    print("$", " ".join(cmd), flush=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    tail = deque(maxlen=30)
    with open(LOG, "a") as fh:
        for line in proc.stdout:
            fh.write(line)
            tail.append(line)
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

    if not os.path.exists(MM):
        sh("mkdir -p /content/bin && curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest "
           "| tar -xj -C /content bin/micromamba", timeout=300)
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


ACTIONS = {"probe": probe, "dense": dense}


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
    json.dump(result, open(RESULT, "w"), indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "data"}, indent=2))


main()