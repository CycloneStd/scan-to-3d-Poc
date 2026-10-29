import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from src.splat_reconstruction import video
from src.splat_reconstruction.video import VideoConfig, extract_video


def test_video_config_validates_sampling_settings() -> None:
    with pytest.raises(ValueError, match="fps"):
        VideoConfig(fps=0)
    with pytest.raises(ValueError, match="sharpness"):
        VideoConfig(min_sharpness=-1)


def test_extract_video_filters_blurry_frames_and_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"synthetic-video")
    sharp = np.indices((180, 320)).sum(axis=0).astype(np.uint8) % 2 * 255
    blurry = np.full((180, 320), 127, dtype=np.uint8)
    ffmpeg_calls = 0
    monkeypatch.setattr(video, "_resolve", lambda value: f"C:\\tools\\{value}.exe")

    def fake_run(command: list[str], _description: str):
        nonlocal ffmpeg_calls
        if "-show_entries" in command:
            return SimpleNamespace(
                stdout=json.dumps(
                    {"streams": [{"width": 640, "height": 360}]}
                )
            )
        ffmpeg_calls += 1
        pattern = Path(command[-1])
        for index, frame in enumerate((sharp, blurry, sharp, blurry)):
            destination = Path(
                str(pattern).replace("%06d", f"{index:06d}")
            )
            assert video.cv2.imwrite(str(destination), frame)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(video, "_run", fake_run)
    config = VideoConfig(fps=2, max_dimension=320, min_sharpness=40)

    first = extract_video(input_video, tmp_path / "frames", config)
    second = extract_video(input_video, tmp_path / "frames", config)

    assert first["frames"] == 2
    assert first["dropped_blurry"] == 2
    assert first["dimensions"] == (320, 180)
    assert second["reused"] is True
    assert ffmpeg_calls == 1


def test_extract_video_requires_at_least_two_sharp_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"synthetic-video")
    monkeypatch.setattr(video, "_resolve", lambda value: value)

    def fake_run(command: list[str], _description: str):
        if "-show_entries" in command:
            return SimpleNamespace(
                stdout=json.dumps(
                    {"streams": [{"width": 64, "height": 48}]}
                )
            )
        path = Path(command[-1].replace("%06d", "000000"))
        assert video.cv2.imwrite(str(path), np.full((48, 64), 100, dtype=np.uint8))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(video, "_run", fake_run)
    with pytest.raises(RuntimeError, match="Only 0 sharp frames"):
        extract_video(
            input_video,
            tmp_path / "frames",
            VideoConfig(fps=1, min_sharpness=40),
        )
