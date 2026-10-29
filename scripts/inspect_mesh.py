"""Standalone mesh/point-cloud inspector (no dependency on cyclone_scan).

Usage: python scripts/inspect_mesh.py MESH [--out DIR] [--json report.json]

Loads a PLY/OBJ/GLB with trimesh, reports geometry/texture health, and renders
orthographic-style diagnostic views (front/side/top + oblique) with a pure
numpy/Pillow point splatter, so a mesh that is "invisible" in a viewer can be
diagnosed from raw coordinates.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image


def load(path):
    obj = trimesh.load(str(path), process=False)
    if isinstance(obj, trimesh.Scene):
        obj = trimesh.util.concatenate([g for g in obj.geometry.values()])
    return obj


def vertex_components(faces, n):
    """Components of the vertex-sharing graph via numpy label propagation
    (avoids needing scipy/networkx, which trimesh would otherwise require)."""
    label = np.arange(n)
    used = np.unique(faces)
    while True:
        m = label[faces].min(1)
        new = label.copy()
        for k in range(3):
            np.minimum.at(new, faces[:, k], m)
        new = new[new]
        if (new == label).all():
            break
        label = new
    return int(len(np.unique(label[used])))


def report(obj, path):
    r = {"file": str(path), "bytes": Path(path).stat().st_size,
         "type": type(obj).__name__}
    v = np.asarray(obj.vertices)
    r["vertices"] = int(len(v))
    r["finite"] = bool(np.isfinite(v).all())
    if len(v):
        lo, hi = v.min(0), v.max(0)
        r["bbox_min"], r["bbox_max"] = lo.tolist(), hi.tolist()
        r["extent"] = (hi - lo).tolist()
        r["centroid"] = v.mean(0).tolist()
        r["distance_of_centroid_from_origin"] = float(np.linalg.norm(v.mean(0)))
    if isinstance(obj, trimesh.Trimesh):
        f = np.asarray(obj.faces)
        r["faces"] = int(len(f))
        if len(f):
            r["index_in_range"] = bool(f.max() < len(v) and f.min() >= 0)
            area = obj.area_faces
            r["degenerate_faces"] = int((area < 1e-12).sum())
            r["surface_area"] = float(obj.area)
            # Computed with plain numpy: trimesh's einsum-based row_norm
            # crashed natively (0xc06d007f) in the cyclone-scan env.
            e = v[f[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)]
            r["median_edge_length"] = float(
                np.median(np.sqrt(((e[:, 0] - e[:, 1]) ** 2).sum(1))))
            r["connected_components"] = vertex_components(f, len(v))
            r["watertight"] = bool(obj.is_watertight)
            r["winding_consistent"] = bool(obj.is_winding_consistent)
            r["has_vertex_colors"] = bool(
                getattr(obj.visual, "kind", None) == "vertex")
        vis = obj.visual
        r["visual_kind"] = getattr(vis, "kind", None)
        uv = getattr(vis, "uv", None)
        r["has_uv"] = uv is not None
        if uv is not None:
            uv = np.asarray(uv)
            r["uv_range"] = [uv.min(0).tolist(), uv.max(0).tolist()]
        mat = getattr(vis, "material", None)
        img = getattr(mat, "image", None) or getattr(
            mat, "baseColorTexture", None)
        if img is not None:
            a = np.asarray(img.convert("RGB"))
            r["texture_size"] = list(img.size)
            r["texture_blank_fraction"] = float((a.sum(-1) == 0).mean())
    return r


def render(points, colors, axes, size=900):
    p = points[:, list(axes)]
    d = points[:, [i for i in range(3) if i not in axes][0]]
    lo, hi = np.percentile(p, 0.5, 0), np.percentile(p, 99.5, 0)
    s = (size - 20) / max((hi - lo).max(), 1e-9)
    xy = ((p - lo) * s + 10).astype(int)
    ok = (xy >= 0).all(1) & (xy < size).all(1)
    order = np.argsort(d[ok])
    xy, c = xy[ok][order], colors[ok][order]
    img = np.full((size, size, 3), 255, np.uint8)
    img[size - 1 - xy[:, 1], xy[:, 0]] = c
    return Image.fromarray(img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mesh")
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--samples", type=int, default=600000)
    a = ap.parse_args()
    obj = load(a.mesh)
    rep = report(obj, a.mesh)
    print(json.dumps(rep, indent=2))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=2))
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        if isinstance(obj, trimesh.Trimesh) and len(obj.faces):
            pts, fi = trimesh.sample.sample_surface(obj, a.samples)
            n = obj.face_normals[fi]
            shade = np.clip(0.35 + 0.65 * np.abs(n @ np.array([0.3, 0.5, 0.8])
                                                  / 1.0), 0, 1)
            grey = (shade[:, None] * 200).astype(np.uint8).repeat(3, 1)
            cols = grey
            try:
                cols = obj.visual.to_color().vertex_colors[:, :3]
                _ = cols
                cols = np.asarray(
                    trimesh.visual.color.interpolate(shade, "gray"))[:, :3]
                cols = grey
            except Exception:
                pass
            textured = None
            try:
                col = obj.visual.to_color()
                if col.kind == "vertex":
                    vc = np.asarray(col.vertex_colors)[:, :3]
                    bary = obj.faces[fi][:, 0]
                    textured = vc[bary]
            except Exception:
                pass
        else:
            pts = np.asarray(obj.vertices)
            if len(pts) > a.samples:
                pts = pts[np.random.default_rng(0).choice(len(pts), a.samples, False)]
            cols = (np.asarray(obj.colors)[:, :3] if hasattr(obj, "colors")
                    and len(obj.colors) else
                    np.full((len(pts), 3), 120, np.uint8))
            textured = None
        views = {"front_xy": (0, 1), "side_zy": (2, 1), "top_xz": (0, 2)}
        for name, ax in views.items():
            render(pts, cols, ax).save(out / f"{name}_geometry.png")
            if textured is not None:
                render(pts, textured, ax).save(out / f"{name}_color.png")
        print("wrote views to", out)


if __name__ == "__main__":
    main()
