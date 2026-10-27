from pathlib import Path
import sqlite3
import struct
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from src.cyclone_scan.config import ScanConfig
from src.cyclone_scan import pipeline as pipeline_module
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
    (model0 / "cameras.bin").write_bytes(struct.pack("<Q", 1))
    (model0 / "images.bin").write_bytes(struct.pack("<Q", 1))
    pts0 = model0 / "points3D.bin"
    pts0.write_bytes(struct.pack("<Q", 1) + b"x")

    model1 = sparse_dir / "1"
    model1.mkdir(parents=True)
    (model1 / "cameras.bin").write_bytes(struct.pack("<Q", 1))
    (model1 / "images.bin").write_bytes(struct.pack("<Q", 1))
    pts1 = model1 / "points3D.bin"
    pts1.write_bytes(struct.pack("<Q", 2) + b"large_model_points_data_here")

    best = pipeline.verify_reconstruction()
    assert best == model1


def test_sequential_matcher_is_used_without_gpu_matching_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = create_pipeline(tmp_path)
    pipeline.config.run_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(pipeline.config.database_path) as database:
        database.executescript(
            "CREATE TABLE images (image_id INTEGER);"
            "CREATE TABLE keypoints (image_id INTEGER);"
            "CREATE TABLE matches (pair_id INTEGER);"
            "INSERT INTO images VALUES (1), (2);"
            "INSERT INTO keypoints VALUES (1), (2);"
        )
    pipeline.runner.help_text = Mock(
        return_value="--SequentialMatching.overlap"
    )

    def run(arguments: list[str], **_kwargs) -> None:
        with sqlite3.connect(pipeline.config.database_path) as database:
            database.execute("INSERT INTO matches VALUES (1)")

    pipeline.runner.run = Mock(side_effect=run)
    pipeline._match_features()

    command = pipeline.runner.run.call_args.args[0]
    assert command[0] == "sequential_matcher"
    assert "exhaustive_matcher" not in command
    assert "--FeatureMatching.use_gpu" not in command
    assert "--SequentialMatching.overlap" in command


def test_missing_openmvs_executable_is_reported(tmp_path: Path) -> None:
    pipeline = create_pipeline(tmp_path)
    with pytest.raises(RuntimeError, match="Required executable not found"):
        pipeline._run_external("missing-openmvs-tool", [])


def test_failed_external_command_includes_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = create_pipeline(tmp_path)
    executable = tmp_path / "fake-tool.exe"
    executable.touch()
    monkeypatch.setattr(
        pipeline_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=2, stdout="tool stdout", stderr="tool error"
        ),
    )

    with pytest.raises(RuntimeError, match="tool error"):
        pipeline._run_external(executable, ["--help"])


def test_unsupported_openmvs_option_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = create_pipeline(tmp_path)
    executable = tmp_path / "fake-openmvs.exe"
    executable.touch()
    monkeypatch.setattr(
        pipeline_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="--output-file", stderr=""
        ),
    )

    with pytest.raises(ValueError, match="does not advertise"):
        pipeline._validate_openmvs_options(
            executable,
            ("--output-file", "--unknown-option"),
        )


def test_missing_expected_output_is_rejected(tmp_path: Path) -> None:
    pipeline = create_pipeline(tmp_path)
    with pytest.raises(RuntimeError, match="was not produced or is empty"):
        pipeline._require_file(tmp_path / "missing.ply", "Mesh")


def test_existing_incomplete_stage_output_is_preserved(
    tmp_path: Path,
) -> None:
    pipeline = create_pipeline(tmp_path)
    output = tmp_path / "partial.mvs"
    output.write_bytes(b"partial")
    operation = Mock()

    with pytest.raises(FileExistsError, match="existing incomplete outputs"):
        pipeline._run_stage(
            "safe_stage",
            operation,
            lambda: False,
            (output,),
        )

    operation.assert_not_called()


def test_valid_stage_output_is_reused(tmp_path: Path) -> None:
    pipeline = create_pipeline(tmp_path)
    output = tmp_path / "complete.mvs"
    output.write_bytes(b"complete")
    operation = Mock()

    pipeline._run_stage(
        "resumed_stage",
        operation,
        lambda: output.is_file() and output.stat().st_size > 0,
        (output,),
    )

    operation.assert_not_called()
    assert pipeline._metadata["stages"]["resumed_stage"]["status"] == "skipped"


def test_database_without_matching_input_signature_is_not_reused(
    tmp_path: Path,
) -> None:
    pipeline = create_pipeline(tmp_path)
    (pipeline.config.image_dir / "image1.jpg").write_bytes(b"first")
    (pipeline.config.image_dir / "image2.jpg").write_bytes(b"second")
    pipeline.config.run_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(pipeline.config.database_path) as database:
        database.executescript(
            "CREATE TABLE images (image_id INTEGER);"
            "CREATE TABLE keypoints (image_id INTEGER);"
            "CREATE TABLE matches (pair_id INTEGER);"
            "INSERT INTO images VALUES (1), (2);"
            "INSERT INTO keypoints VALUES (1), (2);"
        )

    with pytest.raises(FileExistsError, match="different or unverified image set"):
        pipeline.validate_inputs()


def test_textured_obj_requires_material_and_referenced_texture(
    tmp_path: Path,
) -> None:
    pipeline = create_pipeline(tmp_path)
    pipeline.config.textured_dir.mkdir(parents=True, exist_ok=True)
    pipeline.config.textured_obj.write_text(
        "mtllib model.mtl\n", encoding="utf-8"
    )
    (pipeline.config.textured_dir / "model.mtl").write_text(
        "newmtl material\nmap_Kd atlas.png\n", encoding="utf-8"
    )
    assert not pipeline._textured_asset_is_valid()

    (pipeline.config.textured_dir / "atlas.png").write_bytes(b"texture")
    assert pipeline._textured_asset_is_valid()


def test_sparse_ply_export_is_reused_after_completion(tmp_path: Path) -> None:
    pipeline = create_pipeline(tmp_path)
    model = pipeline.config.sparse_dir / "0"
    model.mkdir(parents=True)
    (model / "cameras.bin").write_bytes(struct.pack("<Q", 1))
    (model / "images.bin").write_bytes(struct.pack("<Q", 1))
    (model / "points3D.bin").write_bytes(struct.pack("<Q", 1))

    def convert(arguments: list[str], **_kwargs) -> None:
        output_path = Path(arguments[arguments.index("--output_path") + 1])
        output_path.write_bytes(b"ply")

    pipeline.runner.run = Mock(side_effect=convert)
    pipeline._export_sparse_to_ply(model)
    pipeline._export_sparse_to_ply(model)

    assert pipeline.runner.run.call_count == 1


def test_textured_obj_bundle_exports_to_glb(tmp_path: Path) -> None:
    pytest.importorskip("trimesh")
    pipeline = create_pipeline(tmp_path)
    pipeline.config.textured_dir.mkdir(parents=True, exist_ok=True)
    pipeline.config.textured_obj.write_text(
        "mtllib model.mtl\n"
        "o triangle\n"
        "v 0 0 0\n"
        "v 1 0 0\n"
        "v 0 1 0\n"
        "vt 0 0\n"
        "vt 1 0\n"
        "vt 0 1\n"
        "vn 0 0 1\n"
        "usemtl material\n"
        "f 1/1/1 2/2/1 3/3/1\n",
        encoding="utf-8",
    )
    (pipeline.config.textured_dir / "model.mtl").write_text(
        "newmtl material\nKd 1 1 1\nmap_Kd atlas.png\n",
        encoding="utf-8",
    )
    Image.new("RGB", (2, 2), color=(255, 255, 255)).save(
        pipeline.config.textured_dir / "atlas.png"
    )

    output = pipeline._export_glb()

    assert output.is_file()
    assert output.stat().st_size > 0
    assert (pipeline.config.web_dir / "index.html").is_file()