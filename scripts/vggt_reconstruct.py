"""AI geometry candidate: VGGT point maps -> filtered cloud -> Poisson mesh.

STATUS: written but NOT yet executed (needs a CUDA GPU; none locally).
VGGT is feed-forward inference with a pretrained model (no training or
fine-tuning). Its predicted points are *evidence with a confidence value*, not
ground truth; compare against the COLMAP/OpenMVS result before trusting them.

Output (in --out): points.ply (confidence-filtered, coloured), mesh.ply
(Poisson, trimmed by density), vggt_report.json. Coordinates are in VGGT's own
scale/frame (first-camera frame); they are NOT aligned to the COLMAP model.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--max-images", type=int, default=24,
                    help="evenly sampled subset; T4 (15 GB) memory limits this")
    ap.add_argument("--conf-percentile", type=float, default=50.0,
                    help="drop points below this confidence percentile")
    ap.add_argument("--poisson-depth", type=int, default=10)
    ap.add_argument("--trim-quantile", type=float, default=0.05)
    a = ap.parse_args()

    import torch
    import open3d as o3d
    from vggt.models.vggt import VGGT
    from vggt.utils.load_fn import load_and_preprocess_images

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU required for VGGT (torch.cuda.is_available() is False)")
    if a.out.exists() and any(a.out.iterdir()):
        raise SystemExit(f"{a.out} is not empty; use a new output directory")
    a.out.mkdir(parents=True)

    paths = sorted(p for p in a.images.iterdir()
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if len(paths) < 2:
        raise SystemExit("need at least 2 images")
    idx = np.unique(np.linspace(0, len(paths) - 1,
                                min(a.max_images, len(paths))).round().astype(int))
    chosen = [str(paths[i]) for i in idx]

    dev = "cuda"
    dtype = (torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8
             else torch.float16)
    t0 = time.time()
    model = VGGT.from_pretrained("facebook/VGGT-1B").to(dev).eval()
    images = load_and_preprocess_images(chosen).to(dev)
    with torch.no_grad(), torch.autocast("cuda", dtype=dtype):
        pred = model(images)
    peak = torch.cuda.max_memory_allocated() / 2**30
    infer_s = time.time() - t0

    pts = pred["world_points"].float().cpu().numpy().reshape(-1, 3)
    conf = pred["world_points_conf"].float().cpu().numpy().reshape(-1)
    col = (images.float().cpu().permute(0, 2, 3, 1).numpy().reshape(-1, 3)
           .clip(0, 1))
    finite = np.isfinite(pts).all(1)
    thr = np.percentile(conf[finite], a.conf_percentile)
    keep = finite & (conf >= thr)

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts[keep].astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(col[keep].astype(np.float64))
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=30, std_ratio=2.0)
    # scale-aware normal radius: 3x mean nearest-neighbour distance
    nn = np.asarray(pcd.compute_nearest_neighbor_distance())
    radius = float(3 * nn.mean())
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=40))
    pcd.orient_normals_towards_camera_location(np.zeros(3))
    o3d.io.write_point_cloud(str(a.out / "points.ply"), pcd)

    mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=a.poisson_depth)
    dens = np.asarray(dens)
    mesh.remove_vertices_by_mask(dens < np.quantile(dens, a.trim_quantile))
    o3d.io.write_triangle_mesh(str(a.out / "mesh.ply"), mesh)

    rep = dict(images_used=len(chosen), points_raw=int(finite.sum()),
               points_kept=len(pcd.points), conf_threshold=float(thr),
               normal_radius=radius, mesh_vertices=len(mesh.vertices),
               mesh_faces=len(mesh.triangles), inference_seconds=round(infer_s, 1),
               peak_gpu_gib=round(peak, 2), model="facebook/VGGT-1B",
               note="VGGT frame/scale; not aligned to COLMAP")
    (a.out / "vggt_report.json").write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
