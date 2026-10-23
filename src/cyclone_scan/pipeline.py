from pathlib import Path

from src.cyclone_scan.config import ScanConfig
from src.cyclone_scan.runner import ColmapRunner


class ReconstructionPipeline:
    SUPPORTED_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".bmp",
    }

    def __init__(self, config: ScanConfig) -> None:
        self.config = config
        self.runner = ColmapRunner(config.colmap_executable)

    def validate_inputs(self) -> None:
        if not self.config.image_dir.is_dir():
            raise FileNotFoundError(
                f"Image directory does not exist: "
                f"{self.config.image_dir}"
            )

        images = [
            path
            for path in self.config.image_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in self.SUPPORTED_EXTENSIONS
        ]

        if len(images) < 2:
            raise ValueError(
                "At least two supported image files are required "
                f"in {self.config.image_dir}"
            )

        if self.config.database_path.exists():
            raise FileExistsError(
                f"COLMAP database already exists: "
                f"{self.config.database_path}. "
                "Preserve or remove the previous run before retrying."
            )

    def run(self) -> None:
        self.validate_inputs()
        self.config.prepare_directories()

        common_database_args = [
            "--database_path",
            str(self.config.database_path),
        ]

        print("Step 1/3: Extracting image features...")
        self.runner.run(
            [
                "feature_extractor",
                *common_database_args,
                "--image_path",
                str(self.config.image_dir),
                "--ImageReader.single_camera",
                "1",
                "--FeatureExtraction.use_gpu",
                "0",
            ]
        )

        print("Step 2/3: Matching image features...")
        self.runner.run(
            [
                "exhaustive_matcher",
                *common_database_args,
                "--FeatureMatching.use_gpu",
                "0",
            ]
        )

        print("Step 3/3: Building sparse reconstruction...")
        self.runner.run(
            [
                "mapper",
                *common_database_args,
                "--image_path",
                str(self.config.image_dir),
                "--output_path",
                str(self.config.sparse_dir),
            ]
        )

        model_dir = self.verify_reconstruction()
        print("Sparse reconstruction Verified Successfully")
        print(f"Model directory: {model_dir}")

    def verify_reconstruction(self)-> Path: 
        if not self.config.sparse_dir.is_dir():
            raise RuntimeError(
                f"Sparse output directory is missing: "
                f"{self.config.sparse_dir}"
            )
        
        for model_dir in sorted(self.config.sparse_dir.iterdir()):
            if not model_dir.is_dir():
                continue

            required_files = {"cameras.bin", "images.bin", "points3D.bin"}

            if required_files.issubset(
                {Path.name for path in model_dir.iterdir() if path.is_file()}
            ):
                return model_dir

        raise RuntimeError(
            "COLMAP completed, but no valid sparse model was found. "
            "Check the image overlap and COLMAP logs."
        )