import logging
from types import SimpleNamespace

import pytest

from scan3d.stages.ingest import IngestStage


def _context(tmp_path, photos_dir):
    root = tmp_path / "run"
    output = root / "01_ingest"
    root.mkdir()
    return SimpleNamespace(
        cfg={"inputs": {"photos_dir": str(photos_dir), "videos": []}, "video": {}},
        run=SimpleNamespace(root=root, stage_dir=lambda _: output),
    ), output


def test_ingest_reports_heic_when_no_usable_images(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "IMG_1234.HEIC").touch()
    (photos / "IMG_1235.heif").touch()
    ctx, output = _context(tmp_path, photos)

    with pytest.raises(RuntimeError, match="No usable images found.*There are 2 HEIC files"):
        IngestStage().run(ctx)

    assert not (output / "ingest.json").exists()


def test_ingest_warns_about_ignored_heic_when_jpg_is_present(tmp_path, caplog):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "photo.jpg").touch()
    (photos / "photo.heic").touch()
    ctx, _ = _context(tmp_path, photos)

    with caplog.at_level(logging.WARNING, logger="scan3d.ingest"):
        result = IngestStage().run(ctx)

    assert result["total_images"] == 1
    assert "1 HEIC files are being ignored" in caplog.text
