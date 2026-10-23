from pathlib import Path

from src.cyclone_scan.config import ScanConfig
from src.cyclone_scan.pipeline import ReconstructionPipeline


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    config = ScanConfig(
        project_root=project_root,
        colmap_executable=Path(
            r"D:\Image-to-3D\COLMAP\COLMAP.bat"
        ),
    )

    pipeline = ReconstructionPipeline(config)
    pipeline.run()


if __name__ == "__main__":
    main()