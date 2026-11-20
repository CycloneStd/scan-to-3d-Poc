from __future__ import annotations

import json
import statistics
from pathlib import Path

import numpy as np
from PIL import Image

from ..pipeline import Context, Stage


from ..utils.image import grayscale_preview, sharpness


class ValidateStage(Stage):
    name = "validate"
    dir_name = "02_validate"
    requires = ("ingest",)

    def config_slice(self, cfg):
        return {"policy": 2, **cfg["validation"]}

    def run(self, ctx: Context) -> dict:
        v = ctx.cfg["validation"]
        ingest_dir = ctx.run.stage_dir("01_ingest")
        groups = json.loads((ingest_dir / "ingest.json").read_text())["groups"]

        records = []
        for group, rels in groups.items():
            for rel in rels:
                path = ingest_dir / rel
                rec = {"path": str(path), "group": group, "flags": []}
                try:
                    (w, h), gray = grayscale_preview(path)
                except (OSError, ValueError, Image.DecompressionBombError):
                    rec["flags"].append("unreadable")
                    records.append(rec)
                    continue
                rec.update(width=w, height=h, sharpness=round(sharpness(gray), 2),
                           brightness=round(float(gray.mean()), 1))
                rec["clipped_fraction"] = round(float(np.mean((gray <= 3) | (gray >= 252))), 3)
                if rec["clipped_fraction"] > 0.65:
                    rec["flags"].append("clipped")
                if min(w, h) < v["min_short_side"]:
                    rec["flags"].append("low_resolution")
                if not v["min_brightness"] <= rec["brightness"] <= v["max_brightness"]:
                    rec["flags"].append("bad_exposure")
                records.append(rec)

        medians = {}
        for g in groups:
            vals = [r["sharpness"] for r in records if r["group"] == g and "sharpness" in r]
            medians[g] = statistics.median(vals) if vals else 0.0
        for r in records:
            if "sharpness" in r and r["sharpness"] < max(v.get("min_sharpness", 4.0), v["blur_ratio"] * medians[r["group"]]):
                r["flags"].append("blurry")

        accepted: dict[str, list[str]] = {g: [] for g in groups}
        reasons: dict[str, int] = {}
        for r in records:
            if r["flags"]:
                for f in r["flags"]:
                    reasons[f] = reasons.get(f, 0) + 1
            if "unreadable" not in r["flags"]:
                accepted[r["group"]].append(r["path"])

        if sum(map(len, accepted.values())) < 2:
            raise RuntimeError("Reconstruction needs at least two readable overlapping views from different positions.")
        out = ctx.run.stage_dir(self.dir_name)
        (out / "validate.json").write_text(json.dumps({"median_sharpness": medians, "images": records}, indent=2))
        (out / "accepted.json").write_text(json.dumps(accepted, indent=2))
        return {
            "total": len(records),
            "accepted": {g: len(p) for g, p in accepted.items()},
            "quality_flags": reasons,
            "median_sharpness": medians,
        }