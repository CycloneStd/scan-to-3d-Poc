from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

import cv2


@dataclass(frozen=True)
class VideoConfig:
    fps: float = 3.0
    max_dimension: int = 1920
    min_sharpness: float = 40.0
    jpeg_quality: int = 95
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"

    def __post_init__(self) -> None:
        if not math.isfinite(self.fps) or self.fps <= 0:
            raise ValueError("fps must be a finite positive number")
        if self.max_dimension <= 0:
            raise ValueError("max_dimension must be positive")
        if not math.isfinite(self.min_sharpness) or self.min_sharpness < 0:
            raise ValueError("min_sharpness must be finite and non-negative")
        if not 0 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 0 and 100")


def _resolve(executable: str) -> str:
    found = shutil.which(executable)
    if found:
        return found
    if Path(executable).is_file():
        return str(Path(executable).resolve())
    raise FileNotFoundError(f"Required executable was not found: {executable}")


def _run(command: list[str], description: str) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(
            f"{description} failed with exit code {result.returncode}:\n"
            f"{result.stderr.strip()}"
        )
    return result


def _signature(video: Path, config: VideoConfig) -> dict:
    stat = video.stat()
    return {
        "video": str(video.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "fps": config.fps,
        "max_dimension": config.max_dimension,
        "min_sharpness": config.min_sharpness,
        "jpeg_quality": config.jpeg_quality,
    }


def extract_video(video: Path, output: Path, config: VideoConfig) -> dict:
    video = Path(video)
    output = Path(output)
    if not video.is_file():
        raise FileNotFoundError(f"Video does not exist: {video}")
    output.mkdir(parents=True, exist_ok=True)

    ffmpeg, ffprobe = _resolve(config.ffmpeg), _resolve(config.ffprobe)
    expected = _signature(video, config)
    manifest_path = output / "video_manifest.json"
    existing = sorted(output.glob("frame_*.jpg"))
    other_images = [
        path for path in output.iterdir()
        if path.is_file()
        and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        and not path.name.startswith("frame_")
    ]
    if other_images:
        raise FileExistsError(
            "The run image directory contains non-pipeline images: "
            + ", ".join(str(path) for path in other_images)
        )

    if manifest_path.is_file():
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        records = saved.get("frames", [])
        if (
            all(saved.get(key) == value for key, value in expected.items())
            and len(existing) == len(records)
            and all(
                record.get("name") == path.name
                and record.get("size") == path.stat().st_size
                and record.get("mtime_ns") == path.stat().st_mtime_ns
                for path, record in zip(existing, records)
            )
        ):
            for path in existing:
                frame = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if frame is None or cv2.Laplacian(frame, cv2.CV_64F).var() < config.min_sharpness:
                    break
            else:
                return {
                    "frames": len(existing),
                    "dropped_blurry": saved["dropped_blurry"],
                    "dimensions": saved["dimensions"],
                    "reused": True,
                }
    if existing:
        raise FileExistsError(
            f"Video frames already exist in {output} but do not match the input "
            "or manifest. Use a new --run-name."
        )

    probe = _run(
        [
            ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", str(video),
        ],
        "FFprobe",
    )
    streams = json.loads(probe.stdout).get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream was found in {video}")
    width, height = int(streams[0]["width"]), int(streams[0]["height"])
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid source video dimensions: {width}x{height}")
    scale = min(1.0, config.max_dimension / max(width, height))
    dimensions = (max(1, round(width * scale)), max(1, round(height * scale)))

    with tempfile.TemporaryDirectory(
        prefix="splat-frames-", dir=str(output.parent)
    ) as temporary:
        pattern = Path(temporary) / "frame_%06d.jpg"
        _run(
            [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                "-i", str(video),
                "-vf",
                f"fps={config.fps},scale={dimensions[0]}:{dimensions[1]}:flags=lanczos",
                "-q:v", str(max(2, round((100 - config.jpeg_quality) / 5))),
                "-start_number", "0", "-y", str(pattern),
            ],
            "FFmpeg",
        )
        candidates = sorted(Path(temporary).glob("frame_*.jpg"))
        accepted: list[Path] = []
        sharpness_scores: list[float] = []
        for path in candidates:
            frame = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if frame is None:
                raise RuntimeError(f"Could not read extracted frame: {path}")
            sharpness = float(cv2.Laplacian(frame, cv2.CV_64F).var())
            if sharpness >= config.min_sharpness:
                accepted.append(path)
                sharpness_scores.append(sharpness)
        if len(accepted) < 2:
            raise RuntimeError(
                f"Only {len(accepted)} sharp frames remained from {len(candidates)}. "
                "Lower --min-sharpness or provide a clearer/longer video."
            )
        destinations = []
        for index, source in enumerate(accepted):
            destination = output / f"frame_{index:06d}.jpg"
            shutil.move(str(source), str(destination))
            destinations.append(destination)

    if any(path.stat().st_size == 0 for path in destinations):
        raise RuntimeError("FFmpeg produced an empty frame.")
    manifest = {
        **expected,
        "dimensions": dimensions,
        "dropped_blurry": len(candidates) - len(accepted),
        "frames": [
            {
                "name": path.name,
                "size": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
                "sharpness": round(score, 3),
            }
            for path, score in zip(destinations, sharpness_scores)
        ],
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary_manifest.replace(manifest_path)
    return {
        "frames": len(destinations),
        "dropped_blurry": len(candidates) - len(accepted),
        "dimensions": dimensions,
        "reused": False,
    }
