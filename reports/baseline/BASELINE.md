# Baseline report (local evidence only, 2026-10-28)

Source: `data/runs/south-building` (local copy; not modified). Measured with
`scripts/inspect_mesh.py`; JSON per file in this directory.

| File | Vertices | Faces | Extent (x,y,z) | Components | UV/texture |
|---|---|---|---|---|---|
| sparse/0/points.ply (point cloud) | 92,223 | - | 33 x 49 x 119 | - | - |
| sparse/0/mesh.ply (Poisson on sparse) | 3,102 | 6,169 | 42 x 51 x 41 | 3 | vertex colors |
| sparse/0/delaunay_mesh.ply | 38,241 | 76,409 | 22.6 x 26.5 x 57.4 | 16 | none |
| dense/textured/mesh.ply (final) | 72,444 | 76,409 | 18.3 x 5.7 x 16.1 | 7,930 | UV + 30 MB texture.png |

## Findings (measured)
1. **No dense reconstruction exists locally.** No `fused.ply`, no `.mvs`, no OBJ/MTL.
   The "textured" mesh has exactly the same face count (76,409) as the Delaunay mesh
   built from the *sparse* cloud, i.e. it is a textured sparse-Delaunay mesh. This is
   the main cause of "insufficient detail".
2. The final mesh is fragmented: 7,930 connected components for 76k faces; extent
   (18 x 5.7 x 16) differs from the Delaunay mesh (22 x 26 x 57), so it was trimmed/
   rebuilt and is not the same geometry - its bounds do not match the sparse model.
3. Sparse cloud bbox (z spans -39..80, 119 units) is much larger than the building:
   outlier points are present and no filtering is applied before meshing.
4. `scripts/mesh_sparse_cloud.py` uses a fixed normal radius of 0.5 in arbitrary
   COLMAP units (median Delaunay edge is ~0.02, Poisson mesh edge ~0.7), so normals
   and Poisson depth are not scale-aware. (Hypothesis consistent with the data, not proven.)
5. Non-watertight / vertex-colour-only meshes are not themselves failures, but the
   final deliverable has no OBJ/MTL, which the README promises.
6. Invisible-mesh cause NOT yet established: bounds are finite and plausible, the
   centroid is near the origin; this needs a viewer-side check (not done).

## Tests
`pytest`: 26 passed, 2 skipped, 8 failed in base Python (cv2 missing).
In `cyclone-scan` env: 28 passed, 8 failed - all `tests/test_video.py`, error
`None has no attribute 'VideoCapture'`: **opencv is not installed in the env** although
`environment.yml` lists it. Not a code defect. Re-run after fixing env: pending.

## Environment problems found
- `cyclone-scan` has numpy 2.4.6 with open3d 0.18.0 (needs numpy<2); native crash
  0xc06d007f occurs during mesh sampling/rendering in `inspect_mesh.py`. Pin `numpy<2`.
- No scipy/networkx in env (trimesh graph functions unavailable).
- No GPU, COLMAP, OpenMVS or Blender locally.
