from __future__ import annotations

import json
import statistics
from pathlib import Path

import cv2

from ..pipeline import Context, Stage


def _sharpness(gray) -> float:
    scale = 1024 / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


class ValidateStage(Stage):
    name = "validate"
    dir_name = "02_validate"
    requires = ("ingest",)

    def config_slice(self, cfg):
        return cfg["validation"]

    def run(self, ctx: Context) -> dict:
        v = ctx.cfg["validation"]
        ingest_dir = ctx.run.stage_dir("01_ingest")
        groups = json.loads((ingest_dir / "ingest.json").read_text())["groups"]

        records = []
        for group, rels in groups.items():
            for rel in rels:
                path = ingest_dir / rel
                img = cv2.imread(str(path), cv2.IMREAD_COLOR)
                rec = {"path": str(path), "group": group, "flags": []}
                if img is None:
                    rec["flags"].append("unreadable")
                    records.append(rec)
                    continue
                h, w = img.shape[:2]
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                rec.update(width=w, height=h, sharpness=round(_sharpness(gray), 2),
                           brightness=round(float(gray.mean()), 1))
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
            if "sharpness" in r and r["sharpness"] < v["blur_ratio"] * medians[r["group"]]:
                r["flags"].append("blurry")

        accepted: dict[str, list[str]] = {g: [] for g in groups}
        reasons: dict[str, int] = {}
        for r in records:
            if r["flags"]:
                for f in r["flags"]:
                    reasons[f] = reasons.get(f, 0) + 1
            else:
                accepted[r["group"]].append(r["path"])

        out = ctx.run.stage_dir(self.dir_name)
        (out / "validate.json").write_text(json.dumps({"median_sharpness": medians, "images": records}, indent=2))
        (out / "accepted.json").write_text(json.dumps(accepted, indent=2))
        return {
            "total": len(records),
            "accepted": {g: len(p) for g, p in accepted.items()},
            "rejected_reasons": reasons,
            "median_sharpness": medians,
        }