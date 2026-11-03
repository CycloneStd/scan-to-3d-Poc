from __future__ import annotations
import shutil

from ..pipeline import Context,Stage
from ..remote.bundle import pack, unpack
from ..remote.roundtrip import roundtrip
from .dense import make_upload_workspace


class SplatStage(Stage):
    name =" splat"
    dir_name ="09_splat"
    requires = ("undistort",)

    def config_slice(self, cfg):
        return {"splat": cfg["splat"], "gpu": cfg["remote"].get("gpu")}

    def run(self,ctx:Context)-> dict:
        sc = ctx.cfg["splat"]
        out = ctx.run.stage_dir(self.dir_name)
        ws = ctx.run.stage_dir("05_ndistort")/"workspace"
        staged = out/"upload_ws"/"workspace"
        make_upload_workspace(ws, staged, int(sc["upload_jpeg_quality"]))
        tar = out/"workspace.tar.gz"
        digest = pack({"workspace": staged}, tar)
        shutil.rmtree(out/ "upload_ws",ignore_errors=True)

        data, result_tar = roundtrip(
            ctx.cfg, out, tar, digest,
            {"action": "splat", "max_steps": int(sc["max_steps"]), "data_factor": int(sc["data_factor"]),
             "compress": list(sc["compress"]), "download_ply": bool(sc["download_ply"])},
            "splat_result.part")
        unpack(result_tar, out)

        files_mb = {p.name: round(p.stat().st_size / 1e6, 2) for p in sorted(out.iterdir())
                    if p.is_file() and p.suffix in (".ply", ".spz", ".sog")}

        return {k: data.get(k) for k in ("psnr", "ssim", "lpips", "num_gaussians", "seconds_install",
                                        "seconds_train", "compress", "gsplat_version", "torch", "gpu")} | {
            "max_steps": sc["max_steps"], "files_mb": files_mb}