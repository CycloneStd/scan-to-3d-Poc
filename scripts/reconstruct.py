import argparse
import os
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.cyclone_scan.config import ScanConfig
from src.cyclone_scan.pipeline import ReconstructionPipeline


def find_default_colmap() -> Path:
    env_path = os.environ.get("COLMAP_EXECUTABLE")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    which_colmap = shutil.which("colmap")
    if which_colmap:
        return Path(which_colmap)

    return Path("colmap")


def find_default_input(project_root: Path = PROJECT_ROOT) -> Path:
    env_input = os.environ.get("SCAN_INPUT_DIR")
    if env_input and Path(env_input).exists():
        return Path(env_input)

    return project_root / "data" / "input"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Cyclone Scan 3D photogrammetry pipeline"
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="south-building",
        help="Name of this reconstruction run (default: south-building)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Root directory for run artifacts (default: repository root)",
    )
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Directory containing source photographs (default: data/input)",
    )
    source_group.add_argument(
        "--input-video",
        type=Path,
        help="Video to sample into images before reconstruction",
    )
    parser.add_argument(
        "--colmap",
        type=Path,
        default=find_default_colmap(),
        help="Path to COLMAP executable or COLMAP.bat",
    )
    parser.add_argument(
        "--use-gpu",
        action="store_true",
        default=False,
        help="Request GPU acceleration for COLMAP feature extraction",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Allow replacement of incomplete stage outputs and extracted frames",
    )
    parser.add_argument(
        "--stage",
        choices=[
            "all",
            "preprocess",
            "sparse",
            "dense",
            "mesh",
            "texture",
            "export",
            "view",
        ],
        default="all",
        help="Run full pipeline or a specific stage",
    )
    parser.add_argument("--target-fps", type=float, default=3.0)
    parser.add_argument("--max-image-dimension", type=int, default=1920)
    parser.add_argument(
        "--image-format",
        choices=["jpg", "png", "bmp", "tif"],
        default="jpg",
    )
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument("--sequential-overlap", type=int, default=5)
    parser.add_argument("--num-threads", type=int, default=8)
    parser.add_argument(
        "--densify-option",
        action="append",
        default=[],
        help="Additional verified OpenMVS DensifyPointCloud argument; repeat per token",
    )
    parser.add_argument(
        "--reconstruct-mesh-option",
        action="append",
        default=[],
        help="Additional verified OpenMVS ReconstructMesh argument; repeat per token",
    )
    parser.add_argument(
        "--texture-option",
        action="append",
        default=[],
        help="Additional verified OpenMVS TextureMesh argument; repeat per token",
    )
    parser.add_argument(
        "--interface-colmap",
        type=Path,
        default=os.environ.get("INTERFACE_COLMAP_EXECUTABLE", "InterfaceCOLMAP"),
    )
    parser.add_argument(
        "--densify-point-cloud",
        type=Path,
        default=os.environ.get("DENSIFY_POINT_CLOUD_EXECUTABLE", "DensifyPointCloud"),
    )
    parser.add_argument(
        "--reconstruct-mesh",
        type=Path,
        default=os.environ.get("RECONSTRUCT_MESH_EXECUTABLE", "ReconstructMesh"),
    )
    parser.add_argument(
        "--texture-mesh",
        type=Path,
        default=os.environ.get("TEXTURE_MESH_EXECUTABLE", "TextureMesh"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    run_name = args.run_name
    input_dir = args.input_dir or find_default_input(args.project_root)
    if args.input_video:
        input_dir = args.project_root / "data" / "runs" / run_name / "frames"

    config = ScanConfig(
        project_root=args.project_root,
        colmap_executable=args.colmap,
        run_name=run_name,
        input_dir=input_dir,
        interface_colmap_executable=args.interface_colmap,
        densify_point_cloud_executable=args.densify_point_cloud,
        reconstruct_mesh_executable=args.reconstruct_mesh,
        texture_mesh_executable=args.texture_mesh,
        sequential_overlap=args.sequential_overlap,
        num_threads=args.num_threads,
        max_image_size=args.max_image_dimension,
        densify_options=tuple(args.densify_option),
        reconstruct_mesh_options=tuple(args.reconstruct_mesh_option),
        texture_options=tuple(args.texture_option),
    )

    pipeline = ReconstructionPipeline(
        config,
        use_gpu=args.use_gpu,
        overwrite=args.overwrite,
        blender_executable=os.environ.get("BLENDER_EXECUTABLE"),
        gltf_transform_executable=os.environ.get(
            "GLTF_TRANSFORM_EXECUTABLE", "gltf-transform"
        ),
    )

    if args.input_video:
        from time import perf_counter

        from src.cyclone_scan.video import (
            VideoPreprocessingConfig,
            VideoPreprocessor,
        )

        started = perf_counter()
        report = VideoPreprocessor(
            VideoPreprocessingConfig(
                target_fps=args.target_fps,
                max_dimension=args.max_image_dimension,
                image_format=args.image_format,
                jpeg_quality=args.jpeg_quality,
                overwrite=args.overwrite,
            )
        ).extract(args.input_video, input_dir)
        pipeline.record_stage_result(
            "video_preprocessing",
            {
                "elapsed_seconds": round(perf_counter() - started, 3),
                "input_video": str(report.input_video),
                "output_directory": str(report.output_dir),
                "input_images": report.extracted_frames,
                "output_bytes": sum(
                    frame_path.stat().st_size for frame_path in report.frame_paths
                ),
                "effective_fps": report.effective_fps,
                "source_fps": report.source_fps,
                "source_frame_count": report.source_frame_count,
                "source_dimensions": report.source_dimensions,
                "output_dimensions": report.output_dimensions,
            },
        )
        print(
            f"Extracted {report.extracted_frames} frames at "
            f"{report.effective_fps:.2f} effective FPS; "
            f"output dimensions: {report.output_dimensions[0]}x"
            f"{report.output_dimensions[1]}"
        )
    elif args.stage == "preprocess":
        raise ValueError("--stage preprocess requires --input-video.")

    if args.stage != "preprocess":
        pipeline.run(args.stage)


if __name__ == "__main__":
    main()