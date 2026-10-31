from __future__ import annotations

import shutil

from ..pipeline import Context, Stage
from ..utils import colmap as cm
from ..utils.proc import run


class UndistortStage(Stage):
    name = "undistort"
    dir_name = "05_undistort"
    requires = ("sparse",)

    def config_slice(self, cfg):
        return {"undistort": cfg["undistort"], "colmap": cm.version(cfg["colmap"]["binary"])}

    def run(self, ctx: Context) -> dict:
        binary = ctx.cfg["colmap"]["binary"]
        sp = ctx.manifest.get("sparse")["metrics"]
        model = ctx.run.stage_dir(f"04_sparse_{sp['mapper']}") / "models" / sp["best_model"]["model"]
        out = ctx.run.stage_dir(self.dir_name)
        ws = out / "workspace"
        if ws.exists():
            shutil.rmtree(ws)
        res = run([binary, "image_undistorter",
                   "--image_path", ctx.run.stage_dir("01_ingest") / "images",
                   "--input_path", model, "--output_path", ws, "--output_type", "COLMAP",
                   "--max_image_size", ctx.cfg["undistort"]["max_image_size"]],
                  log_file=ctx.run.root / "logs" / "undistort.log")
        n = sum(1 for p in (ws / "images").rglob("*") if p.is_file())
        return {"undistorted_images": n, "seconds": res.seconds}