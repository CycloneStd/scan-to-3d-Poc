
from pathlib import Path

import open3d as o3d

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT = PROJECT_ROOT / "data/runs/south-building/sparse/0/points.ply"
OUTPUT = PROJECT_ROOT / "data/runs/south-building/sparse/0/mesh.ply"

print("Loading sparse point cloud...")
cloud = o3d.io.read_point_cloud(str(INPUT))

if cloud.is_empty():
    raise RuntimeError(f"No points found in {INPUT}")

print(f"Loaded {len(cloud.points):,} points.")
print("Estimating surface normals on CPU...")

cloud.estimate_normals(
    search_param=o3d.geometry.KDTreeSearchParamHybrid(
        radius=0.5,
        max_nn=30,
    )
)
cloud.orient_normals_consistent_tangent_plane(20)

print("Generating Poisson mesh...")

mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
    cloud,
    depth=8,
)

# Remove low-density vertices to reduce unsupported surface regions.
import numpy as np

densities = np.asarray(densities)
mesh.remove_vertices_by_mask(
    densities < np.quantile(densities, 0.05)
)
mesh.compute_vertex_normals()

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
if not o3d.io.write_triangle_mesh(str(OUTPUT), mesh):
    raise RuntimeError(f"Failed to write mesh to {OUTPUT}")

print(f"Mesh saved: {OUTPUT}")
print(f"Vertices: {len(mesh.vertices):,}")
print(f"Triangles: {len(mesh.triangles):,}")