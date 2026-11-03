from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2

from ..pipeline import Context, Stage
from ..project import files_signature
from ..utils.proc import run

IMAGE_EXT = {".jpg", ".jpeg", ".png"}


def _photos(cfg: dict) -> list[Path]:
    raw = cfg["inputs"].get("photos_dir")
    if not raw:
        return []
    d = Path(raw)
    return sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXT) if d.is_dir() else []


def _videos(cfg: dict) -> list[Path]:
    return [Path(v) for v in cfg["inputs"].get("videos") or []]


def keep_sharpest(gdir: Path, window: int) -> None:
    files = sorted(gdir.glob("*.jpg"))
    for i in range(0, len(files), window):
        chunk = files[i:i + window]
        scores = []
        for f in chunk:
            gray = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            scores.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()) if gray is not None else -1.0)
        best = max(range(len(chunk)), key=scores.__getitem__)
        for j, f in enumerate(chunk):
            if j != best:
                f.unlink()


class IngestStage(Stage):
    name = "ingest"
    dir_name = "01_ingest"

    def config_slice(self, cfg):
        video = {k: v for k, v in cfg["video"].items() if k not in ("select", "oversample")}
        if _videos(cfg):
            video["select"] = cfg["video"]["select"]
            video["oversample"] = cfg["video"]["oversample"]
        return {"inputs": cfg["inputs"], "video": video}

    def input_signature(self, ctx):
        return files_signature(_photos(ctx.cfg) + _videos(ctx.cfg))

    def run(self, ctx: Context) -> dict:
        out = ctx.run.stage_dir(self.dir_name)
        images = out / "images"
        if images.exists():
            shutil.rmtree(images)
        groups: dict[str, list[str]] = {}

        photos = _photos(ctx.cfg)
        if photos:
            gdir = images / "photos"
            gdir.mkdir(parents=True)
            for p in photos:
                (gdir / p.name).symlink_to(p.resolve())
            groups["photos"] = [f"images/photos/{p.name}" for p in photos]

        vcfg = ctx.cfg["video"]
        sharpest = vcfg.get("select", "sharpest") == "sharpest"
        over = int(vcfg.get("oversample", 3)) if sharpest else 1
        for v in _videos(ctx.cfg):
            group = f"video_{v.stem}"
            gdir = images / group
            gdir.mkdir(parents=True)
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", v, "-vf",
                 f"fps={vcfg['fps'] * over}", "-q:v", vcfg["jpeg_quality"], gdir / f"{v.stem}_%05d.jpg"],
                log_file=ctx.run.root / "logs" / "ingest_ffmpeg.log")
            if over > 1:
                keep_sharpest(gdir, over)
            groups[group] = sorted(f"images/{group}/{f.name}" for f in gdir.glob("*.jpg"))

        (out / "ingest.json").write_text(json.dumps({"groups": groups}, indent=2))
        return {"groups": {g: len(f) for g, f in groups.items()}, "total_images": sum(map(len, groups.values()))}