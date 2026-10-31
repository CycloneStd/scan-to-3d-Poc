from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..pipeline import Context, Stage
from ..utils.proc import run


class ExportStage(Stage):
    name = "export"
    dir_name = "08_export"
    requires = ("mesh",)

    def config_slice(self, cfg):
        return cfg["blender"]

    def run(self, ctx: Context) -> dict:
        out = ctx.run.stage_dir(self.dir_name)
        mesh_dir = ctx.run.stage_dir("07_mesh")

        exports = out / "exports"
        if exports.exists():
            shutil.rmtree(exports)
        for p in mesh_dir.rglob("*"):
            if p.is_file():
                dest = exports / p.relative_to(mesh_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)

        objs = sorted(exports.rglob("*.obj"))
        src = objs[0] if objs else exports / "meshed-poisson.ply"
        script = Path(__file__).resolve().parents[1] / "validation" / "blender_check.py"
        run([ctx.cfg["blender"]["binary"], "-b", "--factory-startup", "--python", script, "--",
             "--input", src.resolve(), "--outdir", out.resolve()],
            log_file=ctx.run.root / "logs" / "export_blender.log")

        report = json.loads((out / "blender_report.json").read_text())
        report["source_mesh"] = str(src.relative_to(ctx.run.root))
        return report