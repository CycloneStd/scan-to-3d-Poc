import json
import shutil
import subprocess
from pathlib import Path

from src.cyclone_scan.config import ScanConfig
from src.cyclone_scan.runner import ColmapRunner


class ReconstructionPipeline:
    SUPPORTED_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"
    }

    def __init__(
        self,
        config: ScanConfig,
        *,
        use_gpu: bool = True,
        blender_executable: str | None = None,
        gltf_transform_executable: str = "gltf-transform",
    ) -> None:
        self.config = config
        self.runner = ColmapRunner(config.colmap_executable)
        self.use_gpu = use_gpu
        self.blender_executable = (
            blender_executable or shutil.which("blender")
        )
        self.gltf_transform_executable = gltf_transform_executable

        self.dense_dir = config.run_dir / "dense"
        self.web_asset_dir = config.run_dir / "web"
        self.fused_cloud = self.dense_dir / "fused.ply"
        self.mesh_path = self.dense_dir / "mesh.ply"
        self.textured_mesh_dir = self.dense_dir / "textured"
        self.textured_mesh = self.textured_mesh_dir / "mesh.ply"
        self.texture_atlas = self.textured_mesh_dir / "texture.png"
        self.raw_glb = self.web_asset_dir / "model-raw.glb"
        self.final_glb = self.web_asset_dir / "model.glb"

    def validate_inputs(self) -> None:
        if not self.config.image_dir.is_dir():
            raise FileNotFoundError(
                f"Image directory not found: {self.config.image_dir}"
            )

        images = [
            path for path in self.config.image_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in self.SUPPORTED_EXTENSIONS
        ]

        if len(images) < 2:
            raise ValueError(
                "At least two supported image files are required in "
                f"{self.config.image_dir}"
            )

        if self.config.database_path.exists():
            raise FileExistsError(
                f"Database already exists: {self.config.database_path}. "
                "Remove the previous run directory before starting again."
            )

    def _gpu_flag(self) -> str:
        return "1" if self.use_gpu else "0"

    def _require_file(self, path: Path, description: str) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(
                f"{description} was not produced or is empty: {path}"
            )

    def _run_external(
        self, executable: str, arguments: list[str]
    ) -> None:
        try:
            subprocess.run(
                [executable, *arguments],
                check=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Required executable not found: {executable}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Command failed with exit code {exc.returncode}: "
                f"{executable} {arguments}"
            ) from exc

    def verify_reconstruction(self) -> Path:
        for model_dir in sorted(self.config.sparse_dir.iterdir()):
            if not model_dir.is_dir():
                continue

            required = (
                model_dir / "cameras.bin",
                model_dir / "images.bin",
                model_dir / "points3D.bin",
            )

            if all(path.is_file() for path in required):
                return model_dir

        raise RuntimeError(
            "COLMAP did not produce a valid sparse model in "
            f"{self.config.sparse_dir}"
        )

    def _extract_features(self) -> None:
        print("Step 1/7: Extracting image features...")

        self.runner.run([
            "feature_extractor",
            "--database_path", str(self.config.database_path),
            "--image_path", str(self.config.image_dir),
            "--ImageReader.single_camera", "1",
            "--FeatureExtraction.use_gpu", self._gpu_flag(),
            "--FeatureExtraction.num_threads", "4",
        ])

    def _match_features(self) -> None:
        print("Step 2/7: Matching image features...")

        self.runner.run([
            "exhaustive_matcher",
            "--database_path", str(self.config.database_path),
            "--FeatureMatching.use_gpu", self._gpu_flag(),
            "--FeatureMatching.num_threads", "4",
        ])

    def _build_sparse_model(self) -> Path:
        print("Step 3/7: Building sparse reconstruction...")

        self.runner.run([
            "mapper",
            "--database_path", str(self.config.database_path),
            "--image_path", str(self.config.image_dir),
            "--output_path", str(self.config.sparse_dir),
        ])

        sparse_model = self.verify_reconstruction()
        print(f"Sparse model verified: {sparse_model}")
        return sparse_model

    def _build_dense_cloud(self, sparse_model: Path) -> None:
        print("Step 4/7: Building dense reconstruction...")

        self.dense_dir.mkdir(parents=True, exist_ok=True)

        self.runner.run([
            "image_undistorter",
            "--image_path", str(self.config.image_dir),
            "--input_path", str(sparse_model),
            "--output_path", str(self.dense_dir),
            "--output_type", "COLMAP",
            "--max_image_size", "2000",
        ])

        self.runner.run([
            "patch_match_stereo",
            "--workspace_path", str(self.dense_dir),
            "--workspace_format", "COLMAP",
            "--PatchMatchStereo.geom_consistency", "true",
        ])

        self.runner.run([
            "stereo_fusion",
            "--workspace_path", str(self.dense_dir),
            "--workspace_format", "COLMAP",
            "--input_type", "geometric",
            "--output_path", str(self.fused_cloud),
        ])

        self._require_file(self.fused_cloud, "Dense fused point cloud")

    def _build_textured_mesh(self) -> None:
        print("Step 5/5: Meshing and texturing...")

        self.runner.run([
            "poisson_mesher",
            "--input_path", str(self.fused_cloud),
            "--output_path", str(self.mesh_path),
        ])

        self._require_file(self.mesh_path, "Poisson mesh")

        self.textured_mesh_dir.mkdir(parents=True, exist_ok=True)

        self.runner.run([
            "mesh_texturer",
            "--workspace_path", str(self.dense_dir),
            "--input_path", str(self.mesh_path),
            "--output_path", str(self.textured_mesh_dir),
        ])

        self._require_file(
            self.textured_mesh,
            "Textured PLY mesh",
        )
        self._require_file(
            self.texture_atlas,
            "Texture atlas",
        )

        print(f"Textured mesh: {self.textured_mesh}")
        print(f"Texture atlas: {self.texture_atlas}")

    def _convert_obj_to_glb(self) -> None:
        print("Step 6/7: Converting textured mesh to GLB...")

        if not self.blender_executable:
            raise RuntimeError(
                "Blender was not found. Install Blender and either add it "
                "to PATH or pass blender_executable to the pipeline."
            )

        self.web_asset_dir.mkdir(parents=True, exist_ok=True)

        blender_script = f"""
import bpy

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

bpy.ops.wm.obj_import(filepath={json.dumps(str(self.textured_obj))})

bpy.ops.export_scene.gltf(
    filepath={json.dumps(str(self.raw_glb))},
    export_format="GLB",
    export_image_format="AUTO",
)
"""

        self._run_external(
            self.blender_executable,
            [
                "--background",
                "--python-expr",
                blender_script,
            ],
        )

        self._require_file(self.raw_glb, "Raw GLB export")

    def _optimize_glb(self) -> None:
        print("Step 7/7: Optimizing GLB for web...")

        self._run_external(
            self.gltf_transform_executable,
            [
                "optimize",
                str(self.raw_glb),
                str(self.final_glb),
                "--compress", "draco",
                "--texture-compress", "webp",
                "--texture-size", "1024",
            ],
        )

        self._require_file(self.final_glb, "Optimized GLB")
        size_mb = self.final_glb.stat().st_size / (1024 * 1024)

        print(f"Web-ready model: {self.final_glb}")
        print(f"Final file size: {size_mb:.2f} MB")

    def run(self) -> None:
        self.validate_inputs()
        self.config.prepare_directories()

        self._extract_features()
        self._match_features()
        sparse_model = self._build_sparse_model()
        self._build_dense_cloud(sparse_model)
        self._build_textured_mesh()
        self._convert_obj_to_glb()
        self._optimize_glb()