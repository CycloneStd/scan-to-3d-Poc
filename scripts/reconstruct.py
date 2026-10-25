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

    fallback_win = Path(r"D:\Image-to-3D\COLMAP\COLMAP.bat")
    if fallback_win.exists():
        return fallback_win

    which_colmap = shutil.which("colmap")
    if which_colmap:
        return Path(which_colmap)

    return fallback_win


def find_default_input() -> Path:
    env_input = os.environ.get("SCAN_INPUT_DIR")
    if env_input and Path(env_input).exists():
        return Path(env_input)

    sample_dataset = Path(
        r"C:\Users\HP\Downloads\colmap-half-building\south-building\images"
    )
    if sample_dataset.exists():
        return sample_dataset

    return PROJECT_ROOT / "data" / "input"


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
        "--input-dir",
        type=Path,
        default=find_default_input(),
        help="Directory containing source photographs",
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
        help="Enable CUDA GPU acceleration (default: False, runs on CPU)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite previous reconstruction database and artifacts",
    )
    parser.add_argument(
        "--stage",
        choices=["all", "sparse", "mesh", "texture", "export", "view"],
        default="all",
        help="Run full pipeline or a specific stage",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = ScanConfig(
        project_root=PROJECT_ROOT,
        colmap_executable=args.colmap,
        run_name=args.run_name,
        input_dir=args.input_dir,
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

    if args.stage == "all":
        pipeline.run()
    elif args.stage == "sparse":
        pipeline.validate_inputs()
        config.prepare_directories()
        pipeline._extract_features()
        pipeline._match_features()
        model = pipeline._build_sparse_model()
        pipeline._export_sparse_to_ply(model)
    elif args.stage == "mesh":
        model = pipeline.verify_reconstruction()
        pipeline._build_mesh(model)
    elif args.stage == "texture":
        pipeline._build_textured_mesh()
    elif args.stage == "export":
        pipeline._export_glb()
    elif args.stage == "view":
        viewer = pipeline._create_web_viewer()
        print(f"Open in browser: file:///{viewer.as_posix()}")


if __name__ == "__main__":
    main()