from __future__ import annotations

from pathlib import Path

import numpy as np

EXPECTED_VERTEX_PROPS = ["property float x", "property float y", "property float z"]
EXPECTED_FACE_PROPS = ["property list uchar int vertex_indices", "property list uchar float texcoord"]


def read_textured_ply(path: Path):
    with open(path, "rb") as fh:
        header = []
        while True:
            line = fh.readline().decode("ascii").strip()
            header.append(line)
            if line == "end_header":
                break
        data = fh.read()
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
    verts = np.frombuffer(data, dtype="<f4", count=nv * 3).reshape(nv, 3)
    faces = np.frombuffer(data, dtype=face_dt, count=nf, offset=nv * 12)
    if not (faces["n"] == 3).all() or not (faces["m"] == 6).all():
        raise ValueError("Textured PLY contains non-triangle faces or unexpected texcoord counts")
    return verts, faces["idx"], faces["uv"].reshape(nf, 3, 2)


def convert_textured_ply(ply: Path, texture_name: str, obj_path: Path, flip_v: bool) -> dict:
    verts, idx, uv = read_textured_ply(ply)
    nf = len(idx)
    uv = uv.reshape(-1, 2).astype(np.float64)
    if flip_v:
        uv[:, 1] = 1.0 - uv[:, 1]
    faces = np.empty((nf, 6), dtype=np.int64)
    faces[:, 0::2] = idx.astype(np.int64) + 1
    faces[:, 1::2] = np.arange(1, nf * 3 + 1).reshape(nf, 3)

    mtl_path = obj_path.with_suffix(".mtl")
    with open(obj_path, "w") as fh:
        fh.write(f"mtllib {mtl_path.name}\nusemtl scan\n")
        np.savetxt(fh, verts, fmt="v %.6f %.6f %.6f")
        np.savetxt(fh, uv, fmt="vt %.6f %.6f")
        np.savetxt(fh, faces, fmt="f %d/%d %d/%d %d/%d")
    mtl_path.write_text(f"newmtl scan\nKa 1 1 1\nKd 1 1 1\nmap_Kd {texture_name}\n")
    return {"obj": obj_path.name, "vertices": int(len(verts)), "faces": int(nf), "flip_v": flip_v}