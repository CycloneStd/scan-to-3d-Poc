import hashlib
import json

import pytest

from scan3d.package import build_package


def test_build_package_copies_assets_ar_and_honest_metadata(tmp_path):
    run_dir = tmp_path / "run-1"
    splat_dir = run_dir / "09_splat"
    ar_dir = run_dir / "11_ar"
    out = tmp_path / "deliverables" / "house"
    splat_dir.mkdir(parents=True)
    ar_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({
        "stages": {"splat": {"status": "done", "metrics": {
            "num_gaussians": 1250, "max_steps": 30000, "max_image_size": 768,
            "extra_args": ["--steps_scaler", "0.25"], "psnr": 22.4, "ssim": 0.9, "lpips": 0.1,
        }}}
    }))
    asset_bytes = b"SPZ test"
    (splat_dir / "scene.spz").write_bytes(asset_bytes)
    (ar_dir / "model_ar.glb").write_bytes(b"glb")
    (ar_dir / "ar_report.json").write_text('{"scale":"UNSCALED"}')

    assert build_package(run_dir, out) == out
    package_manifest = json.loads((out / "manifest.json").read_text())
    assert (out / "scene.spz").read_bytes() == asset_bytes
    assert package_manifest["assets"]["scene.spz"] == {
        "bytes": len(asset_bytes),
        "sha256": hashlib.sha256(asset_bytes).hexdigest(),
        "first_bytes_hex": asset_bytes.hex(),
    }
    assert package_manifest["ar_files"] == ["model_ar.glb", "ar_report.json"]
    assert package_manifest["coordinate_system"]["status"] == "NOT PROVIDED"
    assert package_manifest["training"]["extra_args"] == ["--steps_scaler", "0.25"]
    assert (out / "ar" / "model_ar.glb").read_bytes() == b"glb"
    assert "orientation is not provided" in (out / "README.md").read_text()


def test_build_package_requires_completed_splat(tmp_path):
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({"stages": {}}))

    with pytest.raises(SystemExit, match="Run the splat stage to completion first"):
        build_package(run_dir, tmp_path / "package")


def test_build_package_requires_at_least_one_splat_asset(tmp_path):
    run_dir = tmp_path / "run-1"
    (run_dir / "09_splat").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "stages": {"splat": {"status": "done", "metrics": {}}}
    }))

    with pytest.raises(SystemExit, match="No splat assets found"):
        build_package(run_dir, tmp_path / "package")
