from __future__ import annotations

import json
import re
import shutil

from ..pipeline import Context, Stage
from ..utils import colmap as cm
from ..utils.proc import capture, run

MAPPER_COMMAND = {"incremental": "mapper", "global": "global_mapper"}


def parse_stats(text: str) -> dict:
    stats = {}
    for line in text.splitlines():
        line = line.split("] ", 1)[-1].strip()
        m = re.match(r"^([A-Za-z][A-Za-z ]*?):\s*([0-9]+(?:\.[0-9]+)?)", line)
        if m:
            stats[m.group(1).strip().lower().replace(" ", "_")] = float(m.group(2))
    return stats


def _registered(stats: dict) -> float:
    return stats.get("registered_images") or stats.get("registered_frames") or 0.0


class SparseStage(Stage):
    name = "sparse"
    requires = ("features",)

    def config_slice(self, cfg):
        return {"sparse": cfg["sparse"], "colmap": cm.version(cfg["colmap"]["binary"])}

    def run(self, ctx: Context) -> dict:
        cfg = ctx.cfg
        binary = cfg["colmap"]["binary"]
        mapper = cfg["sparse"]["mapper"]
        if mapper not in MAPPER_COMMAND:
            raise ValueError(f"sparse.mapper must be one of {list(MAPPER_COMMAND)}")

        out = ctx.run.stage_dir(f"04_sparse_{mapper}")
        models = out / "models"
        if models.exists():
            shutil.rmtree(models)
        models.mkdir()

        db = ctx.run.stage_dir("03_features") / "database.db"
        images_root = ctx.run.stage_dir("01_ingest") / "images"
        res = run([binary, MAPPER_COMMAND[mapper], "--database_path", db,
                   "--image_path", images_root, "--output_path", models],
                  log_file=ctx.run.root / "logs" / f"sparse_{mapper}.log")

        found = sorted(p for p in models.iterdir() if p.is_dir())
        if not found:
            raise RuntimeError("Mapper produced no model; check logs/sparse_*.log")

        total_images = ctx.manifest.get("features")["metrics"]["db"].get("images")
        model_stats = []
        for m in found:
            _, text = capture([binary, "model_analyzer", "--path", m])
            (ctx.run.root / "logs" / f"sparse_{mapper}_analyze_{m.name}.log").write_text(text)
            model_stats.append({"model": m.name, **parse_stats(text)})
        best = max(model_stats, key=_registered)

        run([binary, "model_converter", "--input_path", models / best["model"],
             "--output_path", out / "sparse.ply", "--output_type", "PLY"],
            log_file=ctx.run.root / "logs" / f"sparse_{mapper}.log")

        metrics = {
            "mapper": mapper,
            "colmap": cm.version(binary),
            "input_images": total_images,
            "best_model": best,
            "registered_fraction": round(_registered(best) / total_images, 3) if total_images else None,
            "num_models": len(found),
            "mapper_seconds": res.seconds,
            "peak_children_rss_mb": res.peak_children_rss_mb,
        }
        (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
        return metrics