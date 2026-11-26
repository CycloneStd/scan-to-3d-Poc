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


def test_delivery_rebuild_preserves_unrelated_files(tmp_path):
    run, out = tmp_path / "run", tmp_path / "delivery"
    run.mkdir()
    (run / "manifest.json").write_text('{"stages": {}}')
    deliver(run, out)
    deliver(run, out)
    notes = out / "user-notes.txt"
    notes.write_text("keep")
    with pytest.raises(ValueError, match="outside the previous delivery"):
        deliver(run, out)
    assert notes.read_text() == "keep"


def test_delivery_preserves_already_oriented_export(tmp_path):
    run, out = tmp_path / "run", tmp_path / "delivery"
    mesh = run / "08_export/exports/textured"
    mesh.mkdir(parents=True)
    (mesh / "model.obj").write_text("v -1 0 0\nv 1 2 0\n")
    (mesh / "model.mtl").touch()
    (mesh / "texture.png").touch()
    stages = {"export": {"metrics": {"obj_orientation": {"size_x_y_z": [2, 2, 0]}}}}
    (run / "manifest.json").write_text(json.dumps({"stages": stages}))
    result = deliver(run, out)
    assert (out / "mesh/model.obj").read_bytes() == (mesh / "model.obj").read_bytes()
    assert "upright" in result["orientation"]["mesh"]
