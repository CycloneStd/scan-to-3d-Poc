from pathlib import Path
import pytest

from src.cyclone_scan.config import ScanConfig
from src.cyclone_scan.pipeline import ReconstructionPipeline

def create_pipeline(tmp_path: Path, **kwargs) -> ReconstructionPipeline:
    config = ScanConfig(
        project_root=tmp_path,
        colmap_executable=Path("COLMAP.bat"),
    )
    config.image_dir.mkdir(parents=True, exist_ok=True)
    return ReconstructionPipeline(config, **kwargs)


def test_rejects_missing_image_dir(tmp_path: Path) -> None:
    config = ScanConfig(
        project_root=tmp_path,
        colmap_executable=Path("COLMAP.bat"),
        input_dir=tmp_path / "non_existent_folder",
    )
    pipeline = ReconstructionPipeline(config)
    with pytest.raises(FileNotFoundError, match="Image directory does not exist"):
        pipeline.validate_inputs()


def test_rejects_insufficient_images(tmp_path: Path) -> None:
    pipeline = create_pipeline(tmp_path)
    with pytest.raises(ValueError, match="At least two"):
        pipeline.validate_inputs()


def test_rejects_existing_database(tmp_path: Path) -> None:
    pipeline = create_pipeline(tmp_path)
    pipeline.config.run_dir.mkdir(parents=True, exist_ok=True)
    pipeline.config.database_path.touch()

    (pipeline.config.image_dir / "image1.jpg").touch()
    (pipeline.config.image_dir / "image2.jpg").touch()

    with pytest.raises(FileExistsError, match="COLMAP database already exists"):
        pipeline.validate_inputs()


def test_allows_existing_database_with_overwrite(tmp_path: Path) -> None:
    pipeline = create_pipeline(tmp_path, overwrite=True)
    pipeline.config.run_dir.mkdir(parents=True, exist_ok=True)
    pipeline.config.database_path.touch()

    (pipeline.config.image_dir / "image1.jpg").touch()
    (pipeline.config.image_dir / "image2.jpg").touch()

    pipeline.validate_inputs()


def test_accepts_two_supported_images(tmp_path: Path) -> None:
    pipeline = create_pipeline(tmp_path)

    (pipeline.config.image_dir / "image1.jpg").touch()
    (pipeline.config.image_dir / "image2.png").touch()

    pipeline.validate_inputs()


def test_verify_reconstruction_finds_best_model(tmp_path: Path) -> None:
    pipeline = create_pipeline(tmp_path)
    sparse_dir = pipeline.config.sparse_dir

    model0 = sparse_dir / "0"
    model0.mkdir(parents=True)
    (model0 / "cameras.bin").touch()
    (model0 / "images.bin").touch()
    pts0 = model0 / "points3D.bin"
    pts0.write_bytes(b"small")

    model1 = sparse_dir / "1"
    model1.mkdir(parents=True)
    (model1 / "cameras.bin").touch()
    (model1 / "images.bin").touch()
    pts1 = model1 / "points3D.bin"
    pts1.write_bytes(b"large_model_points_data_here")

    best = pipeline.verify_reconstruction()
    assert best == model1