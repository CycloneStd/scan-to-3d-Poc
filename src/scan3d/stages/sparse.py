from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

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


def registered_per_group(images_txt: Path) -> dict[str, int]:
    """Count registered images per top-level folder (= camera group) from COLMAP's images.txt."""
    lines = [ln for ln in images_txt.read_text().splitlines() if not ln.startswith("#")]
    counts: dict[str, int] = {}
    for ln in lines[::2]:  # every other line is an image header; the next line holds its 2D points
        if not ln.strip():
            continue
        group = ln.split()[-1].split("/")[0]
        counts[group] = counts.get(group, 0) + 1
    return counts


def gate_status(by_group: dict, min_fraction: float) -> dict:
    fractions = {g: v["registered"] / v["input"] for g, v in by_group.items() if v["input"]}
    worst = min(fractions.values()) if fractions else 0.0
    return {"min_fraction": min_fraction, "worst_group_fraction": round(worst, 3),
            "passed": worst >= min_fraction, "per_group": {g: round(f, 3) for g, f in fractions.items()}}


class SparseStage(Stage):
    name = "sparse"
    requires = ("features",)

    def config_slice(self, cfg):
        return {"sparse": cfg["sparse"], "gate": cfg["gate"], "colmap": cm.version(cfg["colmap"]["binary"])}

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
        logf = ctx.run.root / "logs" / f"sparse_{mapper}.log"
        res = run([binary, MAPPER_COMMAND[mapper], "--database_path", db,
                   "--image_path", images_root, "--output_path", models], log_file=logf)

        found = sorted(p for p in models.iterdir() if p.is_dir())
        if not found:
            raise RuntimeError("Mapper produced no model; check logs/sparse_*.log")

        model_stats = []
        for m in found:
            _, text = capture([binary, "model_analyzer", "--path", m])
            (ctx.run.root / "logs" / f"sparse_{mapper}_analyze_{m.name}.log").write_text(text)
            model_stats.append({"model": m.name, **parse_stats(text)})
        best = max(model_stats, key=_registered)

        run([binary, "model_converter", "--input_path", models / best["model"],
             "--output_path", out / "sparse.ply", "--output_type", "PLY"], log_file=logf)

        txt_dir = out / "best_model_txt"
        if txt_dir.exists():
            shutil.rmtree(txt_dir)
        txt_dir.mkdir()
        run([binary, "model_converter", "--input_path", models / best["model"],
             "--output_path", txt_dir, "--output_type", "TXT"], log_file=logf)
        by_group = registered_per_group(txt_dir / "images.txt")
        expected = ctx.manifest.get("validate")["metrics"]["accepted"]

        metrics = {
            "mapper": mapper,
            "colmap": cm.version(binary),
            "registered_by_group": {g: {"registered": by_group.get(g, 0), "input": n} for g, n in expected.items()},
            "best_model": best,
            "num_models": len(found),
            "mapper_seconds": res.seconds,
            "peak_children_rss_mb": res.peak_children_rss_mb,
        }
        gate_cfg = ctx.cfg.get("gate", {})
        metrics["gate"] = gate_status(metrics["registered_by_group"], float(gate_cfg.get("min_registered_fraction", 0.9)))
        (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
        if not metrics["gate"]["passed"] and gate_cfg.get("enforce", True):
            reg = {g: f"{v['registered']} of {v['input']}" for g, v in metrics["registered_by_group"].items()}
            raise RuntimeError(
                f"Capture quality check failed: only {reg} images could be placed in 3D "
                f"({metrics['gate']['worst_group_fraction']:.0%}, need {metrics['gate']['min_fraction']:.0%}). "
                "Common causes: too few photos, too little overlap (aim for about 70%), blurry or shiny subject, "
                "photos taken in big jumps, or files in a scrambled order. Retake the capture. "
                "To process it anyway: --set gate.enforce=false")
        return metrics
