from __future__ import annotations

from ..pipeline import Context, Stage
from ..remote.bundle import pack, unpack
from ..remote.executor import ColabExecutor
from ..utils.ply import ply_counts


class DenseStage(Stage):
    name = "dense"
    dir_name = "06_dense"
    requires = ("undistort",)

    def config_slice(self, cfg):
        return {"dense": cfg["dense"], "gpu": cfg["remote"].get("gpu")}

    def run(self, ctx: Context) -> dict:
        cfg = ctx.cfg
        out = ctx.run.stage_dir(self.dir_name)
        ws = ctx.run.stage_dir("05_undistort") / "workspace"
        tar = out / "workspace.tar.gz"
        pack({"workspace": ws}, tar)

        r = cfg["remote"]
        ex = ColabExecutor(r["session"], r.get("gpu"), r.get("high_mem", True), r.get("auth"))
        job = {"action": "dense", "workspace_tar": "/content/workspace.tar.gz",
               "colmap_specs": cfg["dense"]["colmap_specs"],
               "geom_consistency": cfg["dense"]["geom_consistency"]}
        with ex.open_session():
            result = ex.run_job(job, out / "remote", uploads={tar: "/content/workspace.tar.gz"})
            if result.get("ok"):
                ex.download("/content/dense_result.tar.gz", out / "dense_result.tar.gz")
        if not result.get("ok"):
            raise RuntimeError("Remote dense stage failed:\n" + result.get("error", "unknown error"))

        unpack(out / "dense_result.tar.gz", out)
        data = result["data"]
        return {"fused_points": ply_counts(out / "fused.ply").get("vertex"),
                "colmap_spec": data["colmap_spec"], "gpu": data["gpu"],
                "seconds_patch_match": data["seconds_patch_match"],
                "seconds_fusion": data["seconds_fusion"]}