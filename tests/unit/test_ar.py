import json
from pathlib import Path
import numpy as np

from scan3d.ar import (
    estimate_ground_plane,
    estimate_scale_from_markers,
    estimate_up_robust,
    orient_obj,
    triangulate_rays,
)


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


def test_triangulate_rays_exact_intersection():
    # Ray 1: from (0, 0, 0) along (1, 0, 0)
    # Ray 2: from (1, 1, 0) along (0, -1, 0)
    # Intersection is (1, 0, 0)
    origins = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]])
    directions = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])
    pt = triangulate_rays(origins, directions)
    assert np.allclose(pt, [1.0, 0.0, 0.0], atol=1e-5)


def test_estimate_scale_from_markers(tmp_path):
    # Setup camera intrinsics (PINHOLE: fx=1000, fy=1000, cx=500, cy=500, 1000x1000 image)
    cams_file = tmp_path / "cameras.txt"
    cams_file.write_text("1 PINHOLE 1000 1000 1000.0 1000.0 500.0 500.0\n")

    # Marker corners in world coordinates (size = 0.2 units):
    # 0: (-0.1, 0.1, 0)
    # 1: (0.1, 0.1, 0)
    # 2: (0.1, -0.1, 0)
    # 3: (-0.1, -0.1, 0)
    marker_3d = np.array([
        [-0.1, 0.1, 0.0],
        [0.1, 0.1, 0.0],
        [0.1, -0.1, 0.0],
        [-0.1, -0.1, 0.0],
    ])

    # Two cameras looking at the origin along +Z:
    # Cam 1 at (-1, 0, -5), Cam 2 at (1, 0, -5)
    # COLMAP camera coords: X right, Y down, Z forward.
    # So looking at origin from -Z: R = I, t1 = (1, 0, 5), t2 = (-1, 0, 5)
    # In camera 1 frame: P_cam = P_world + [1, 0, 5]
    # In camera 2 frame: P_cam = P_world + [-1, 0, 5]
    def project(pt3d, t):
        pc = pt3d + t
        u = 1000.0 * (pc[0] / pc[2]) + 500.0
        v = 1000.0 * (pc[1] / pc[2]) + 500.0
        return [float(u), float(v)]

    corners_img1 = [project(p, np.array([1.0, 0.0, 5.0])) for p in marker_3d]
    corners_img2 = [project(p, np.array([-1.0, 0.0, 5.0])) for p in marker_3d]

    img_dir = tmp_path / "images"
    img_dir.mkdir()
    (img_dir / "img1.jpg").write_text("dummy")
    (img_dir / "img2.jpg").write_text("dummy")

    (img_dir / "img1.marker.json").write_text(json.dumps({"0": corners_img1}))
    (img_dir / "img2.marker.json").write_text(json.dumps({"0": corners_img2}))

    # In COLMAP images.txt:
    # QW QX QY QZ TX TY TZ CAMERA_ID NAME
    imgs_file = tmp_path / "images.txt"
    imgs_file.write_text(
        "1 1.0 0.0 0.0 0.0 1.0 0.0 5.0 1 img1.jpg\n\n"
        "2 1.0 0.0 0.0 0.0 -1.0 0.0 5.0 1 img2.jpg\n\n"
    )

    info = estimate_scale_from_markers(img_dir, cams_file, imgs_file, marker_id=0, marker_length_m=0.10)
    assert info is not None
    assert info["views_detected"] == 2
    assert np.isclose(info["model_edge_length"], 0.2, atol=1e-3)
    # Scale factor = 0.10 / 0.20 = 0.5
    assert np.isclose(info["scale_factor"], 0.5, atol=1e-3)


def test_estimate_ground_plane_and_robust_up(tmp_path):
    # 200 points on a ground plane y = -1.2 + small noise
    rng = np.random.default_rng(123)
    x = rng.uniform(-5, 5, 200)
    z = rng.uniform(-5, 5, 200)
    y = np.full(200, -1.2) + rng.normal(0, 0.005, 200)
    ground_pts = np.column_stack([x, y, z])

    # Some vertical wall points
    wall_x = rng.uniform(-2, 2, 50)
    wall_y = rng.uniform(-1.2, 2.0, 50)
    wall_z = np.full(50, 3.0)
    wall_pts = np.column_stack([wall_x, wall_y, wall_z])

    all_pts = np.vstack([ground_pts, wall_pts])

    cam_up = np.array([0.0, 1.0, 0.0])
    normal, d = estimate_ground_plane(all_pts, camera_up=cam_up, distance_threshold=0.03)

    assert np.allclose(normal, [0.0, 1.0, 0.0], atol=0.05)
    assert np.isclose(d, 1.2, atol=0.05)

    # Test estimate_up_robust
    imgs_file = tmp_path / "images.txt"
    # COLMAP camera with rotation such that -R[1] = [0, 1, 0]
    # When R = I, -R[1] = [0, -1, 0].
    # To get -R[1] = [0, 1, 0], we need R[1] = [0, -1, 0].
    # 180 deg rotation around X: qw=0, qx=1, qy=0, qz=0
    # R = [[1, 0, 0], [0, -1, 0], [0, 0, -1]] -> -R[1] = [0, 1, 0]
    imgs_file.write_text("1 0.0 1.0 0.0 0.0 0.0 0.0 5.0 1 cam1.jpg\n\n")

    up, coherence, cam_count, method, ground_d = estimate_up_robust(imgs_file, points=all_pts)
    assert method == "ground_plane_ransac"
    assert np.allclose(up, [0.0, 1.0, 0.0], atol=0.05)
    assert ground_d is not None


def test_orient_obj_with_ground_plane(tmp_path):
    obj = tmp_path / "test.obj"
    # Ground plane is at Y = -2.0, with a low noise spike at Y = -3.5
    obj.write_text(
        "v -1 -2 -1\nv 1 -2 -1\nv 1 -2 1\nv -1 -2 1\n"
        "v 0 2 0\n"
        "v 0 -3.5 0\n"  # underground noise spike
        "f 1 2 3\n"
    )
    # Ground plane equation: y + 2.0 = 0 -> normal = (0, 1, 0), d = 2.0
    orient_obj(obj, np.array([0.0, 1.0, 0.0]), scale=1.0, ground_plane_d=2.0)
    text = obj.read_text()
    vertices = np.array([[float(v) for v in line.split()[1:4]]
                         for line in text.splitlines() if line.startswith("v ")])
    # The 4 ground vertices originally at Y = -2.0 should now be at Y = 0.0
    ground_verts = vertices[:4]
    assert np.allclose(ground_verts[:, 1], 0.0, atol=1e-5)
    # The noise spike is at Y = -1.5 (below floor level), not forcing the whole model up
    assert np.isclose(vertices[5, 1], -1.5, atol=1e-5)