from pathlib import Path
from src.cyclone_scan.config import ScanConfig


def test_scan_config_default_paths(tmp_path: Path) -> None:
    config = ScanConfig(
        project_root=tmp_path,
        colmap_executable=Path("COLMAP.bat"),
        run_name="my-run",
    )

    assert config.image_dir == tmp_path / "data" / "input"
    assert config.run_dir == tmp_path / "data" / "runs" / "my-run"
    assert config.database_path == config.run_dir / "database.db"
    assert config.sparse_dir == config.run_dir / "sparse"
    assert config.dense_dir == config.run_dir / "dense"
    assert config.textured_dir == config.dense_dir / "textured"
    assert config.textured_mesh == config.textured_dir / "mesh.ply"
    assert config.texture_atlas == config.textured_dir / "texture.png"
    assert config.web_dir == config.run_dir / "web"
    assert config.final_glb == config.web_dir / "model.glb"


def test_scan_config_custom_input_dir(tmp_path: Path) -> None:
    custom_input = tmp_path / "custom_images"
    config = ScanConfig(
        project_root=tmp_path,
        colmap_executable=Path("COLMAP.bat"),
        input_dir=custom_input,
    )
    assert config.image_dir == custom_input


def test_scan_config_prepare_directories(tmp_path: Path) -> None:
    config = ScanConfig(
        project_root=tmp_path,
        colmap_executable=Path("COLMAP.bat"),
        run_name="prep-test",
    )
    config.prepare_directories()

    assert config.image_dir.is_dir()
    assert config.run_dir.is_dir()
    assert config.sparse_dir.is_dir()
    assert config.dense_dir.is_dir()
    assert config.textured_dir.is_dir()
    assert config.web_dir.is_dir()
