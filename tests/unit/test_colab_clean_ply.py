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


def test_clean_ply_rejects_truncated_header(tmp_path):
    src = tmp_path / "broken.ply"
    src.write_bytes(b"ply\nformat binary_little_endian 1.0\n")
    with pytest.raises(ValueError, match="Truncated PLY header"):
        clean_ply(src, tmp_path / "out.ply")


def test_clean_ply_filters_out_of_bounds_haze(tmp_path):
    dtype = np.dtype([(name, "<f4") for name in
                      ("x", "y", "z", "opacity", "scale_0", "scale_1", "scale_2")])
    # 20 solid points clustered between x=[-1, 1], y=[-1, 1], z=[0, 0]
    data = np.zeros(23, dtype=dtype)
    data["x"][:20] = np.linspace(-1, 1, 20)
    data["y"][:20] = np.linspace(-1, 1, 20)
    data["opacity"][:20] = 2.0
    data["scale_0"][:20] = data["scale_1"][:20] = data["scale_2"][:20] = -5.0

    # Gaussian 20: low opacity (filtered by low_opacity)
    data["opacity"][20] = -3.0

    # Gaussian 21: solid, within radius, but way above the bounding box in Z (e.g. sky floater/haze)
    data["x"][21] = 0.0
    data["y"][21] = 0.0
    data["z"][21] = 1.2
    data["opacity"][21] = 2.0
    data["scale_0"][21] = data["scale_1"][21] = data["scale_2"][21] = -5.0

    # Gaussian 22: valid in-bounds point
    data["x"][22] = 0.5
    data["y"][22] = 0.5
    data["z"][22] = 0.0
    data["opacity"][22] = 2.0
    data["scale_0"][22] = data["scale_1"][22] = data["scale_2"][22] = -5.0

    src, dst = tmp_path / "input.ply", tmp_path / "clean_bbox.ply"
    write_ply(src, data)
    stats = clean_ply(src, dst, crop_factor=5.0, bbox_margin=0.2)

    assert stats["before"] == 23
    assert stats["after"] == 21
    assert "out_of_bounds" in stats["removed"]
    assert stats["removed"]["out_of_bounds"] == 1
    assert stats["removed"]["low_opacity"] == 1
