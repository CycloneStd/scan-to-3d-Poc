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

        full = out / "meshed-poisson.ply"
        r1 = run([binary, "poisson_mesher", "--input_path", ctx.run.stage_dir("06_dense") / "fused.ply",
                  "--output_path", full], log_file=logf)
        c = ply_counts(full)
        metrics = {"poisson_seconds": r1.seconds, "full_vertices": c.get("vertex"), "full_faces": c.get("face")}

        mesh_for_texture = full
        ratio = ctx.cfg["mesh"].get("target_face_ratio")
        if ratio:
            if "target_face_ratio" not in cm.help_text(binary, "mesh_simplifier"):
                raise RuntimeError("This COLMAP's mesh_simplifier has no target_face_ratio option; "
                                   "paste the output of `colmap mesh_simplifier -h`")
            simplified = out / "meshed-simplified.ply"
            r2 = run([binary, "mesh_simplifier", "--input_path", full, "--output_path", simplified,
                      "--MeshSimplification.target_face_ratio", ratio], log_file=logf)
            c = ply_counts(simplified)
            metrics.update(simplify_seconds=r2.seconds, mesh_vertices=c.get("vertex"), mesh_faces=c.get("face"))
            mesh_for_texture = simplified

        if ctx.cfg["mesh"]["texture"]:
            r3 = run([binary, "mesh_texturer",
                      "--workspace_path", ctx.run.stage_dir("05_undistort") / "workspace",
                      "--input_path", mesh_for_texture, "--output_path", out / "textured"], log_file=logf)
            metrics["texture_seconds"] = r3.seconds
        metrics["files"] = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
        return metrics