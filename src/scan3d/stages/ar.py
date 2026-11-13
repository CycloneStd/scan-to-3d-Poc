from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2

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
        for path in out.iterdir():
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        log_file = ctx.run.root / "logs" / "ar.log"

        full = ctx.run.stage_dir("07_mesh") / "meshed-poisson.ply"
        full_faces = ply_counts(full)["face"]
        if full_faces <= 0:
            raise RuntimeError(f"Poisson mesh has no faces: {full}")
        ratio = min(1.0, ar["target_faces"] / full_faces)
        small = out / "mesh_ar.ply"
        run([binary, "mesh_simplifier", "--input_path", full, "--output_path", small,
             "--MeshSimplification.target_face_ratio", ratio], log_file=log_file)

        reconstruction_dir = ctx.run.stage_dir("06_reconstruction")
        textured = out / "textured"
        run([binary, "mesh_texturer", "--workspace_path", reconstruction_dir / "workspace",
             "--input_path", small, "--output_path", textured], log_file=log_file)

        obj = out / "mesh_ar.obj"
        convert_textured_ply(textured / "mesh.ply", "texture_ar.jpg", obj,
                             flip_v=cfg["export"]["flip_v"])
        image = cv2.imread(str(textured / "texture.png"))
        if image is None:
            raise RuntimeError(f"Could not read texture image {textured / 'texture.png'}")
        height, width = image.shape[:2]
        factor = min(1.0, ar["texture_px"] / max(height, width))
        if factor < 1.0:
            image = cv2.resize(image, (int(width * factor), int(height * factor)),
                               interpolation=cv2.INTER_AREA)
        if not cv2.imwrite(str(out / "texture_ar.jpg"), image,
                           [cv2.IMWRITE_JPEG_QUALITY, int(ar["jpeg_quality"])]):
            raise RuntimeError(f"Could not write texture image {out / 'texture_ar.jpg'}")
        shutil.rmtree(textured)

        images_txt = reconstruction_dir / "best_model_txt" / "images.txt"
        up, coherence, camera_count = estimate_up(images_txt)
        info = orient_obj(obj, up, ar.get("scale_factor"))

        script = Path(__file__).resolve().parents[1] / "validation" / "ar_export.py"
        run([cfg["blender"]["binary"], "-b", "--factory-startup", "--python", script, "--",
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
