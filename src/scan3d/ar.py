from __future__ import annotations

import json
import logging
import shutil
from itertools import chain
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np

log = logging.getLogger("scan3d.ar")


def _read_cameras(images_txt: Path) -> list[tuple[np.ndarray, np.ndarray]]:
    lines = images_txt.read_text().splitlines()
    cameras = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 10:
            raise ValueError(f"Invalid COLMAP image record in {images_txt}: {line}")
        qw, qx, qy, qz = map(float, fields[1:5])
        rotation = np.array([
            [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qw * qz), 2 * (qx * qz + qw * qy)],
            [2 * (qx * qy + qw * qz), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qw * qx)],
            [2 * (qx * qz - qw * qy), 2 * (qy * qz + qw * qx), 1 - 2 * (qx * qx + qy * qy)],
        ], dtype=np.float64)
        translation = np.asarray(list(map(float, fields[5:8])), dtype=np.float64)
        cameras.append((rotation, translation))
        if i < len(lines):
            i += 1
    return cameras


def read_cameras_txt(cameras_txt: Path) -> dict[int, dict]:
    """Parse COLMAP cameras.txt into a dictionary keyed by camera ID."""
    cameras = {}
    if not cameras_txt.exists():
        return cameras
    for line in cameras_txt.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        cam_id = int(parts[0])
        model = parts[1]
        width, height = int(parts[2]), int(parts[3])
        params = [float(p) for p in parts[4:]]
        if model in ("SIMPLE_PINHOLE", "SIMPLE_RADIAL"):
            fx = fy = params[0]
            cx, cy = params[1], params[2]
        elif model in ("PINHOLE", "RADIAL", "OPENCV", "OPENCV_FISHEYE", "FULL_OPENCV"):
            fx, fy = params[0], params[1]
            cx, cy = params[2], params[3]
        else:
            fx = fy = params[0] if params else float(width)
            cx, cy = width / 2.0, height / 2.0
        cameras[cam_id] = {
            "model": model, "width": width, "height": height,
            "fx": fx, "fy": fy, "cx": cx, "cy": cy, "params": params,
        }
    return cameras


def read_images_txt(images_txt: Path) -> dict[str, dict]:
    """Parse COLMAP images.txt into a dict keyed by image filename."""
    images = {}
    if not images_txt.exists():
        return images
    lines = images_txt.read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 10:
            continue
        image_id = int(fields[0])
        qw, qx, qy, qz = map(float, fields[1:5])
        tx, ty, tz = map(float, fields[5:8])
        cam_id = int(fields[8])
        name = fields[9]
        rotation = np.array([
            [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qw * qz), 2 * (qx * qz + qw * qy)],
            [2 * (qx * qy + qw * qz), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qw * qx)],
            [2 * (qx * qz - qw * qy), 2 * (qy * qz + qw * qx), 1 - 2 * (qx * qx + qy * qy)],
        ], dtype=np.float64)
        translation = np.array([tx, ty, tz], dtype=np.float64)
        center = -rotation.T @ translation
        images[name] = {
            "image_id": image_id, "camera_id": cam_id,
            "rotation": rotation, "translation": translation, "center": center,
        }
        if i < len(lines):
            i += 1
    return images


def triangulate_rays(origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
    """Find the 3D point that minimizes sum of squared perpendicular distances to all rays.
    origins: (N, 3), directions: (N, 3) normalized."""
    dirs = directions / np.linalg.norm(directions, axis=1, keepdims=True)
    I = np.eye(3)
    projs = I - dirs[:, :, None] * dirs[:, None, :]
    A = projs.sum(axis=0)
    b = (projs @ origins[:, :, None]).squeeze(-1).sum(axis=0)
    try:
        return np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(A, b, rcond=None)[0]


def detect_marker_corners_in_image(image_path: Path, marker_id: int = 0,
                                   dictionary_name: str = "DICT_4X4_50") -> np.ndarray | None:
    """Detect 4 corners [(u, v), ...] of marker_id in an image.
    Uses OpenCV aruco module when installed, with sidecar JSON fallback for testing."""
    sidecar = image_path.with_suffix(".marker.json")
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            if str(marker_id) in data:
                return np.asarray(data[str(marker_id)], dtype=np.float64)
        except Exception:
            pass

    try:
        import cv2
        img = cv2.imread(str(image_path))
        if img is not None and hasattr(cv2, "aruco"):
            dict_attr = getattr(cv2.aruco, dictionary_name, getattr(cv2.aruco, "DICT_4X4_50", None))
            if dict_attr is not None:
                dictionary = cv2.aruco.getPredefinedDictionary(dict_attr)
                if hasattr(cv2.aruco, "ArucoDetector"):
                    detector = cv2.aruco.ArucoDetector(dictionary)
                    corners, ids, _ = detector.detectMarkers(img)
                else:
                    corners, ids, _ = cv2.aruco.detectMarkers(img, dictionary)
                if ids is not None and len(ids) > 0:
                    flat_ids = ids.ravel().tolist()
                    if marker_id in flat_ids:
                        idx = flat_ids.index(marker_id)
                        return np.asarray(corners[idx][0], dtype=np.float64)
    except Exception:
        pass

    return None


def estimate_scale_from_markers(images_dir: Path, cameras_txt: Path, images_txt: Path,
                                marker_id: int = 0, marker_length_m: float = 0.10) -> dict | None:
    """Triangulate 4 ArUco marker corners across registered views and calculate real-world metric scale factor."""
    cams = read_cameras_txt(cameras_txt)
    imgs = read_images_txt(images_txt)
    if not cams or not imgs:
        return None

    corner_rays: list[list[tuple[np.ndarray, np.ndarray]]] = [[], [], [], []]
    views_detected = 0

    for name, img_info in imgs.items():
        img_path = images_dir / name
        if not img_path.exists():
            continue
        corners_2d = detect_marker_corners_in_image(img_path, marker_id=marker_id)
        if corners_2d is None or len(corners_2d) != 4:
            continue

        cam = cams.get(img_info["camera_id"])
        if not cam:
            continue

        views_detected += 1
        fx, fy, cx, cy = cam["fx"], cam["fy"], cam["cx"], cam["cy"]
        R, t, C = img_info["rotation"], img_info["translation"], img_info["center"]

        for k in range(4):
            u, v = corners_2d[k]
            ray_cam = np.array([(u - cx) / fx, (v - cy) / fy, 1.0], dtype=np.float64)
            ray_world = R.T @ ray_cam
            direction = ray_world / np.linalg.norm(ray_world)
            corner_rays[k].append((C, direction))

    if views_detected < 2:
        return None

    corners_3d = []
    for k in range(4):
        origins = np.array([r[0] for r in corner_rays[k]])
        directions = np.array([r[1] for r in corner_rays[k]])
        corner_3d = triangulate_rays(origins, directions)
        corners_3d.append(corner_3d)

    c3d = np.array(corners_3d)
    # Edge lengths in model units between consecutive corners: (0->1, 1->2, 2->3, 3->0)
    edge_lengths = [
        float(np.linalg.norm(c3d[1] - c3d[0])),
        float(np.linalg.norm(c3d[2] - c3d[1])),
        float(np.linalg.norm(c3d[3] - c3d[2])),
        float(np.linalg.norm(c3d[0] - c3d[3])),
    ]
    median_edge = float(np.median(edge_lengths))
    if median_edge <= 1e-7:
        return None

    scale_factor = marker_length_m / median_edge
    consistency = float(np.std(edge_lengths) / max(np.mean(edge_lengths), 1e-7))

    return {
        "scale_factor": float(scale_factor),
        "marker_id": marker_id,
        "views_detected": views_detected,
        "model_edge_length": round(median_edge, 6),
        "marker_length_m": marker_length_m,
        "edge_lengths": [round(e, 6) for e in edge_lengths],
        "consistency": round(consistency, 4),
        "corners_3d": [[round(coord, 6) for coord in pt] for pt in c3d.tolist()],
    }


def estimate_ground_plane(points: np.ndarray, camera_up: np.ndarray | None = None,
                          max_iterations: int = 1500, distance_threshold: float = 0.05,
                          min_inliers_fraction: float = 0.05) -> tuple[np.ndarray, float] | None:
    """Find dominant horizontal ground plane using RANSAC.
    points: (N, 3)
    Returns: (normal, d) such that normal . x + d = 0, with normal aligned towards up."""
    if len(points) < 50:
        return None

    sample_pts = points
    if len(points) > 10000:
        step = len(points) // 10000
        sample_pts = points[::step]

    n_pts = len(sample_pts)
    best_inliers_count = 0
    best_plane = None
    rng = np.random.default_rng(42)

    for _ in range(max_iterations):
        sample_idx = rng.choice(n_pts, size=3, replace=False)
        p0, p1, p2 = sample_pts[sample_idx]
        normal = np.cross(p1 - p0, p2 - p0)
        norm_len = np.linalg.norm(normal)
        if norm_len < 1e-8:
            continue
        normal /= norm_len

        if camera_up is not None:
            dot = float(np.dot(normal, camera_up))
            if abs(dot) < 0.65:  # within ~49 degrees of vertical
                continue
            if dot < 0:
                normal = -normal

        d = -float(np.dot(normal, p0))
        dists = np.abs(sample_pts @ normal + d)
        inliers_count = int(np.sum(dists <= distance_threshold))

        if inliers_count > best_inliers_count:
            best_inliers_count = inliers_count
            best_plane = (normal, d)

    if best_plane is None or (best_inliers_count / n_pts < min_inliers_fraction and best_inliers_count < 40):
        return None

    normal, d = best_plane
    inlier_mask = np.abs(sample_pts @ normal + d) <= distance_threshold
    inlier_pts = sample_pts[inlier_mask]
    center = inlier_pts.mean(axis=0)
    _, _, vh = np.linalg.svd(inlier_pts - center)
    refined_normal = vh[2]
    if camera_up is not None and np.dot(refined_normal, camera_up) < 0:
        refined_normal = -refined_normal
    refined_d = -float(np.dot(refined_normal, center))

    return refined_normal, refined_d


def _rotation_between(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    source_norm = np.linalg.norm(source)
    target_norm = np.linalg.norm(target)
    if source_norm == 0 or target_norm == 0:
        raise ValueError("Cannot orient using a zero-length direction")
    a, b = source / source_norm, target / target_norm
    cosine = float(np.clip(np.dot(a, b), -1.0, 1.0))
    cross = np.cross(a, b)
    sine = float(np.linalg.norm(cross))
    if sine < 1e-12:
        if cosine > 0:
            return np.eye(3)
        basis = np.eye(3)[np.argmin(np.abs(a))]
        axis = np.cross(a, basis)
        axis /= np.linalg.norm(axis)
        return 2 * np.outer(axis, axis) - np.eye(3)
    skew = np.array([[0, -cross[2], cross[1]],
                     [cross[2], 0, -cross[0]],
                     [-cross[1], cross[0], 0]])
    return np.eye(3) + skew + skew @ skew * ((1 - cosine) / (sine * sine))


def estimate_up(images_txt: Path) -> tuple[np.ndarray, float, int]:
    """Average camera up directions in model coordinates; COLMAP camera Y points down."""
    cameras = _read_cameras(images_txt)
    if not cameras:
        raise ValueError(f"No registered cameras found in {images_txt}")
    ups = np.array([-rotation[1] for rotation, _ in cameras])
    mean = ups.mean(axis=0)
    coherence = float(np.linalg.norm(mean))
    if coherence < 1e-12:
        raise ValueError(f"Camera up directions do not have a coherent average in {images_txt}")
    return mean / coherence, coherence, len(cameras)


def estimate_up_robust(images_txt: Path, points: np.ndarray | None = None) -> tuple[np.ndarray, float, int, str, float | None]:
    """Combines camera up directions with RANSAC ground plane fitting when point data is available."""
    camera_up, coherence, cam_count = estimate_up(images_txt)
    method = "camera_mean"
    ground_d = None

    if points is not None and len(points) >= 100:
        try:
            span = np.ptp(points, axis=0)
            diag = float(np.linalg.norm(span))
            thresh = max(0.02, diag * 0.02)
            plane = estimate_ground_plane(points, camera_up=camera_up, distance_threshold=thresh)
            if plane is not None:
                ground_normal, ground_d = plane
                if np.dot(ground_normal, camera_up) > 0.65:
                    return ground_normal, coherence, cam_count, "ground_plane_ransac", ground_d
        except Exception:
            pass

    return camera_up, coherence, cam_count, method, ground_d


def orient_obj(obj_path: Path, up, scale: float | None, ground_plane_d: float | None = None) -> dict:
    """Rotate `up` to +Y, optionally scale, centre in X/Z, and set ground level at Y=0."""
    rotation = _rotation_between(np.asarray(up, dtype=float), np.array([0.0, 1.0, 0.0]))
    with obj_path.open() as source:
        vertex_lines = (line for line in source if line.startswith("v "))
        first = next(vertex_lines, None)
        if first is None:
            raise ValueError(f"No vertices found in {obj_path}")
        vertices = np.loadtxt(chain((first,), vertex_lines), usecols=(1, 2, 3), ndmin=2)
    vertices = vertices @ rotation.T
    if scale:
        vertices *= scale
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    vertices[:, 0] -= (low[0] + high[0]) / 2
    vertices[:, 2] -= (low[2] + high[2]) / 2

    if ground_plane_d is not None:
        ground_y = (-ground_plane_d * scale) if scale else -ground_plane_d
        # Shift vertices so ground plane sits at Y = 0
        vertices[:, 1] -= ground_y
    else:
        vertices[:, 1] -= low[1]

    vertex_index = 0
    output = NamedTemporaryFile(mode="w", dir=obj_path.parent, delete=False)
    temporary = Path(output.name)
    try:
        with output, obj_path.open() as source:
            for line in source:
                if line.startswith("v "):
                    ending = "\n" if line.endswith("\n") else ""
                    line = ("v %.6f %.6f %.6f" % tuple(vertices[vertex_index])) + ending
                    vertex_index += 1
                output.write(line)
                if vertex_index == len(vertices):
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                    break
        shutil.copymode(obj_path, temporary)
        temporary.replace(obj_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "size_x_y_z": [round(float(s), 4) for s in high - low],
        "vertices": len(vertices),
        "ground_aligned": ground_plane_d is not None,
    }
