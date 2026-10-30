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


class FeaturesStage(Stage):
    name = "features"
    dir_name = "03_features"
    requires = ("validate",)

    def config_slice(self, cfg):
        binary = cfg["colmap"]["binary"]
        return {"features": cfg["features"], "colmap": cm.version(binary)}

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
                  cm.gpu_flag(binary, "feature_extractor", "FeatureExtraction"), use_gpu],
                 log_file=logf)
        r2 = run([binary, "exhaustive_matcher", "--database_path", db,
                  cm.gpu_flag(binary, "exhaustive_matcher", "FeatureMatching"), use_gpu],
                 log_file=logf)
        return {"db": db_stats(db), "extract_seconds": r1.seconds, "match_seconds": r2.seconds,
                "peak_children_rss_mb": r2.peak_children_rss_mb}