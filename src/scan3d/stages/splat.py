from __future__ import annotations

import shutil
from pathlib import Path

import cv2

from ..pipeline import Context, Stage
from ..remote.bundle import pack, unpack
from ..remote.roundtrip import roundtrip
from ..utils.proc import run
from .dense import make_upload_workspace


def check_workspace(binary: str, ws: Path, tmp: Path) -> None:
    """Every camera's recorded size must equal the size of the images that use it."""
    txt = tmp / "ws_check_txt"
    shutil.rmtree(txt, ignore_errors=True)
    txt.mkdir(parents=True)
    run([binary, "model_converter", "--input_path", ws / "sparse", "--output_path", txt, "--output_type", "TXT"])
    cams = {}
    for ln in (txt / "cameras.txt").read_text().splitlines():
        if ln and not ln.startswith("#"):
            f = ln.split()
            cams[f[0]] = (int(f[2]), int(f[3]))
    lines = [ln for ln in (txt / "images.txt").read_text().splitlines() if not ln.startswith("#")]
    seen = {}
    for ln in lines[::2]:
        f = ln.split()
        if len(f) >= 10:
            seen.setdefault(f[8], f[9])
    for cam_id, name in seen.items():
        image = cv2.imread(str(ws / "images" / name))
        if image is None:
            raise RuntimeError(f"Could not read image {name} while checking camera dimensions")
        h, w = image.shape[:2]
        cw, ch = cams[cam_id]
        if abs(w - cw) > 1 or abs(h - ch) > 1:
            raise RuntimeError(f"Camera {cam_id} says {cw}x{ch} but {name} is {w}x{h}")


def undistort_small(ctx: Context, out: Path, size: int) -> Path:
    binary = ctx.cfg["colmap"]["binary"]
    sp = ctx.manifest.get("sparse")["metrics"]
    model = ctx.run.stage_dir(f"04_sparse_{sp['mapper']}") / "models" / sp["best_model"]["model"]
    ws = out / "ws_small"
    shutil.rmtree(ws, ignore_errors=True)
    run([binary, "image_undistorter", "--image_path", ctx.run.stage_dir("01_ingest") / "images",
         "--input_path", model, "--output_path", ws, "--output_type", "COLMAP", "--max_image_size", size],
        log_file=ctx.run.root / "logs" / "undistort_splat.log")
    check_workspace(binary, ws, ctx.run.root / "logs")
    return ws


class SplatStage(Stage):
    name = "splat"
    dir_name = "09_splat"
    requires = ("undistort",)

    def config_slice(self, cfg):
        return {"splat": cfg["splat"], "gpu": cfg["remote"].get("gpu")}

    def run(self, ctx: Context) -> dict:
        sc = ctx.cfg["splat"]
        out = ctx.run.stage_dir(self.dir_name)
        size = sc.get("max_image_size")
        src_ws = undistort_small(ctx, out, int(size)) if size else ctx.run.stage_dir("05_undistort") / "workspace"
        staged = out / "upload_ws" / "workspace"
        make_upload_workspace(src_ws, staged, int(sc["upload_jpeg_quality"]))
        tar = out / "workspace.tar.gz"
        digest = pack({"workspace": staged}, tar)
        shutil.rmtree(out / "upload_ws", ignore_errors=True)
        if size:
            shutil.rmtree(out / "ws_small", ignore_errors=True)

        data, result_tar = roundtrip(
            ctx.cfg, out, tar, digest,
            {"action": "splat", "max_steps": int(sc["max_steps"]), "data_factor": int(sc["data_factor"]),
             "extra_args": [str(a) for a in (sc.get("extra_args") or [])],
             "compress": list(sc["compress"]), "download_ply": bool(sc["download_ply"]),
             "clean": dict(sc["clean"]) if sc.get("clean") else None},
            "splat_result.part")
        unpack(result_tar, out)

        files_mb = {p.name: round(p.stat().st_size / 1e6, 2) for p in sorted(out.iterdir())
                    if p.is_file() and p.suffix in (".ply", ".spz", ".sog")}
        keys = ("psnr", "ssim", "lpips", "num_gaussians", "clean", "seconds_install", "seconds_train",
                "compress", "timing", "wall_s", "bundle_mb", "upload_workers", "gsplat_version", "gpu")
        return {k: data.get(k) for k in keys} | {"max_steps": sc["max_steps"], "extra_args": sc.get("extra_args"),
                                                  "max_image_size": size, "files_mb": files_mb}
