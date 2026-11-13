from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..pipeline import Context, Stage
from ..remote.bundle import pack, sha256, unpack
from ..remote.executor import ColabExecutor
from .features import effective_matcher


class ReconstructionStage(Stage):
    """Run the memory-intensive COLMAP reconstruction chain on Colab."""

    name = "reconstruction"
    dir_name = "06_reconstruction"
    requires = ("validate",)

    def config_slice(self, cfg):
        return {
            "features": cfg["features"],
            "sparse": cfg["sparse"],
            "undistort": cfg["undistort"],
            "dense": cfg["dense"],
            "remote": {key: cfg["remote"].get(key) for key in
                       ("session", "gpu", "high_mem", "gpu_fallbacks", "chunk_mb", "io_timeout")},
            "colmap_specs": cfg["dense"]["colmap_specs"],
        }

    def run(self, ctx: Context) -> dict:
        cfg = ctx.cfg
        out = ctx.run.stage_dir(self.dir_name)
        accepted = json.loads((ctx.run.stage_dir("02_validate") / "accepted.json").read_text())
        ingest_dir = ctx.run.stage_dir("01_ingest")
        input_dir = out / "upload" / "input"
        shutil.rmtree(input_dir, ignore_errors=True)
        images_dir = input_dir / "images"
        images_dir.mkdir(parents=True)

        image_names = sorted(
            str(Path(relative).relative_to(ingest_dir / "images")).replace("\\", "/")
            for paths in accepted.values()
            for relative in paths
        )
        if not image_names:
            raise RuntimeError("Image validation accepted no photos for reconstruction.")
        for name in image_names:
            source = ingest_dir / "images" / name
            destination = images_dir / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        (input_dir / "image_list.txt").write_text("\n".join(image_names), encoding="utf-8")

        input_tar = out / "colab_input.tar.gz"
        digest = pack({"input": input_dir}, input_tar)
        upload_mb = round(input_tar.stat().st_size / 1e6, 1)
        shutil.rmtree(out / "upload", ignore_errors=True)

        remote = cfg["remote"]
        chunk_mb = int(remote.get("chunk_mb", 4))
        parts_prefix = f"reconstruction_input_{ctx.run.root.name}.part"
        executor = ColabExecutor(remote["session"], remote.get("gpu"), remote.get("high_mem", True),
                                 remote.get("auth"), fallback_gpus=remote.get("gpu_fallbacks", []),
                                 io_timeout=int(remote.get("io_timeout", 600)))
        result_tar = out / "colab_result.tar.gz"
        result = None
        with executor.open_session():
            parts = executor.upload_chunked(input_tar, parts_prefix, chunk_mb)
            result = executor.run_job({
                "action": "reconstruct_mesh",
                "job_id": ctx.run.root.name,
                "workspace_tar": "/content/reconstruction_input.tar.gz",
                "parts_prefix": parts_prefix,
                "num_parts": parts,
                "sha256": digest,
                "chunk_bytes": chunk_mb * 1024 * 1024,
                "image_count": len(image_names),
                "matcher": effective_matcher(cfg),
                "sequential_overlap": int(cfg["features"]["sequential_overlap"]),
                "camera_model": cfg["features"]["camera_model"],
                "max_image_size": int(cfg["features"]["max_image_size"]),
                "num_threads": int(cfg["features"]["num_threads"]),
                "mapper": cfg["sparse"]["mapper"],
                "undistort_max_image_size": int(cfg["undistort"]["max_image_size"]),
                "geom_consistency": bool(cfg["dense"]["geom_consistency"]),
                "colmap_specs": cfg["dense"]["colmap_specs"],
            }, out / "remote", on_output=self._track_remote_stages(ctx))
            if result.get("ok"):
                executor.download_chunked("reconstruction_result.part", result["data"]["result_parts"], result_tar)

        if not result or not result.get("ok"):
            raise RuntimeError("Remote Colab reconstruction failed:\n" + (result or {}).get("error", "unknown error"))
        data = result["data"]
        if sha256(result_tar) != data["result_sha256"]:
            raise RuntimeError("Downloaded Colab reconstruction failed its checksum; retry the scan.")
        unpack(result_tar, out)
        shutil.rmtree(out / "remote", ignore_errors=True)
        input_tar.unlink(missing_ok=True)
        result_tar.unlink(missing_ok=True)
        for stage in ("features", "sparse", "undistort", "dense"):
            ctx.manifest.update(stage, status="done", finished="remote-complete")
        return {
            "input_images": len(image_names),
            "registered_by_group": data["registered_by_group"],
            "best_model": data["best_model"],
            "matcher": data["matcher"],
            "gpu": data["gpu"],
            "colmap_spec": data["colmap_spec"],
            "seconds_features": data["seconds_features"],
            "seconds_matching": data["seconds_matching"],
            "seconds_mapper": data["seconds_mapper"],
            "seconds_undistort": data["seconds_undistort"],
            "seconds_patch_match": data["seconds_patch_match"],
            "seconds_fusion": data["seconds_fusion"],
            "fused_points": data["fused_points"],
            "upload_mb": upload_mb,
            "colab_seconds": result.get("seconds"),
        }

    @staticmethod
    def _track_remote_stages(ctx: Context):
        order = ("features", "sparse", "undistort", "dense")
        buffer = ""

        def update(chunk: str) -> None:
            nonlocal buffer
            buffer = (buffer + chunk)[-512:]
            marker = "@@RECON_STAGE@@"
            if marker not in buffer:
                return
            stage = buffer.rsplit(marker, 1)[1].splitlines()[0].strip()
            if stage not in order:
                return
            for name in order:
                if name == stage:
                    ctx.manifest.update(name, status="running", started="remote")
                    break
                ctx.manifest.update(name, status="done", finished="remote")

        return update
