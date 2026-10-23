import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.cyclone_scan.config import ScanConfig
from src.cyclone_scan.pipeline import ReconstructionPipeline


def main() -> None:
    config = ScanConfig(
        project_root=PROJECT_ROOT,
        colmap_executable=Path(
            r"D:\Image-to-3D\COLMAP\COLMAP.bat"
        ),
        run_name="south-building",
        input_dir=Path(
            r"C:\Users\HP\Downloads\colmap-half-building\south-building\images"
        ),
    )

    use_gpu = False

    pipeline = ReconstructionPipeline(
        config,
        use_gpu=use_gpu,
        blender_executable=os.environ.get("BLENDER_EXECUTABLE"),
        gltf_transform_executable=os.environ.get(
            "GLTF_TRANSFORM_EXECUTABLE", "gltf-transform"
        ),
    )

    pipeline.run()


if __name__ == "__main__":
    main()