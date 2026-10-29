import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.splat_reconstruction.pipeline import PipelineConfig, SplatPipeline
from src.splat_reconstruction.video import VideoConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a COLMAP camera baseline and train a gsplat 3D Gaussian scene."
    )
    parser.add_argument("--run-name", required=True, help="Unique name for this run.")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "runs",
        help="Directory under which the run folder will be created.",
    )
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--input-dir", type=Path, help="Folder of overlapping photos.")
    sources.add_argument("--input-video", type=Path, help="Video to sample with FFmpeg.")
    parser.add_argument(
        "--colmap",
        default=os.environ.get("COLMAP_EXECUTABLE", "colmap"),
        help="COLMAP executable path.",
    )
    parser.add_argument(
        "--gsplat-trainer",
        type=Path,
        default=os.environ.get("GSPLAT_TRAINER"),
        required=os.environ.get("GSPLAT_TRAINER") is None,
        help="Path to gsplat examples/simple_trainer.py.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable with CUDA-enabled PyTorch and gsplat installed.",
    )
    parser.add_argument(
        "--mapper",
        choices=["global_mapper", "mapper"],
        default="global_mapper",
        help="COLMAP global mapper (GLOMAP successor) or incremental mapper.",
    )
    parser.add_argument(
        "--matching",
        choices=["exhaustive", "sequential"],
        help="Defaults to sequential for video and exhaustive for photos.",
    )
    parser.add_argument("--overlap", type=int, default=5)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--gpu-features", action="store_true")
    parser.add_argument("--steps", type=int, default=7000)
    parser.add_argument("--fps", type=float, default=3.0)
    parser.add_argument("--max-dimension", type=int, default=1920)
    parser.add_argument("--min-sharpness", type=float, default=40.0)
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    video = VideoConfig(
        fps=args.fps,
        max_dimension=args.max_dimension,
        min_sharpness=args.min_sharpness,
        jpeg_quality=args.jpeg_quality,
        ffmpeg=args.ffmpeg,
        ffprobe=args.ffprobe,
    )
    config = PipelineConfig(
        project_dir=args.project_dir,
        run_name=args.run_name,
        colmap=args.colmap,
        gsplat_trainer=args.gsplat_trainer,
        python=args.python,
        input_dir=args.input_dir,
        input_video=args.input_video,
        mapper=args.mapper,
        matching=args.matching,
        overlap=args.overlap,
        threads=args.threads,
        gpu_features=args.gpu_features,
        max_steps=args.steps,
        video=video,
    )
    SplatPipeline(config).run()


if __name__ == "__main__":
    main()
