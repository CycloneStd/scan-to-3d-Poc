from __future__ import annotations

import shutil

from ..pipeline import Context, Stage
from ..utils import colmap as cm
from ..utils.ply import ply_counts
from ..utils.proc import run


class MeshStage(Stage):
    name = "mesh"
    dir_name = "07_mesh"
    requires = ("dense",)

    def config_slice(self, cfg):
        return {"mesh": cfg["mesh"], "colmap": cm.version(cfg["colmap"]["binary"])}

    def run(self, ctx: Context) -> dict:
        binary = ctx.cfg["colmap"]["binary"]
        out = ctx.run.stage_dir(self.dir_name)
        for p in out.iterdir():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        logf = ctx.run.root / "logs" / "mesh.log"

        mesh = out / "meshed-poisson.ply"
        r1 = run([binary, "poisson_mesher", "--input_path", ctx.run.stage_dir("06_dense") / "fused.ply",
                  "--output_path", mesh], log_file=logf)
        counts = ply_counts(mesh)
        metrics = {"poisson_seconds": r1.seconds, "mesh_vertices": counts.get("vertex"),
                   "mesh_faces": counts.get("face")}

        if ctx.cfg["mesh"]["texture"]:
            r2 = run([binary, "mesh_texturer",
                      "--workspace_path", ctx.run.stage_dir("05_undistort") / "workspace",
                      "--input_path", mesh, "--output_path", out / "textured"], log_file=logf)
            metrics["texture_seconds"] = r2.seconds
        metrics["files"] = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
        return metrics