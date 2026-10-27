from dataclasses import dataclass
import json
import math
from pathlib import Path

try:
    import cv2
except ImportError:  # OpenCV is optional for still-image reconstruction.
    cv2 = None


@dataclass(frozen=True)
class VideoPreprocessingConfig:
    target_fps: float = 3.0
    max_dimension: int = 1920
    image_format: str = "jpg"
    jpeg_quality: int = 95
    overwrite: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(self.target_fps) or self.target_fps <= 0:
            raise ValueError("target_fps must be a finite positive number")
        if self.max_dimension <= 0:
            raise ValueError("max_dimension must be positive")
        image_format = self.image_format.lower().lstrip(".")
        if image_format not in {"jpg", "jpeg", "png", "bmp", "tif", "tiff"}:
            raise ValueError(f"Unsupported image format: {self.image_format}")
        if not 0 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 0 and 100")
        object.__setattr__(self, "image_format", image_format)


@dataclass(frozen=True)
class VideoPreprocessingReport:
    input_video: Path
    output_dir: Path
    extracted_frames: int
    effective_fps: float
    source_fps: float | None
    source_frame_count: int | None
    source_dimensions: tuple[int, int]
    output_dimensions: tuple[int, int]
    frame_paths: tuple[Path, ...]


class VideoPreprocessor:
    def __init__(self, config: VideoPreprocessingConfig | None = None) -> None:
        self.config = config or VideoPreprocessingConfig()

    def extract(
        self, input_video: Path, output_dir: Path
    ) -> VideoPreprocessingReport:
        if cv2 is None:
            raise RuntimeError(
                "OpenCV is required for video preprocessing. "
                "Install the project's environment dependencies."
            )

        input_video = Path(input_video)
        output_dir = Path(output_dir)
        if not input_video.is_file():
            raise FileNotFoundError(f"Input video does not exist: {input_video}")

        extension = self.config.image_format
        if extension == "jpeg":
            extension = "jpg"
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "video_preprocessing.json"
        supported_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        unrelated_images = [
            path
            for path in output_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in supported_extensions
            and not path.name.startswith("frame_")
        ]
        if unrelated_images:
            raise FileExistsError(
                f"Output directory contains non-generated images: "
                f"{', '.join(str(path) for path in unrelated_images)}"
            )
        existing_frames = sorted(
            path
            for path in output_dir.glob("frame_*")
            if path.is_file() and path.suffix.lower() in supported_extensions
        )
        source_stat = input_video.stat()
        expected_manifest = {
            "input_video": str(input_video.resolve()),
            "input_size": source_stat.st_size,
            "input_mtime_ns": source_stat.st_mtime_ns,
            "target_fps": self.config.target_fps,
            "max_dimension": self.config.max_dimension,
            "image_format": self.config.image_format,
            "jpeg_quality": self.config.jpeg_quality,
        }
        if existing_frames and not self.config.overwrite and manifest_path.is_file():
            saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if all(
                saved_manifest.get(key) == value
                for key, value in expected_manifest.items()
            ):
                first_frame = cv2.imread(str(existing_frames[0]))
                if (
                    first_frame is not None
                    and all(frame.stat().st_size > 0 for frame in existing_frames)
                ):
                    if len(existing_frames) != int(saved_manifest["extracted_frames"]):
                        raise RuntimeError(
                            "Saved preprocessing manifest does not match the "
                            "frames present in the output directory."
                        )
                    return VideoPreprocessingReport(
                        input_video=input_video,
                        output_dir=output_dir,
                        extracted_frames=len(existing_frames),
                        effective_fps=float(saved_manifest["effective_fps"]),
                        source_fps=saved_manifest["source_fps"],
                        source_frame_count=saved_manifest["source_frame_count"],
                        source_dimensions=tuple(saved_manifest["source_dimensions"]),
                        output_dimensions=tuple(saved_manifest["output_dimensions"]),
                        frame_paths=tuple(existing_frames),
                    )
        if existing_frames and not self.config.overwrite:
            raise FileExistsError(
                f"Extracted frames already exist in {output_dir}; "
                "use overwrite=True to replace generated frames."
            )
        capture = cv2.VideoCapture(str(input_video))
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Unable to open input video: {input_video}")

        source_fps_value = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(source_fps_value) or source_fps_value < 0:
            capture.release()
            raise ValueError(
                f"Video reports an invalid FPS value: {source_fps_value}"
            )
        source_fps = source_fps_value if source_fps_value > 0 else None
        source_frame_count_value = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        source_frame_count = (
            int(source_frame_count_value)
            if math.isfinite(source_frame_count_value)
            and source_frame_count_value > 0
            else None
        )
        dimensions = [
            float(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            float(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        ]
        source_width, source_height = (
            int(value) if math.isfinite(value) and value > 0 else 0
            for value in dimensions
        )

        for frame_path in existing_frames:
            frame_path.unlink()
        if manifest_path.exists() and self.config.overwrite:
            manifest_path.unlink()

        saved_paths: list[Path] = []
        selected_times: list[float] = []
        output_dimensions = (0, 0)
        observed_source_dimensions = (source_width, source_height)
        next_sample_time = 0.0
        frame_index = 0
        last_timestamp: float | None = None
        frame_interval = 1.0 / self.config.target_fps
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break

                timestamp_ms = float(capture.get(cv2.CAP_PROP_POS_MSEC))
                timestamp = timestamp_ms / 1000.0
                if (
                    not math.isfinite(timestamp)
                    or timestamp < 0
                    or (last_timestamp is not None and timestamp <= last_timestamp)
                ):
                    if source_fps is None:
                        raise RuntimeError(
                            "Video has no usable timestamps or FPS metadata; "
                            "cannot sample frames reliably."
                        )
                    timestamp = frame_index / source_fps
                last_timestamp = timestamp

                if timestamp + 1e-9 >= next_sample_time:
                    height, width = frame.shape[:2]
                    if (
                        observed_source_dimensions[0] <= 0
                        or observed_source_dimensions[1] <= 0
                    ):
                        observed_source_dimensions = (width, height)
                    scale = min(1.0, self.config.max_dimension / max(width, height))
                    if scale < 1.0:
                        frame = cv2.resize(
                            frame,
                            (round(width * scale), round(height * scale)),
                            interpolation=cv2.INTER_AREA,
                        )

                    frame_path = output_dir / (
                        f"frame_{len(saved_paths):06d}.{extension}"
                    )
                    parameters = []
                    if extension in {"jpg", "jpeg"}:
                        parameters = [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality]
                    if not cv2.imwrite(str(frame_path), frame, parameters):
                        raise RuntimeError(f"Failed to write extracted frame: {frame_path}")
                    saved_paths.append(frame_path)
                    selected_times.append(timestamp)
                    output_dimensions = (int(frame.shape[1]), int(frame.shape[0]))
                    while next_sample_time <= timestamp + 1e-9:
                        next_sample_time += frame_interval

                frame_index += 1
        finally:
            capture.release()

        if not saved_paths:
            raise RuntimeError(f"No frames were extracted from {input_video}")

        elapsed = selected_times[-1] - selected_times[0]
        effective_fps = (
            (len(selected_times) - 1) / elapsed if elapsed > 0 else 0.0
        )
        if source_width <= 0 or source_height <= 0:
            source_width, source_height = observed_source_dimensions

        report = VideoPreprocessingReport(
            input_video=input_video,
            output_dir=output_dir,
            extracted_frames=len(saved_paths),
            effective_fps=effective_fps,
            source_fps=source_fps,
            source_frame_count=source_frame_count,
            source_dimensions=(source_width, source_height),
            output_dimensions=output_dimensions,
            frame_paths=tuple(saved_paths),
        )
        manifest = {
            **expected_manifest,
            "extracted_frames": report.extracted_frames,
            "effective_fps": report.effective_fps,
            "source_fps": report.source_fps,
            "source_frame_count": report.source_frame_count,
            "source_dimensions": report.source_dimensions,
            "output_dimensions": report.output_dimensions,
        }
        temporary_manifest = manifest_path.with_suffix(".json.tmp")
        temporary_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_manifest.replace(manifest_path)
        return report
