from __future__ import annotations

import json
import shutil
from pathlib import Path

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


class IngestStage(Stage):
    name = "ingest"
    dir_name = "01_ingest"

    def config_slice(self, cfg):
        return {"inputs": cfg["inputs"], "video": cfg["video"]}

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

        fps = ctx.cfg["video"]["fps"]
        quality = ctx.cfg["video"]["jpeg_quality"]
        for v in _videos(ctx.cfg):
            group = f"video_{v.stem}"
            gdir = images / group
            gdir.mkdir(parents=True)
            # ffmpeg applies the phone's rotation metadata automatically
            run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", v, "-vf", f"fps={fps}",
                 "-q:v", quality, gdir / f"{v.stem}_%05d.jpg"],
                log_file=ctx.run.root / "logs" / "ingest_ffmpeg.log",
            )
            groups[group] = sorted(f"images/{group}/{f.name}" for f in gdir.glob("*.jpg"))

        (out / "ingest.json").write_text(json.dumps({"groups": groups}, indent=2))
        return {"groups": {g: len(f) for g, f in groups.items()}, "total_images": sum(map(len, groups.values()))}