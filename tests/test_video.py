from pathlib import Path

import numpy as np
import pytest

from src.cyclone_scan import video
from src.cyclone_scan.video import VideoPreprocessingConfig, VideoPreprocessor


class FakeCapture:
    def __init__(
        self,
        frames: int = 11,
        *,
        fps: float = 10.0,
        width: int = 4000,
        height: int = 2000,
        opened: bool = True,
    ) -> None:
        self.frames = frames
        self.fps = fps
        self.width = width
        self.height = height
        self.opened = opened
        self.index = -1

    def isOpened(self) -> bool:
        return self.opened

    def get(self, prop: int) -> float:
        if prop == video.cv2.CAP_PROP_FPS:
            return self.fps
        if prop == video.cv2.CAP_PROP_FRAME_WIDTH:
            return self.width
        if prop == video.cv2.CAP_PROP_FRAME_HEIGHT:
            return self.height
        if prop == video.cv2.CAP_PROP_POS_MSEC:
            return max(0, self.index) * 100.0
        return 0.0

    def read(self):
        self.index += 1
        if self.index >= self.frames:
            return False, None
        return True, np.zeros((self.height, self.width, 3), dtype=np.uint8)

    def release(self) -> None:
        pass


def create_input(tmp_path: Path) -> Path:
    path = tmp_path / "source.mp4"
    path.write_bytes(b"video")
    return path


def test_extract_samples_resizes_and_names_frames_chronologically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_input(tmp_path)
    written: list[tuple[str, tuple[int, ...]]] = []
    monkeypatch.setattr(video.cv2, "VideoCapture", lambda _path: FakeCapture())

    def write_image(path: str, frame: np.ndarray, _parameters: list[int]) -> bool:
        written.append((path, frame.shape))
        Path(path).write_bytes(b"frame")
        return True

    monkeypatch.setattr(video.cv2, "imwrite", write_image)
    report = VideoPreprocessor(
        VideoPreprocessingConfig(target_fps=2, max_dimension=1000)
    ).extract(tmp_path / "source.mp4", tmp_path / "frames")

    assert [Path(path).name for path, _ in written] == [
        "frame_000000.jpg",
        "frame_000001.jpg",
        "frame_000002.jpg",
    ]
    assert all(shape[:2] == (500, 1000) for _, shape in written)
    assert report.extracted_frames == 3
    assert report.effective_fps == pytest.approx(2.0)
    assert report.source_dimensions == (4000, 2000)
    assert report.output_dimensions == (1000, 500)


def test_missing_video_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Input video does not exist"):
        VideoPreprocessor().extract(tmp_path / "missing.mp4", tmp_path / "frames")


def test_video_open_failure_is_reported(tmp_path: Path, monkeypatch) -> None:
    video_path = create_input(tmp_path)
    monkeypatch.setattr(
        video.cv2, "VideoCapture", lambda _path: FakeCapture(opened=False)
    )

    with pytest.raises(RuntimeError, match="Unable to open input video"):
        VideoPreprocessor().extract(video_path, tmp_path / "frames")


def test_empty_video_is_reported(tmp_path: Path, monkeypatch) -> None:
    video_path = create_input(tmp_path)
    monkeypatch.setattr(
        video.cv2, "VideoCapture", lambda _path: FakeCapture(frames=0)
    )

    with pytest.raises(RuntimeError, match="No frames were extracted"):
        VideoPreprocessor().extract(video_path, tmp_path / "frames")


def test_invalid_video_fps_is_rejected(tmp_path: Path, monkeypatch) -> None:
    video_path = create_input(tmp_path)
    monkeypatch.setattr(
        video.cv2, "VideoCapture", lambda _path: FakeCapture(fps=-1)
    )

    with pytest.raises(ValueError, match="invalid FPS"):
        VideoPreprocessor().extract(video_path, tmp_path / "frames")


def test_missing_fps_uses_capture_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = create_input(tmp_path)
    monkeypatch.setattr(
        video.cv2, "VideoCapture", lambda _path: FakeCapture(fps=0)
    )
    monkeypatch.setattr(
        video.cv2, "imwrite", lambda path, _frame, _params: Path(path).write_bytes(b"x") > 0
    )

    report = VideoPreprocessor(
        VideoPreprocessingConfig(target_fps=2, max_dimension=5000)
    ).extract(video_path, tmp_path / "frames")

    assert report.source_fps is None
    assert report.extracted_frames == 3


def test_matching_preprocessing_manifest_reuses_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = create_input(tmp_path)
    output_dir = tmp_path / "frames"
    monkeypatch.setattr(video.cv2, "VideoCapture", lambda _path: FakeCapture(frames=1))
    monkeypatch.setattr(
        video.cv2,
        "imwrite",
        lambda path, _frame, _params: Path(path).write_bytes(b"frame") > 0,
    )
    monkeypatch.setattr(
        video.cv2,
        "imread",
        lambda _path: np.zeros((2, 2, 3), dtype=np.uint8),
    )
    preprocessor = VideoPreprocessor(
        VideoPreprocessingConfig(max_dimension=5000)
    )
    first_report = preprocessor.extract(video_path, output_dir)
    monkeypatch.setattr(
        video.cv2,
        "VideoCapture",
        lambda _path: pytest.fail("matching frames should be reused"),
    )

    second_report = preprocessor.extract(video_path, output_dir)

    assert second_report.frame_paths == first_report.frame_paths


def test_existing_frames_are_not_mixed_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = create_input(tmp_path)
    output_dir = tmp_path / "frames"
    output_dir.mkdir()
    (output_dir / "frame_000000.png").write_bytes(b"existing")
    monkeypatch.setattr(video.cv2, "VideoCapture", lambda _path: FakeCapture())

    with pytest.raises(FileExistsError, match="use overwrite=True"):
        VideoPreprocessor().extract(video_path, output_dir)


@pytest.mark.parametrize(
    "values",
    [
        {"target_fps": 0},
        {"target_fps": float("nan")},
        {"max_dimension": 0},
        {"jpeg_quality": 101},
        {"image_format": "webp"},
    ],
)
def test_invalid_video_configuration_is_rejected(values: dict) -> None:
    with pytest.raises(ValueError):
        VideoPreprocessingConfig(**values)
