from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from ..pipeline import Context, Stage
from ..utils.ply_to_obj import convert_textured_ply
from ..utils.proc import run


class ExportStage(Stage):
    name = "export"
    dir_name = "08_export"
    requires = ("mesh",)

    def config_slice(self, cfg):
        return {"blender": cfg["blender"], "export": cfg["export"]}

    def run(self, ctx: Context) -> dict:
        out = ctx.run.stage_dir(self.dir_name)
        mesh_dir = ctx.run.stage_dir("07_mesh")

        exports = out / "exports"
        if exports.exists():
            shutil.rmtree(exports)
        for p in mesh_dir.rglob("*"):
            if p.is_file() and p.name not in {"meshed-full.ply", "meshed-poisson.ply"}:   # full-resolution mesh stays in 07_mesh
                dest = exports / p.relative_to(mesh_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)

        conversion = None
        tex_ply = exports / "textured" / "mesh.ply"
        tex_png = exports / "textured" / "texture.png"
        if tex_ply.exists() and tex_png.exists():
            conversion = convert_textured_ply(tex_ply, tex_png.name, exports / "textured" / "model.obj",
                                              flip_v=ctx.cfg["export"]["flip_v"],
                                              max_edge_factor=ctx.cfg["mesh"].get("max_edge_factor"))

        obj = exports / "textured" / "model.obj"
        if obj.exists():
            # Orient mesh upright if camera poses are available
            images_txt = ctx.run.stage_dir("06_reconstruction") / "best_model_txt" / "images.txt"
            if not images_txt.exists():
                for cand_dir in ("04_sparse_incremental", "04_sparse_hierarchical"):
                    cand = ctx.run.stage_dir(cand_dir) / "best_model_txt" / "images.txt"
                    if cand.exists():
                        images_txt = cand
                        break
            if images_txt.exists():
                try:
                    from ..ar import estimate_up, orient_obj
                    up, _, _ = estimate_up(images_txt)
                    orient_obj(obj, up, scale=None)
                except Exception:
                    pass

        if obj.exists():
            with zipfile.ZipFile(out / "model-obj.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=1) as bundle:
                for path in (obj, obj.with_suffix(".mtl"), tex_png):
                    bundle.write(path, path.name)
        simplified = exports / "meshed-simplified.ply"
        src = obj if obj.exists() else simplified if simplified.exists() else mesh_dir / "meshed-poisson.ply"

        if not src.exists():
            src = mesh_dir / "meshed-full.ply"

        script = Path(__file__).resolve().parents[1] / "validation" / "blender_check.py"
        report_path = out / "blender_report.json"
        report_path.unlink(missing_ok=True)
        run([ctx.cfg["blender"]["binary"], "-b", "--factory-startup", "--python-exit-code", "1",
             "--python", script, "--", "--input", src.resolve(), "--outdir", out.resolve()],
            log_file=ctx.run.root / "logs" / "export_blender.log")
        report = json.loads((out / "blender_report.json").read_text())
        if not report.get("faces") or not report.get("glb_bytes"):
            raise RuntimeError("Blender did not export a nonempty mesh")
        report["source_mesh"] = str(src.relative_to(ctx.run.root))
        report["obj_conversion"] = conversion
        return report