import html
import json
from pathlib import Path
import shutil
import subprocess

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
        use_gpu: bool = False,
        overwrite: bool = False,
        blender_executable: str | None = None,
        gltf_transform_executable: str = "gltf-transform",
    ) -> None:
        self.config = config
        self.runner = ColmapRunner(config.colmap_executable)
        self.use_gpu = use_gpu
        self.overwrite = overwrite
        self.blender_executable = blender_executable or shutil.which("blender")
        self.gltf_transform_executable = gltf_transform_executable

        self.dense_dir = config.dense_dir
        self.web_asset_dir = config.web_dir
        self.fused_cloud = self.dense_dir / "fused.ply"
        self.mesh_path = self.dense_dir / "mesh.ply"
        self.textured_mesh_dir = config.textured_dir
        self.textured_mesh = config.textured_mesh
        self.texture_atlas = config.texture_atlas
        self.raw_glb = self.web_asset_dir / "model-raw.glb"
        self.final_glb = config.final_glb

    def validate_inputs(self) -> None:
        if not self.config.image_dir.exists():
            raise FileNotFoundError(
                f"Image directory does not exist: {self.config.image_dir}"
            )

        images = [
            path for path in self.config.image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS
        ]

        if len(images) < 2:
            raise ValueError(
                "At least two supported image files are required in "
                f"{self.config.image_dir}"
            )

        if self.config.database_path.exists() and not self.overwrite:
            raise FileExistsError(
                f"COLMAP database already exists: {self.config.database_path}. "
                "Remove the previous run directory before starting again, "
                "or run with overwrite=True."
            )

    def _gpu_flag(self) -> str:
        return "1" if self.use_gpu else "0"

    def _require_file(self, path: Path, description: str) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(
                f"{description} was not produced or is empty: {path}"
            )

    def _run_external(self, executable: str, arguments: list[str]) -> None:
        resolved = shutil.which(executable)
        if not resolved:
            raise RuntimeError(f"Required executable not found: {executable}")
        try:
            subprocess.run([resolved, *arguments], check=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Command failed with exit code {exc.returncode}: "
                f"{executable} {' '.join(arguments)}"
            ) from exc

    def verify_reconstruction(self) -> Path:
        if not self.config.sparse_dir.exists():
            raise RuntimeError(
                f"Sparse directory does not exist: {self.config.sparse_dir}"
            )

        valid_models: list[tuple[Path, int]] = []
        for model_dir in sorted(self.config.sparse_dir.iterdir()):
            if not model_dir.is_dir():
                continue

            bin_files = (
                model_dir / "cameras.bin",
                model_dir / "images.bin",
                model_dir / "points3D.bin",
            )
            txt_files = (
                model_dir / "cameras.txt",
                model_dir / "images.txt",
                model_dir / "points3D.txt",
            )

            if all(p.is_file() for p in bin_files):
                pts_size = (model_dir / "points3D.bin").stat().st_size
                valid_models.append((model_dir, pts_size))
            elif all(p.is_file() for p in txt_files):
                pts_size = (model_dir / "points3D.txt").stat().st_size
                valid_models.append((model_dir, pts_size))

        if not valid_models:
            raise RuntimeError(
                "COLMAP did not produce a valid sparse model in "
                f"{self.config.sparse_dir}"
            )

        # Select the model with the largest points file (most reconstructed points)
        best_model = max(valid_models, key=lambda item: item[1])[0]
        return best_model

    def _extract_features(self) -> None:
        print("Step 1/7: Extracting image features...")
        self.runner.run([
            "feature_extractor",
            "--database_path", str(self.config.database_path),
            "--image_path", str(self.config.image_dir),
            "--ImageReader.single_camera", "1",
            "--FeatureExtraction.use_gpu", self._gpu_flag(),
            "--FeatureExtraction.gpu_index", "0" if self.use_gpu else "-1",
            "--FeatureExtraction.num_threads", "8",
        ])

    def _match_features(self) -> None:
        print("Step 2/7: Matching image features...")
        self.runner.run([
            "exhaustive_matcher",
            "--database_path", str(self.config.database_path),
            "--FeatureMatching.use_gpu", self._gpu_flag(),
            "--FeatureMatching.gpu_index", "0" if self.use_gpu else "-1",
            "--FeatureMatching.num_threads", "8",
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

    def _export_sparse_to_ply(self, sparse_model: Path) -> Path:
        print("Step 4/7: Exporting sparse points to PLY...")
        ply_output = sparse_model / "points.ply"
        self.runner.run([
            "model_converter",
            "--input_path", str(sparse_model),
            "--output_path", str(ply_output),
            "--output_type", "PLY",
        ])
        self._require_file(ply_output, "Exported sparse point cloud")
        print(f"Sparse point cloud exported: {ply_output}")
        return ply_output

    def _undistort_images(self, sparse_model: Path) -> None:
        print("Undistorting images for dense/mesh texturing...")
        self.dense_dir.mkdir(parents=True, exist_ok=True)
        self.runner.run([
            "image_undistorter",
            "--image_path", str(self.config.image_dir),
            "--input_path", str(sparse_model),
            "--output_path", str(self.dense_dir),
            "--output_type", "COLMAP",
            "--max_image_size", "2000",
        ])

    def _build_mesh(self, sparse_model: Path) -> Path:
        print("Step 5/7: Generating surface mesh...")
        self._undistort_images(sparse_model)

        if self.use_gpu:
            print("Running MVS dense reconstruction (GPU mode)...")
            self.runner.run([
                "patch_match_stereo",
                "--PatchMatchStereo.gpu_index", "0",
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
            self.runner.run([
                "poisson_mesher",
                "--input_path", str(self.fused_cloud),
                "--output_path", str(self.mesh_path),
            ])
        else:
            print("Running Delaunay surface meshing on CPU...")
            self.runner.run([
                "delaunay_mesher",
                "--input_type", "sparse",
                "--input_path", str(sparse_model),
                "--output_path", str(self.mesh_path),
            ])

        self._require_file(self.mesh_path, "Surface mesh")
        print(f"Mesh generated: {self.mesh_path}")
        return self.mesh_path

    def _build_textured_mesh(self) -> None:
        print("Step 6/7: Texturing surface mesh...")
        self.textured_mesh_dir.mkdir(parents=True, exist_ok=True)

        self.runner.run([
            "mesh_texturer",
            "--workspace_path", str(self.dense_dir),
            "--input_path", str(self.mesh_path),
            "--output_path", str(self.textured_mesh_dir),
        ])

        self._require_file(self.textured_mesh, "Textured PLY mesh")
        self._require_file(self.texture_atlas, "Texture atlas")

        print(f"Textured mesh: {self.textured_mesh}")
        print(f"Texture atlas: {self.texture_atlas}")

    def _export_glb(self) -> Path:
        print("Step 7/7: Converting to web-ready GLB model...")
        self.web_asset_dir.mkdir(parents=True, exist_ok=True)

        # 1. Native Python export using trimesh (fast, reliable, no Blender required)
        try:
            import trimesh
            mesh = trimesh.load(str(self.textured_mesh))
            target_path = self.raw_glb if shutil.which(self.gltf_transform_executable) else self.final_glb
            mesh.export(str(target_path))
            self._require_file(target_path, "GLB export")
            print(f"Exported GLB via trimesh: {target_path}")
        except Exception as exc:
            print(f"Trimesh export note: {exc}. Attempting Blender export if available...")
            if not self.blender_executable:
                raise RuntimeError(
                    "GLB export failed with trimesh, and Blender executable was not found."
                ) from exc

            blender_script = f"""
import bpy

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

try:
    bpy.ops.wm.ply_import(filepath={json.dumps(str(self.textured_mesh))})
except Exception:
    bpy.ops.import_mesh.ply(filepath={json.dumps(str(self.textured_mesh))})

bpy.ops.export_scene.gltf(
    filepath={json.dumps(str(self.final_glb))},
    export_format="GLB",
    export_image_format="AUTO",
)
"""
            self._run_external(
                self.blender_executable,
                ["--background", "--python-expr", blender_script],
            )
            self._require_file(self.final_glb, "Blender GLB export")

        # 2. Optional gltf-transform optimization if tool is installed
        if shutil.which(self.gltf_transform_executable) and self.raw_glb.is_file():
            try:
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
                print(f"Optimized with gltf-transform: {self.final_glb}")
            except Exception as opt_err:
                print(f"gltf-transform optimization skipped: {opt_err}")
                shutil.copyfile(self.raw_glb, self.final_glb)

        self._require_file(self.final_glb, "Final GLB model")
        size_mb = self.final_glb.stat().st_size / (1024 * 1024)
        print(f"Final 3D Web Model: {self.final_glb} ({size_mb:.2f} MB)")

        # 3. Create an HTML 3D Web Viewer
        self._create_web_viewer()
        return self.final_glb

    def _create_web_viewer(self) -> Path:
        viewer_html = self.web_asset_dir / "index.html"
        model_filename = self.final_glb.name

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3D Building Reconstruction Viewer</title>
    <script type="module" src="https://ajax.googleapis.com/ajax/libs/model-viewer/3.4.0/model-viewer.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            width: 100vw;
            height: 100vh;
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            overflow: hidden;
        }}
        model-viewer {{
            width: 100%;
            height: 100%;
        }}
        .header {{
            position: absolute;
            top: 20px;
            left: 20px;
            color: #f8fafc;
            background: rgba(15, 23, 42, 0.75);
            backdrop-filter: blur(8px);
            padding: 12px 20px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.1);
            pointer-events: none;
        }}
        .header h1 {{
            margin: 0 0 4px 0;
            font-size: 1.1rem;
            font-weight: 600;
        }}
        .header p {{
            margin: 0;
            font-size: 0.85rem;
            color: #94a3b8;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Scan-to-3D Model Viewer</h1>
        <p>Interactive 3D reconstruction preview. Click and drag to rotate, scroll to zoom.</p>
    </div>
    <model-viewer
        src="{html.escape(model_filename)}"
        alt="3D Building Model"
        auto-rotate
        camera-controls
        shadow-intensity="1.2"
        exposure="1"
        camera-orbit="45deg 75deg auto"
        interaction-prompt="auto">
    </model-viewer>
</body>
</html>
"""
        viewer_html.write_text(html_content, encoding="utf-8")
        print(f"Interactive Web 3D Viewer generated: {viewer_html}")
        return viewer_html

    def run(self) -> None:
        if self.overwrite and self.config.database_path.exists():
            print(f"Removing previous database for fresh run: {self.config.database_path}")
            self.config.database_path.unlink()

        self.validate_inputs()
        self.config.prepare_directories()

        self._extract_features()
        self._match_features()
        sparse_model = self._build_sparse_model()
        self._export_sparse_to_ply(sparse_model)

        self._build_mesh(sparse_model)
        self._build_textured_mesh()
        self._export_glb()
        print("Pipeline execution completed successfully!")