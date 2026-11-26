from __future__ import annotations

from pathlib import Path

import numpy as np

EXPECTED_VERTEX_PROPS = ["property float x", "property float y", "property float z"]
EXPECTED_FACE_PROPS = ["property list uchar int vertex_indices", "property list uchar float texcoord"]


def read_textured_ply(path: Path):
    with open(path, "rb") as fh:
        header = []
        while True:
            raw = fh.readline()
            if not raw:
                raise ValueError("Truncated PLY header")
            line = raw.decode("ascii").strip()
            header.append(line)
            if line == "end_header":
                break
        data_offset = fh.tell()
    if "format binary_little_endian 1.0" not in header:
        raise ValueError(f"Unsupported PLY format in {path}: {header}")
    nv = nf = None
    props: dict[str, list[str]] = {}
    current = None
    for line in header:
        if line.startswith("element "):
            _, name, n = line.split()
            current = name
            props[name] = []
            if name == "vertex":
                nv = int(n)
            elif name == "face":
                nf = int(n)
        elif line.startswith("property") and current:
            props[current].append(line)
    if props.get("vertex") != EXPECTED_VERTEX_PROPS or props.get("face") != EXPECTED_FACE_PROPS:
        raise ValueError(f"Unexpected textured-PLY layout in {path}: {props}")

    face_dt = np.dtype([("n", "u1"), ("idx", "<i4", (3,)), ("m", "u1"), ("uv", "<f4", (6,))])
    if nv is None or nf is None or nv < 0 or nf < 0:
        raise ValueError("Invalid textured PLY element counts")
    if path.stat().st_size - data_offset < nv * 12 + nf * face_dt.itemsize:
        raise ValueError("Truncated textured PLY data")
    with path.open("rb") as fh:
        fh.seek(data_offset)
        verts = np.fromfile(fh, dtype="<f4", count=nv * 3).reshape(nv, 3)
        faces = np.fromfile(fh, dtype=face_dt, count=nf)
    if len(faces) != nf or not (faces["n"] == 3).all() or not (faces["m"] == 6).all():
        raise ValueError("Textured PLY contains non-triangle faces or unexpected texcoord counts")
    if nf and (faces["idx"].min() < 0 or faces["idx"].max() >= nv):
        raise ValueError("Textured PLY face references an invalid vertex")
    return verts, faces["idx"], faces["uv"].reshape(nf, 3, 2)


def read_ply_points(path: Path) -> np.ndarray | None:
    """Read XYZ coordinates from a binary PLY file."""
    if not path.exists():
        return None
    try:
        props = []
        nv = None
        data_offset = 0
        with open(path, "rb") as fh:
            while True:
                line = fh.readline()
                if not line:
                    break
                decoded = line.decode("ascii", errors="ignore").strip()
                if decoded.startswith("element vertex"):
                    nv = int(decoded.split()[2])
                elif decoded.startswith("property") and nv is not None:
                    parts = decoded.split()
                    t, name = parts[1], parts[2]
                    t_dt = "<f4" if t in ("float", "float32") else "<f8" if t in ("double", "float64") else "u1"
                    props.append((name, t_dt))
                elif decoded == "end_header":
                    data_offset = fh.tell()
                    break
            if nv is None or not props:
                return None
            dtype = np.dtype(props)
            fh.seek(data_offset)
            data = np.fromfile(fh, dtype=dtype, count=nv)
            if "x" in data.dtype.names and "y" in data.dtype.names and "z" in data.dtype.names:
                return np.column_stack([data["x"], data["y"], data["z"]]).astype(np.float64)
    except Exception:
        pass
    return None


def prune_unsupported_mesh_faces(verts: np.ndarray, idx: np.ndarray, uv: np.ndarray,
                                 fused_pts: np.ndarray,
                                 max_distance: float | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Remove triangles whose vertices are far from any measured fused point cloud point,
    eliminating hallucinated Poisson balloon sheets and paper-like planes."""
    if len(idx) == 0 or len(fused_pts) == 0:
        return verts, idx, uv

    pts = fused_pts
    if len(pts) > 50000:
        step = len(pts) // 50000
        pts = pts[::step]

    span = np.ptp(pts, axis=0)
    diag = float(np.linalg.norm(span))
    if max_distance is None:
        max_distance = max(0.04, diag * 0.04)

    voxel_size = max_distance
    voxel_coords = np.floor(pts / voxel_size).astype(np.int64)
    occupied = set(map(tuple, voxel_coords))

    vert_voxels = np.floor(verts / voxel_size).astype(np.int64)
    offsets = np.array([
        [dx, dy, dz]
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for dz in (-1, 0, 1)
    ], dtype=np.int64)

    vert_supported = np.zeros(len(verts), dtype=bool)
    for i, v in enumerate(vert_voxels):
        if tuple(v) in occupied:
            vert_supported[i] = True
            continue
        for off in offsets:
            if tuple(v + off) in occupied:
                vert_supported[i] = True
                break

    face_supported = vert_supported[idx].all(axis=1)
    if not face_supported.any():
        return verts, idx, uv

    idx, uv = idx[face_supported], uv[face_supported]
    used, remapped = np.unique(idx.ravel(), return_inverse=True)
    verts, idx = verts[used], remapped.reshape(-1, 3)
    return verts, idx, uv


def remove_small_components(verts: np.ndarray, idx: np.ndarray, uv: np.ndarray,
                            min_faces: int = 50) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Prune isolated floating triangle clusters with fewer than min_faces."""
    if len(idx) == 0 or min_faces <= 1:
        return verts, idx, uv

    nv = len(verts)
    parent = np.arange(nv, dtype=np.int32)

    def find(i):
        root = i
        while parent[root] != root:
            root = parent[root]
        curr = i
        while curr != root:
            nxt = parent[curr]
            parent[curr] = root
            curr = nxt
        return root

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i0, i1, i2 in idx:
        union(i0, i1)
        union(i1, i2)

    roots = np.array([find(tri[0]) for tri in idx], dtype=np.int32)
    unique_roots, counts = np.unique(roots, return_counts=True)
    root_to_count = dict(zip(unique_roots, counts))

    max_count = max(counts) if len(counts) > 0 else 0
    keep_mask = np.array([root_to_count[r] >= min_faces or root_to_count[r] == max_count for r in roots], dtype=bool)

    if not keep_mask.any() or keep_mask.all():
        return verts, idx, uv

    idx, uv = idx[keep_mask], uv[keep_mask]
    used, remapped = np.unique(idx.ravel(), return_inverse=True)
    verts, idx = verts[used], remapped.reshape(-1, 3)
    return verts, idx, uv


def convert_textured_ply(ply: Path, texture_name: str, obj_path: Path, flip_v: bool,
                         max_edge_factor: float | None = None,
                         min_component_faces: int | None = None,
                         fused_pts: np.ndarray | None = None,
                         max_point_distance: float | None = None) -> dict:
    verts, idx, uv = read_textured_ply(ply)
    original_faces = len(idx)

    # 1. Prune unsupported Poisson hallucinated sheets that have no fused point support
    if fused_pts is not None and len(fused_pts) > 0 and len(idx) > 0:
        verts, idx, uv = prune_unsupported_mesh_faces(verts, idx, uv, fused_pts, max_distance=max_point_distance)

    # 2. Trim stretched outlier edges
    if max_edge_factor and len(idx) > 0:
        current_faces = len(idx)
        lengths = np.empty((current_faces, 3), dtype=np.float32)
        for start in range(0, current_faces, 32768):
            corners = verts[idx[start:start + 32768]]
            lengths[start:start + len(corners)] = np.linalg.norm(corners - np.roll(corners, 1, axis=1), axis=2)
        median = np.median(lengths)
        if median > 0:
            keep = lengths.max(axis=1) <= max_edge_factor * median
            if keep.any():
                idx, uv = idx[keep], uv[keep]
                used, remapped = np.unique(idx.ravel(), return_inverse=True)
                verts, idx = verts[used], remapped.reshape(-1, 3)

    # 3. Remove small disconnected floating components
    if min_component_faces and min_component_faces > 1 and len(idx) > 0:
        verts, idx, uv = remove_small_components(verts, idx, uv, min_faces=min_component_faces)

    nf = len(idx)
    mtl_path = obj_path.with_suffix(".mtl")
    with open(obj_path, "w") as fh:
        fh.write(f"mtllib {mtl_path.name}\nusemtl scan\n")
        np.savetxt(fh, verts, fmt="v %.6f %.6f %.6f")
        for start in range(0, nf, 32768):
            coords = uv[start:start + 32768].reshape(-1, 2)
            if flip_v:
                coords = coords.astype(np.float64)
                coords[:, 1] = 1.0 - coords[:, 1]
            np.savetxt(fh, coords, fmt="vt %.6f %.6f")
        for start in range(0, nf, 32768):
            stop = min(start + 32768, nf)
            faces = np.empty((stop - start, 6), dtype=np.int64)
            faces[:, 0::2] = idx[start:stop]
            faces[:, 0::2] += 1
            faces[:, 1::2] = np.arange(start * 3 + 1, stop * 3 + 1).reshape(-1, 3)
            np.savetxt(fh, faces, fmt="f %d/%d %d/%d %d/%d")
    mtl_path.write_text(f"newmtl scan\nNs 60.0\nKa 0.2 0.2 0.2\nKd 0.8 0.8 0.8\nKs 0.15 0.15 0.15\nd 1.0\nillum 2\nmap_Kd {texture_name}\n")
    return {"obj": obj_path.name, "vertices": int(len(verts)), "faces": int(nf), "trimmed_faces": original_faces - nf, "flip_v": flip_v}