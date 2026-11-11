import json

import pytest

from scan3d.deliver import deliver


def test_deliver_layout(tmp_path):
    run = tmp_path / "run"
    (run / "09_splat").mkdir(parents=True)
    (run / "11_ar").mkdir()
    (run / "manifest.json").write_text(json.dumps({"stages": {}}))
    (run / "09_splat" / "scene.spz").write_bytes(b"spz")
    (run / "11_ar" / "model_ar.glb").write_bytes(b"glb")
    (run / "11_ar" / "ar_report.json").write_text(json.dumps({"faces": 10, "scale": "UNSCALED"}))

    out = tmp_path / "out"
    manifest = deliver(run, out)

    assert (out / "splat" / "scene.spz").read_bytes() == b"spz"
    assert (out / "ar" / "model_ar.glb").exists()
    assert "mesh/model.obj" in manifest["not_included"]
    assert "ar/model_ar.usdz" in manifest["not_included"]
    assert any(file["file"] == "splat/scene.spz" and len(file["sha256"]) == 64
               for file in manifest["files"])
    assert (out / "README.md").exists()


def test_deliver_refuses_output_inside_source_run(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(ValueError, match="must not overlap"):
        deliver(run, run / "handoff")
    assert run.exists()
