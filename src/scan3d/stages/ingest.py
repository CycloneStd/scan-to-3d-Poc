from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from ..pipeline import Context, Stage
from ..project import files_signature, fingerprint
from ..utils.proc import run
from ..utils.image import grayscale_preview, sharpness

IMAGE_EXT = {".jpg", ".jpeg", ".png"}


def _photos(cfg: dict) -> list[Path]:
    raw = cfg["inputs"].get("photos_dir")
    if not raw:
        return []
    d = Path(raw)
    return sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXT) if d.is_dir() else []


def camera_group(path: Path) -> str:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            lens = exif.get_ifd(0x8769)
            key = [image.size, exif.get(271), exif.get(272), lens.get(42036),
                   str(lens.get(37386)), lens.get(41989), exif.get(274, 1)]
            return "photos_" + fingerprint(key)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return "photos_unknown"


def _videos(cfg: dict) -> list[Path]:
    return [Path(v) for v in cfg["inputs"].get("videos") or []]


def _frame_motion(gray, previous_gray) -> float:
    if previous_gray is None:
        return 1.0
    current = np.asarray(
        Image.fromarray(gray).resize((64, 64), Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    previous = np.asarray(
        Image.fromarray(previous_gray).resize((64, 64), Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    return float(np.abs(current - previous).mean() / 255.0)


def keep_sharpest(gdir: Path, window: int, motion_aware: bool = False) -> None:
    files = sorted(gdir.glob("*.jpg"))
    previous_gray = None
    for i in range(0, len(files), window):
        chunk = files[i:i + window]
        candidates = []
        for f in chunk:
            try:
                _, gray = grayscale_preview(f)
                candidates.append((f, max(0.0, sharpness(gray)), gray))
            except (OSError, ValueError):
                candidates.append((f, 0.0, None))

        sharpest = max((candidate[1] for candidate in candidates), default=0.0)
        scores = []
        for _, score, gray in candidates:
            if sharpest == 0:
                scores.append(-1.0)
                continue
            score /= sharpest
            if motion_aware and gray is not None:
                motion = min(1.0, _frame_motion(gray, previous_gray) / 0.2)
                score *= 0.5 + 0.5 * motion
            scores.append(score)
        best = max(range(len(candidates)), key=scores.__getitem__)
        if candidates[best][2] is not None:
            previous_gray = candidates[best][2]
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
        return {
            "camera_grouping_version": 1,
            "video_selector_version": 2,
            "inputs": cfg["inputs"],
            "video": video,
        }

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
            for p in photos:
                group = camera_group(p)
                gdir = images / group
                gdir.mkdir(parents=True, exist_ok=True)
                name = fingerprint(p.name) + p.suffix.lower() if any(c.isspace() for c in p.name) else p.name
                target = gdir / name
                try:
                    target.symlink_to(p.resolve())
                except OSError:
                    shutil.copy2(p, target)
                groups.setdefault(group, []).append(f"images/{group}/{name}")

        vcfg = ctx.cfg["video"]
        selection = vcfg.get("select", "sharpest")
        if selection not in {"sharpest", "motion_sharpest", "all"}:
            raise ValueError("video.select must be sharpest, motion_sharpest or all")
        if float(vcfg["fps"]) <= 0 or int(vcfg.get("oversample", 3)) < 1:
            raise ValueError("video.fps and video.oversample must be positive")
        sharpest = selection in {"sharpest", "motion_sharpest"}
        over = int(vcfg.get("oversample", 3)) if sharpest else 1
        for v in _videos(ctx.cfg):
            stem = fingerprint(v.name) if any(c.isspace() for c in v.stem) else v.stem
            group = f"video_{stem}"
            gdir = images / group
            gdir.mkdir(parents=True)
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", v, "-vf",
                 f"fps={vcfg['fps'] * over}", "-q:v", vcfg["jpeg_quality"], gdir / f"{stem}_%05d.jpg"],
                log_file=ctx.run.root / "logs" / "ingest_ffmpeg.log")
            if over > 1:
                keep_sharpest(gdir, over, motion_aware=selection == "motion_sharpest")
            groups[group] = sorted(f"images/{group}/{f.name}" for f in gdir.glob("*.jpg"))

        raw = ctx.cfg["inputs"].get("photos_dir")
        heic = [p for p in Path(raw).iterdir() if p.suffix.lower() in (".heic", ".heif")] if raw and Path(raw).is_dir() else []
        if not any(groups.values()):
            raise RuntimeError("No usable images found." + (
                f" There are {len(heic)} HEIC files: set the iPad to Settings > Camera > Formats > "
                "Most Compatible, or convert them to JPG." if heic else ""))
        if heic:
            logging.getLogger("scan3d.ingest").warning("%d HEIC files are being ignored", len(heic))

        (out / "ingest.json").write_text(json.dumps({"groups": groups}, indent=2))
        return {"groups": {g: len(f) for g, f in groups.items()}, "total_images": sum(map(len, groups.values()))}
