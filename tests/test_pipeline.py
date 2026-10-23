
from pathlib import Path

import pytest

from src.cyclone_scan.config import ScanConfig
from src.cyclone_scan.pipeline import ReconstructionPipeline


def create_pipeline(tmp_path: Path) -> ReconstructionPipeline:
    config = ScanConfig(
        project_root=tmp_path,
        colmap_executable=Path("COLMAP.bat"),
    )

    config.image_dir.mkdir(parents=True)
    return ReconstructionPipeline(config)


def test_rejects_insufficient_images(tmp_path: Path) -> None:
    pipeline = create_pipeline(tmp_path)

    with pytest.raises(ValueError, match="At least two"):
        pipeline.validate_inputs()
