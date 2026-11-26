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

def test_textured_ply_rejects_negative_vertex_indices(tmp_path):
    ply = tmp_path / "mesh.ply"
    write_ply(ply)
    with ply.open("r+b") as stream:
        stream.seek(len(HEADER) + 4 * 12 + 1)
        stream.write((-1).to_bytes(4, "little", signed=True))
    with pytest.raises(ValueError, match="invalid vertex"):
        read_textured_ply(ply)


def test_remove_small_components():
    from scan3d.utils.ply_to_obj import remove_small_components
    # Main component: 2 connected triangles sharing an edge (verts 0, 1, 2 and 0, 2, 3)
    # Disconnected component: 1 floating triangle (verts 4, 5, 6)
    verts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [10, 10, 10], [11, 10, 10], [11, 11, 10]
    ], dtype=np.float32)
    idx = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6]], dtype=np.int32)
    uv = np.zeros((3, 3, 2), dtype=np.float32)

    # With min_faces=2, the single floating triangle [4, 5, 6] must be pruned
    v_out, idx_out, uv_out = remove_small_components(verts, idx, uv, min_faces=2)

    assert len(idx_out) == 2
    assert len(v_out) == 4
    assert np.all(idx_out < 4)


def test_prune_unsupported_mesh_faces():
    from scan3d.utils.ply_to_obj import prune_unsupported_mesh_faces
    # 2 faces:
    # Face 0 (verts 0, 1, 2) is on the real scanned surface near (0, 0, 0)
    # Face 1 (verts 3, 4, 5) is a hallucinated "paper sheet" stretching into empty space near (5, 5, 5)
    verts = np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
        [5.0, 5.0, 5.0], [6.0, 5.0, 5.0], [5.0, 6.0, 5.0],
    ], dtype=np.float32)
    idx = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
    uv = np.zeros((2, 3, 2), dtype=np.float32)

    # Fused point cloud has points around (0, 0, 0) only
    fused_pts = np.array([
        [0.1, 0.1, 0.0], [0.5, 0.2, 0.0], [0.8, 0.1, 0.0], [0.2, 0.8, 0.0]
    ], dtype=np.float64)

    # Max distance = 1.0
    v_out, idx_out, uv_out = prune_unsupported_mesh_faces(verts, idx, uv, fused_pts, max_distance=1.2)

    # Face 1 (the paper sheet at (5, 5, 5)) must be pruned!
    assert len(idx_out) == 1
    assert len(v_out) == 3
    assert np.all(v_out[:, 0] <= 1.0)
