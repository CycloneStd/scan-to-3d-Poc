from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from ..ar import estimate_up, orient_obj
from ..pipeline import Context, Stage
from ..utils import colmap as cm
from ..utils.ply import ply_counts
from ..utils.ply_to_obj import convert_textured_ply
from ..utils.proc import run


class ArStage(Stage):
    name = "ar"
    dir_name = "11_ar"
    requires = ("mesh", "reconstruction")

    def config_slice(self, cfg):
        return {"ar": cfg["ar"], "flip_v": cfg["export"]["flip_v"],
                "colmap": cm.version(cfg["colmap"]["binary"]), "blender": cfg["blender"]}

    def run(self, ctx: Context) -> dict:
        cfg, ar = ctx.cfg, ctx.cfg["ar"]
        binary = cfg["colmap"]["binary"]
        out = ctx.run.stage_dir(self.dir_name)
        log_file = ctx.run.root / "logs" / "ar.log"
        reconstruction_dir = ctx.run.stage_dir("06_reconstruction")
        remote_ar = reconstruction_dir / "ar"

        if ctx.manifest.get("reconstruction")["metrics"].get("ar_reuses_mesh"):
            remote_ar = reconstruction_dir / "mesh"
        if (remote_ar / "textured" / "mesh.ply").exists():
            textured = out / "textured"
            shutil.rmtree(textured, ignore_errors=True)
            shutil.copytree(remote_ar / "textured", textured)
        else:
            for path in out.iterdir():
                shutil.rmtree(path) if path.is_dir() else path.unlink()
            full = ctx.run.stage_dir("07_mesh") / "meshed-poisson.ply"
            if not full.exists():
                full = ctx.run.stage_dir("07_mesh") / "meshed-full.ply"
            if not full.exists():
                full = ctx.run.stage_dir("07_mesh") / "meshed-simplified.ply"
            full_faces = ply_counts(full)["face"] if full.exists() else 0
            if full_faces <= 0:
                raise RuntimeError(f"Poisson mesh has no faces: {full}")
            ratio = min(1.0, ar["target_faces"] / full_faces)
            small = out / "mesh_ar.ply"
            run([binary, "mesh_simplifier", "--input_path", full, "--output_path", small,
                 "--MeshSimplification.target_face_ratio", ratio], log_file=log_file)

            textured = out / "textured"
            run([binary, "mesh_texturer", "--workspace_path", reconstruction_dir / "workspace",
                 "--input_path", small, "--output_path", textured], log_file=log_file)

        obj = out / "mesh_ar.obj"
        convert_textured_ply(textured / "mesh.ply", "texture_ar.jpg", obj,
                             flip_v=cfg["export"]["flip_v"], max_edge_factor=cfg["mesh"].get("max_edge_factor"))
        with Image.open(textured / "texture.png") as image:
            image.thumbnail((ar["texture_px"], ar["texture_px"]), Image.Resampling.LANCZOS)
            image.convert("RGB").save(out / "texture_ar.jpg", quality=int(ar["jpeg_quality"]))
        shutil.rmtree(textured, ignore_errors=True)

        images_txt = reconstruction_dir / "best_model_txt" / "images.txt"
        up, coherence, camera_count = estimate_up(images_txt)
        info = orient_obj(obj, up, ar.get("scale_factor"))

        script = Path(__file__).resolve().parents[1] / "validation" / "ar_export.py"
        run([cfg["blender"]["binary"], "-b", "--factory-startup", "--python-exit-code", "1", "--python", script, "--",
             "--input", obj.resolve(), "--outdir", out.resolve(), "--name", "model_ar"],
            log_file=log_file)
        report_path = out / "ar_report.json"
        report = json.loads(report_path.read_text())
        report.update({
            "faces_requested": ar["target_faces"],
            "up_agreement": round(coherence, 3),
            "cameras_used": camera_count,
            "oriented_size_x_y_z": info["size_x_y_z"],
            "scale_factor": ar.get("scale_factor"),
            "scale": ("factor %s applied" % ar["scale_factor"]) if ar.get("scale_factor")
                     else "UNSCALED: arbitrary model units are exported as if they were metres",
        })
        report_path.write_text(json.dumps(report, indent=2))
        return report
