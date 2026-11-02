from __future__ import annotations

import json
import shutil
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
            if p.is_file() and p.name != "meshed-poisson.ply":   # full-resolution mesh stays in 07_mesh
                dest = exports / p.relative_to(mesh_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)

        conversion = None
        tex_ply = exports / "textured" / "mesh.ply"
        tex_png = exports / "textured" / "texture.png"
        if tex_ply.exists() and tex_png.exists():
            conversion = convert_textured_ply(tex_ply, tex_png.name, exports / "textured" / "model.obj",
                                              flip_v=ctx.cfg["export"]["flip_v"])

        obj = exports / "textured" / "model.obj"
        simplified = exports / "meshed-simplified.ply"
        src = obj if obj.exists() else simplified if simplified.exists() else mesh_dir / "meshed-poisson.ply"

        script = Path(__file__).resolve().parents[1] / "validation" / "blender_check.py"
        run([ctx.cfg["blender"]["binary"], "-b", "--factory-startup", "--python", script, "--",
             "--input", src.resolve(), "--outdir", out.resolve()],
            log_file=ctx.run.root / "logs" / "export_blender.log")

        report = json.loads((out / "blender_report.json").read_text())
        report["source_mesh"] = str(src.relative_to(ctx.run.root))
        report["obj_conversion"] = conversion
        return report