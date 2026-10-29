import json
from pathlib import Path
import struct
import sqlite3
from unittest.mock import Mock

import pytest

from src.splat_reconstruction.pipeline import PipelineConfig, SplatPipeline


def create_config(tmp_path: Path, source: Path | None = None, **kwargs) -> PipelineConfig:
    source = source or tmp_path / "source"
    return PipelineConfig(
        project_dir=tmp_path / "runs",
        run_name=kwargs.pop("run_name", "test-run"),
        colmap="colmap",
        gsplat_trainer=tmp_path / "gsplat" / "examples" / "simple_trainer.py",
        input_dir=source,
        **kwargs,
    )


def test_pipeline_config_requires_one_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        PipelineConfig(
            project_dir=tmp_path,
            run_name="run",
            colmap="colmap",
            gsplat_trainer=tmp_path / "trainer.py",
        )


@pytest.mark.parametrize(
    "values",
    [
        {"mapper": "unknown"},
        {"matching": "invalid"},
        {"steps": 0},
        {"run_name": "../outside"},
    ],
)
def test_pipeline_config_rejects_bad_options(tmp_path: Path, values: dict) -> None:
    values = values.copy()
    if "steps" in values:
        values["max_steps"] = values.pop("steps")
    with pytest.raises(ValueError):
        create_config(tmp_path, **values)


def test_headless_subprocess_environment_removes_opencv_qt_paths(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM_PLUGIN_PATH", "/opencv/qt/plugins")
    monkeypatch.setenv("QT_QPA_FONTDIR", "/opencv/qt/fonts")
    monkeypatch.setenv("KEEP_ME", "value")

    environment = SplatPipeline._headless_subprocess_environment()

    assert "QT_QPA_PLATFORM_PLUGIN_PATH" not in environment
    assert "QT_QPA_FONTDIR" not in environment
    assert environment["KEEP_ME"] == "value"


def test_image_input_stages_reuses_and_rejects_mixed_inputs(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "photo-a.jpg").write_bytes(b"first")
    (source / "photo-b.png").write_bytes(b"second")
    pipeline = SplatPipeline(create_config(tmp_path, source))

    metrics = pipeline._stage_input()
    assert metrics["images"] == 2
    assert [path.name for path in pipeline._image_files(pipeline.config.image_dir)] == [
        "image_000000.jpg",
        "image_000001.png",
    ]
    assert pipeline._stage_input()["images"] == 2

    (source / "photo-a.jpg").write_bytes(b"changed")
    with pytest.raises(FileExistsError, match="different source images"):
        pipeline._stage_input()


def test_image_input_requires_two_images(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.jpg").write_bytes(b"image")
    with pytest.raises(ValueError, match="At least two"):
        SplatPipeline(create_config(tmp_path, source))._stage_input()


def test_stage_records_failure_and_refuses_incomplete_outputs(tmp_path: Path) -> None:
    pipeline = SplatPipeline(create_config(tmp_path))
    output = pipeline.config.run_dir / "partial"
    output.write_text("partial", encoding="utf-8")
    with pytest.raises(FileExistsError, match="incomplete output"):
        pipeline._stage("sparse_mapping", "sig", lambda: False, Mock(), [output])

    output.unlink()
    with pytest.raises(RuntimeError, match="expected failure"):
        pipeline._stage(
            "feature_extraction",
            "sig",
            lambda: False,
            lambda: (_ for _ in ()).throw(RuntimeError("expected failure")),
            [],
        )
    assert pipeline.metadata["stages"]["feature_extraction"]["status"] == "failed"


def test_sparse_model_selects_largest_model_without_reading_whole_cloud(
    tmp_path: Path,
) -> None:
    pipeline = SplatPipeline(create_config(tmp_path))
    for name, count in (("0", 2), ("1", 10)):
        model = pipeline.config.sparse_dir / name
        model.mkdir(parents=True)
        for file in ("cameras.bin", "images.bin"):
            (model / file).write_bytes(struct.pack("<Q", 1))
        (model / "points3D.bin").write_bytes(struct.pack("<Q", count) + b"x" * 100)

    assert pipeline._sparse_models()[0].name == "1"


def test_database_counts_include_verified_match_table(tmp_path: Path) -> None:
    pipeline = SplatPipeline(create_config(tmp_path))
    pipeline.config.run_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(pipeline.config.database) as database:
        database.executescript(
            "CREATE TABLE images (image_id INTEGER);"
            "CREATE TABLE keypoints (image_id INTEGER, rows INTEGER);"
            "CREATE TABLE two_view_geometries (pair_id INTEGER, rows INTEGER, cols INTEGER);"
            "INSERT INTO images VALUES (1), (2);"
            "INSERT INTO keypoints VALUES (1, 120), (2, 100);"
            "INSERT INTO two_view_geometries VALUES (1, 15, 2);"
        )
    assert pipeline._database_counts() == (2, 2, 1)


@pytest.mark.parametrize(
    "gpu_flag",
    ["--FeatureExtraction.use_gpu", "--SiftExtraction.use_gpu"],
)
def test_feature_extraction_disables_gpu_by_default(
    tmp_path: Path, monkeypatch, gpu_flag: str
) -> None:
    pipeline = SplatPipeline(create_config(tmp_path))
    command = []

    monkeypatch.setattr(
        pipeline,
        "_run_help",
        lambda _: (
            "--ImageReader.single_camera --FeatureExtraction.num_threads "
            f"{gpu_flag}"
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "_stage",
        lambda name, signature, valid, operation, outputs: operation(),
    )
    monkeypatch.setattr(
        pipeline,
        "_run_command",
        lambda args, stage: command.extend(args) or "",
    )

    pipeline._extract_features("image-signature")

    option_index = command.index(gpu_flag)
    assert command[option_index + 1] == "0"


def test_sparse_export_persists_ply_and_camera_text(tmp_path: Path, monkeypatch) -> None:
    pipeline = SplatPipeline(create_config(tmp_path))
    model = pipeline.config.sparse_dir / "0"
    model.mkdir(parents=True)

    def fake_run(command: list[str], stage: str, cwd=None) -> str:
        output_path = Path(command[command.index("--output_path") + 1])
        if command[command.index("--output_type") + 1] == "PLY":
            output_path.write_bytes(b"ply\nvalid")
        else:
            output_path.mkdir(parents=True, exist_ok=True)
            for name in ("cameras.txt", "images.txt", "points3D.txt"):
                (output_path / name).write_text("data", encoding="utf-8")
        return ""

    monkeypatch.setattr(pipeline, "_run_command", fake_run)
    cloud = pipeline._export_sparse(model, "image-signature")
    assert cloud.is_file()
    assert {
        path.name for path in (pipeline.config.run_dir / "cameras_text").iterdir()
    } == {"cameras.txt", "images.txt", "points3D.txt"}


def test_ply_search_ignores_non_ply_outputs(tmp_path: Path) -> None:
    pipeline = SplatPipeline(create_config(tmp_path))
    pipeline.config.gsplat_dir.mkdir(parents=True)
    (pipeline.config.gsplat_dir / "not-a-ply.ply").write_bytes(b"no")
    output = pipeline.config.gsplat_dir / "point_cloud.ply"
    output.write_bytes(b"ply\nbody")
    assert pipeline._ply_outputs() == [output]


def test_camera_export_metadata_is_json_serializable(tmp_path: Path) -> None:
    pipeline = SplatPipeline(create_config(tmp_path))
    pipeline.metadata["summary"] = {"path": str(pipeline.config.run_dir)}
    pipeline._write_metadata()
    loaded = json.loads(pipeline.config.metadata_path.read_text(encoding="utf-8"))
    assert loaded["summary"]["path"] == str(pipeline.config.run_dir)
