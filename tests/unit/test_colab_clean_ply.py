import numpy as np
import pytest

from scan3d.remote.colab_entry import clean_ply


def write_ply(path, data):
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {len(data)}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property float opacity\n"
        "property float scale_0\n"
        "property float scale_1\n"
        "property float scale_2\n"
        "end_header\n"
    )
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(data.tobytes())


def test_clean_ply_filters_and_reports_stats(tmp_path):
    dtype = np.dtype([(name, "<f4") for name in
                      ("x", "y", "z", "opacity", "scale_0", "scale_1", "scale_2")])
    data = np.zeros(22, dtype=dtype)
    data["x"][:20] = np.linspace(-1, 1, 20)
    data["x"][20] = 12
    data["x"][21] = 0.08
    data["opacity"] = 2
    data["scale_0"] = data["scale_1"] = data["scale_2"] = -5
    data["opacity"][0] = -2
    data["scale_0"][21] = data["scale_1"][21] = data["scale_2"][21] = -1

    src, dst = tmp_path / "input.ply", tmp_path / "clean.ply"
    write_ply(src, data)
    stats = clean_ply(src, dst)

    assert stats["before"] == 22
    assert stats["after"] == 19
    assert stats["removed"] == {"low_opacity": 1, "oversized": 1, "far_away": 1}
    assert stats["scene_radius"] > 0
    assert dst.read_bytes().startswith(b"ply\nformat binary_little_endian 1.0\n")


def test_clean_ply_rejects_empty_solid_reference_set(tmp_path):
    dtype = np.dtype([(name, "<f4") for name in
                      ("x", "y", "z", "opacity", "scale_0", "scale_1", "scale_2")])
    data = np.zeros(1, dtype=dtype)
    src, dst = tmp_path / "input.ply", tmp_path / "clean.ply"
    write_ply(src, data)

    with pytest.raises(ValueError, match="no Gaussians have opacity greater than 0.5"):
        clean_ply(src, dst)
