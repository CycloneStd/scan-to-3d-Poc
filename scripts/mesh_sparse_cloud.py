import argparse
from pathlib import Path
import subprocess
import numpy as np

try:
    import open3d as o3d
except ImportError as exc:
    raise ImportError(
        "open3d is required for mesh_sparse_cloud.py. "
        "Install with: pip install open3d"
    ) from exc

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Poisson surface mesh from sparse point cloud using Open3D"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data/runs/south-building/sparse/0/points.ply",
        help="Path to sparse points.ply file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data/runs/south-building/sparse/0/mesh.ply",
        help="Path for generated mesh.ply output",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=9,
        help="Poisson octree reconstruction depth (default: 9)",
    )
    parser.add_argument(
        "--trim-quantile",
        type=float,
        default=0.05,
        help="Quantile threshold to prune low density vertices (default: 0.05)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input
    output_path = args.output

    if not input_path.exists():
        sparse_dir = input_path.parent
        bin_model = sparse_dir / "points3D.bin"
        if bin_model.exists():
            print(f"{input_path} not found. Attempting COLMAP model_converter conversion...")
            colmap_cmd = [
                r"D:\Image-to-3D\COLMAP\COLMAP.bat",
                "model_converter",
                "--input_path", str(sparse_dir),
                "--output_path", str(input_path),
                "--output_type", "PLY",
            ]
            subprocess.run(colmap_cmd, check=True)

    print(f"Loading sparse point cloud from {input_path}...")
    cloud = o3d.io.read_point_cloud(str(input_path))

    if cloud.is_empty():
        raise RuntimeError(f"No points found in {input_path}")

    print(f"Loaded {len(cloud.points):,} points.")
    print("Estimating surface normals on CPU...")

    cloud.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(
            radius=0.5,
            max_nn=30,
        )
    )
    cloud.orient_normals_consistent_tangent_plane(20)

    print(f"Generating Poisson mesh (depth={args.depth})...")
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        cloud,
        depth=args.depth,
    )

    densities = np.asarray(densities)
    if args.trim_quantile > 0:
        threshold = np.quantile(densities, args.trim_quantile)
        mesh.remove_vertices_by_mask(densities < threshold)

    mesh.compute_vertex_normals()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(output_path), mesh):
        raise RuntimeError(f"Failed to write mesh to {output_path}")

    print(f"Mesh saved: {output_path}")
    print(f"Vertices: {len(mesh.vertices):,}")
    print(f"Triangles: {len(mesh.triangles):,}")


if __name__ == "__main__":
    main()