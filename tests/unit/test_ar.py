import numpy as np

from scan3d.ar import orient_obj


def test_orient_obj_up_scale_and_origin(tmp_path):
    obj = tmp_path / "m.obj"
    obj.write_text("mtllib m.mtl\nv 0 0 0\nv 2 0 0\nv 0 -4 0\nv 2 -4 6\nvt 0 0\nf 1/1 2/1 3/1\n")
    orient_obj(obj, np.array([0.0, -1.0, 0.0]), scale=0.5)
    text = obj.read_text()
    vertices = np.array([[float(value) for value in line.split()[1:4]]
                         for line in text.splitlines() if line.startswith("v ")])
    assert np.isclose(vertices[:, 1].min(), 0.0)
    assert np.isclose(vertices[:, 1].max(), 2.0)
    assert np.isclose((vertices[:, 0].min() + vertices[:, 0].max()) / 2, 0.0)
    assert "f 1/1 2/1 3/1" in text