from __future__ import annotations

import shutil

from ..pipeline import Context, Stage
from ..utils import colmap as cm
from ..utils.ply import ply_counts
from ..utils.proc import run


class MeshStage(Stage):
    name = "mesh"
    dir_name = "07_mesh"
    requires = ("reconstruction",)

    def config_slice(self, cfg):
        return {"mesh": cfg["mesh"], "colmap": cm.version(cfg["colmap"]["binary"])}

    def run(self, ctx: Context) -> dict:
        binary = ctx.cfg["colmap"]["binary"]
        out = ctx.run.stage_dir(self.dir_name)
        reconstruction_dir = ctx.run.stage_dir("06_reconstruction")
        remote_mesh = reconstruction_dir / "mesh"

        # Check if remote Colab reconstruction already generated the mesh
        if (remote_mesh / "textured" / "mesh.ply").exists() or (out / "textured" / "mesh.ply").exists():
            if remote_mesh.exists():
                for p in remote_mesh.iterdir():
                    dest = out / p.name
                    if p.is_dir():
                        shutil.copytree(p, dest, dirs_exist_ok=True)
                    elif not dest.exists():
                        shutil.copy2(p, dest)
            full = out / "meshed-poisson.ply"
            simplified = out / "meshed-simplified.ply"
            mesh_for_texture = simplified if simplified.exists() else full
            c_full = ply_counts(full) if full.exists() else {}
            c_mesh = ply_counts(mesh_for_texture) if mesh_for_texture.exists() else {}
            recon_entry = ctx.manifest.get("reconstruction") or {}
            recon_metrics = recon_entry.get("metrics") or {}
            return {
                "poisson_seconds": recon_metrics.get("seconds_poisson", 0.0),
                "full_vertices": c_full.get("vertex") or recon_metrics.get("full_vertices"),
                "full_faces": c_full.get("face") or recon_metrics.get("full_faces"),
                "simplify_seconds": recon_metrics.get("seconds_simplify", 0.0),
                "mesh_vertices": c_mesh.get("vertex") or recon_metrics.get("mesh_vertices"),
                "mesh_faces": c_mesh.get("face") or recon_metrics.get("mesh_faces"),
                "texture_seconds": recon_metrics.get("seconds_texture", 0.0),
                "files": sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()),
                "remote_executed": True,
            }

        for p in out.iterdir():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        logf = ctx.run.root / "logs" / "mesh.log"

        full = out / "meshed-poisson.ply"
        poisson_depth = str(ctx.cfg["mesh"].get("poisson_depth", 11))
        poisson_cmd = [binary, "poisson_mesher", "--input_path", reconstruction_dir / "fused.ply",
                       "--output_path", full, "--PoissonMeshing.depth", poisson_depth,
                       "--PoissonMeshing.trim", "1"]
        r1 = run(poisson_cmd, log_file=logf)
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
                      "--workspace_path", reconstruction_dir / "workspace",
                      "--input_path", mesh_for_texture, "--output_path", out / "textured"], log_file=logf)
            metrics["texture_seconds"] = r3.seconds
        metrics["files"] = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
        return metrics
