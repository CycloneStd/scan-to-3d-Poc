from __future__ import annotations

from pathlib import Path

import numpy as np


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


def orient_obj(obj_path: Path, up, scale: float | None) -> dict:
    """Rotate `up` to +Y, optionally scale, centre in X/Z, and put the lowest point at Y=0."""
    lines = obj_path.read_text().split("\n")
    vertex_indices = [i for i, line in enumerate(lines) if line.startswith("v ")]
    if not vertex_indices:
        raise ValueError(f"No vertices found in {obj_path}")
    vertices = np.array([lines[i].split()[1:4] for i in vertex_indices], dtype=np.float64)
    vertices = vertices @ _rotation_between(np.asarray(up, dtype=float), np.array([0.0, 1.0, 0.0])).T
    if scale:
        vertices *= scale
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    vertices[:, 0] -= (low[0] + high[0]) / 2
    vertices[:, 2] -= (low[2] + high[2]) / 2
    vertices[:, 1] -= low[1]
    for i, vertex in zip(vertex_indices, vertices):
        lines[i] = "v %.6f %.6f %.6f" % tuple(vertex)
    obj_path.write_text("\n".join(lines))
    size = vertices.max(axis=0) - vertices.min(axis=0)
    return {"size_x_y_z": [round(float(s), 4) for s in size], "vertices": len(vertex_indices)}