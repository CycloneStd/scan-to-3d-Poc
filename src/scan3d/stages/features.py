from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from ..pipeline import Context, Stage
from ..utils import colmap as cm
from ..utils.proc import run


def db_stats(db: Path) -> dict:
    try:
        con = sqlite3.connect(db)
        try:
            q = lambda sql: con.execute(sql).fetchone()[0]
            return {
                "images": q("SELECT COUNT(*) FROM images"),
                "cameras": q("SELECT COUNT(*) FROM cameras"),
                "keypoints_total": q("SELECT COALESCE(SUM(rows), 0) FROM keypoints"),
                "verified_pairs": q("SELECT COUNT(*) FROM two_view_geometries WHERE rows > 0"),
            }
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"error": str(exc)}


def effective_matcher(cfg: dict) -> str:
    m = cfg["features"]["matcher"]
    if m == "auto":
        video_only = not cfg["inputs"].get("photos_dir") and bool(cfg["inputs"].get("videos"))
        return "sequential" if video_only else "exhaustive"
    if m not in ("exhaustive", "sequential"):
        raise ValueError("features.matcher must be auto, exhaustive or sequential")
    return m


class FeaturesStage(Stage):
    name = "features"
    dir_name = "03_features"
    requires = ("validate",)

    def config_slice(self, cfg):
        base = {k: v for k, v in cfg["features"].items() if k not in ("matcher", "sequential_overlap")}
        matcher = effective_matcher(cfg)
        if matcher != "exhaustive":
            base["matcher"] = matcher
            base["sequential_overlap"] = cfg["features"]["sequential_overlap"]
        return {"features": base, "colmap": cm.version(cfg["colmap"]["binary"])}

    def run(self, ctx: Context) -> dict:
        cfg = ctx.cfg
        binary = cfg["colmap"]["binary"]
        use_gpu = "1" if cfg["features"]["use_gpu"] else "0"
        out = ctx.run.stage_dir(self.dir_name)
        db = out / "database.db"
        if db.exists():
            db.unlink()

        images_root = ctx.run.stage_dir("01_ingest") / "images"
        accepted = json.loads((ctx.run.stage_dir("02_validate") / "accepted.json").read_text())
        names = sorted(os.path.relpath(p, images_root) for paths in accepted.values() for p in paths)
        image_list = out / "image_list.txt"
        image_list.write_text("\n".join(names))

        logf = ctx.run.root / "logs" / "features.log"
        r1 = run([binary, "feature_extractor",
                  "--database_path", db, "--image_path", images_root, "--image_list_path", image_list,
                  "--ImageReader.single_camera_per_folder", "1",
                  "--ImageReader.camera_model", cfg["features"]["camera_model"],
                  cm.gpu_flag(binary, "feature_extractor", "FeatureExtraction"), use_gpu,
                  cm.option_flag(binary, "feature_extractor", "FeatureExtraction", "max_image_size"),
                  str(cfg["features"]["max_image_size"]),
                  cm.option_flag(binary, "feature_extractor", "FeatureExtraction", "num_threads"),
                  str(cfg["features"]["num_threads"])],
                 log_file=logf)

        matcher = effective_matcher(cfg)
        cmd = [binary, f"{matcher}_matcher", "--database_path", db,
               cm.gpu_flag(binary, f"{matcher}_matcher", "FeatureMatching"), use_gpu]
        if matcher == "sequential":
            opt = "--SequentialMatching.overlap"
            if opt not in cm.help_text(binary, "sequential_matcher"):
                raise RuntimeError("sequential_matcher has no SequentialMatching.overlap option; "
                                   "paste the output of `colmap sequential_matcher -h`")
            cmd += [opt, cfg["features"]["sequential_overlap"]]
        r2 = run(cmd, log_file=logf)
        return {"db": db_stats(db), "matcher": matcher, "extract_seconds": r1.seconds,
                "match_seconds": r2.seconds, "peak_children_rss_mb": r2.peak_children_rss_mb}
