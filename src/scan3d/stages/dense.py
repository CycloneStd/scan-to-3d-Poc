from __future__ import annotations

import logging
import shutil
from pathlib import Path

import cv2

from ..pipeline import Context, Stage
from ..remote.bundle import pack, sha256, unpack
from ..remote.executor import ColabExecutor
from ..utils.ply import ply_counts

log = logging.getLogger("scan3d.dense")


def make_upload_workspace(src: Path, dst: Path, quality: int) -> None:
    """Copy the undistorted workspace, re-encoding images as JPEG to shrink the upload.
    Dimensions are unchanged, so camera models and depth-map sizes stay valid."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("images"))
    for p in (src / "images").rglob("*"):
        if not p.is_file():
            continue
        out = dst / "images" / p.relative_to(src / "images")
        out.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() in (".jpg", ".jpeg"):
            img = cv2.imread(str(p), cv2.IMREAD_COLOR)
            if img is None:
                raise RuntimeError(f"Could not read {p}")
            cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        else:
            shutil.copy2(p, out)


class DenseStage(Stage):
    name = "dense"
    dir_name = "06_dense"
    requires = ("undistort",)

    def config_slice(self, cfg):
        return {"dense": cfg["dense"], "gpu": cfg["remote"].get("gpu")}

    def run(self, ctx: Context) -> dict:
        cfg = ctx.cfg
        out = ctx.run.stage_dir(self.dir_name)
        ws = ctx.run.stage_dir("05_undistort") / "workspace"

        quality = int(cfg["dense"].get("upload_jpeg_quality", 85))
        upload_ws = out / "upload_ws" / "workspace"
        make_upload_workspace(ws, upload_ws, quality)
        tar = out / "workspace.tar.gz"
        digest = pack({"workspace": upload_ws}, tar)
        log.info("Upload bundle: %.1f MB", tar.stat().st_size / 1e6)
        shutil.rmtree(out / "upload_ws", ignore_errors=True)

        r = cfg["remote"]
        chunk_mb = int(r.get("chunk_mb", 4))
        ex = ColabExecutor(r["session"], r.get("gpu"), r.get("high_mem", True), r.get("auth"),
                           fallback_gpus=r.get("gpu_fallbacks", []))
        result_tar = out / "dense_result.tar.gz"
        result = None
        for attempt in (1, 2):
            try:
                with ex.open_session():
                    n = ex.upload_chunked(tar, "ws.part", chunk_mb)
                    job = {"action": "dense", "workspace_tar": "/content/workspace.tar.gz",
                           "parts_prefix": "ws.part", "num_parts": n, "sha256": digest,
                           "chunk_bytes": chunk_mb * 1024 * 1024,
                           "colmap_specs": cfg["dense"]["colmap_specs"],
                           "geom_consistency": cfg["dense"]["geom_consistency"]}
                    result = ex.run_job(job, out / "remote")
                    if result.get("ok"):
                        ex.download_chunked("dense_result.part", result["data"]["result_parts"], result_tar)
                break
            except RuntimeError as exc:
                log.warning("Remote attempt %d failed: %s", attempt, exc)
                if attempt == 2:
                    raise
        if not result or not result.get("ok"):
            raise RuntimeError("Remote dense stage failed:\n" + (result or {}).get("error", "unknown error"))

        data = result["data"]
        if sha256(result_tar) != data["result_sha256"]:
            raise RuntimeError("Downloaded dense result failed its checksum; re-run the stage")
        unpack(result_tar, out)
        return {"fused_points": ply_counts(out / "fused.ply").get("vertex"),
                "colmap_spec": data["colmap_spec"], "gpu": data["gpu"],
                "upload_mb": round(tar.stat().st_size / 1e6, 1),
                "seconds_patch_match": data["seconds_patch_match"],
                "seconds_fusion": data["seconds_fusion"]}