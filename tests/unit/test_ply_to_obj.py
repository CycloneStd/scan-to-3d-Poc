import numpy as np 
import pytest

from scan3d.utils.ply_to_obj import convert_textured_ply,read_textured_ply

HEADER = (b"ply\nformat binary_little_endian 1.0\ncomment TextureFile texture.png\n"
          b"element vertex 4\nproperty float x\nproperty float y\nproperty float z\n"
          b"element face 2\nproperty list uchar int vertex_indices\n"
          b"property list uchar float texcoord\nend_header\n")


def write_ply(path, header=HEADER):
    verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype="<f4")
    face_dt = np.dtype([("n", "u1"), ("idx", "<i4", (3,)), ("m", "u1"), ("uv", "<f4", (6,))])
    faces = np.zeros(2, dtype=face_dt)
    faces["n"], faces["m"] = 3, 6
    faces["idx"] = [[0, 1, 2], [0, 2, 3]]
    faces["uv"] = [[0, 0, 1, 0, 1, 1], [0, 0, 1, 1, 0, 1]]
    path.write_bytes(header + verts.tobytes() + faces.tobytes())

def test_read(tmp_path):
    ply = tmp_path / "mesh.ply"
    write_ply(ply)
    verts, idx, uv = read_textured_ply(ply)
    assert verts.shape == (4, 3) and idx.shape == (2, 3) and uv.shape == (2, 3, 2)

def test_convert_flips_v(tmp_path):
    ply = tmp_path / "mesh.ply"
    write_ply(ply)
    info = convert_textured_ply(ply, "texture.png", tmp_path / "m.obj", flip_v=True)
    lines = (tmp_path / "m.obj").read_text().splitlines()
    assert info["faces"] == 2 and sum(l.startswith("v ") for l in lines) == 4
    vts = [l for l in lines if l.startswith("vt ")]
    assert len(vts) == 6 and vts[0] == "vt 0.000000 1.000000"
    assert [l for l in lines if l.startswith("f ")][0] == "f 1/1 2/2 3/3"
    assert "map_Kd texture.png" in (tmp_path / "m.mtl").read_text()

def test_unexpected_layout_fails(tmp_path):
    ply = tmp_path / "mesh.ply"
    write_ply(ply, HEADER.replace(b"property float z\n", b"property float z\nproperty float w\n"))
    with pytest.raises(ValueError):
        read_textured_ply(ply)