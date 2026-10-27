import html
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import time
from datetime import datetime, timezone
from typing import Callable

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
        self.logs_dir = config.run_dir / "logs"
        self.metadata_path = config.run_dir / "metadata.json"
        self._active_stage: str | None = None
        self._colmap_help_cache: dict[str, str] = {}
        self._metadata: dict = {"run_name": config.run_name, "stages": {}}
        if self.metadata_path.is_file():
            self._metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            self._metadata.setdefault("stages", {})

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

        if self.config.database_path.exists():
            saved_signature = self._metadata["stages"].get(
                "feature_extraction", {}
            ).get("input_signature")
            if not self._database_has_features() and not self.overwrite:
                raise FileExistsError(
                    f"COLMAP database already exists but has no reusable "
                    f"features: {self.config.database_path}"
                )
            if (
                self._database_has_features()
                and saved_signature != self._image_input_signature()
            ):
                raise FileExistsError(
                    f"COLMAP database belongs to a different or unverified "
                    f"image set: {self.config.database_path}. Use a new "
                    "run name to preserve both reconstructions."
                )

    def _gpu_flag(self) -> str:
        return "1" if self.use_gpu else "0"

    def _database_counts(self) -> dict[str, int]:
        if not self.config.database_path.is_file():
            return {"images": 0, "keypoints": 0, "matches": 0}
        try:
            with sqlite3.connect(self.config.database_path) as database:
                tables = {
                    row[0]
                    for row in database.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                counts = {}
                for table in ("images", "keypoints", "matches"):
                    if table not in tables:
                        counts[table] = 0
                        continue
                    columns = {
                        row[1]
                        for row in database.execute(f"PRAGMA table_info({table})")
                    }
                    if table == "matches" and {"rows", "cols"} <= columns:
                        query = (
                            "SELECT COUNT(*) FROM matches "
                            "WHERE rows > 0 AND cols > 0"
                        )
                    elif table == "keypoints" and "rows" in columns:
                        query = "SELECT COUNT(*) FROM keypoints WHERE rows > 0"
                    else:
                        query = f"SELECT COUNT(*) FROM {table}"
                    counts[table] = int(database.execute(query).fetchone()[0])
                return counts
        except sqlite3.Error as exc:
            raise RuntimeError(
                f"Unable to inspect COLMAP database {self.config.database_path}: {exc}"
            ) from exc

    def _database_has_features(self) -> bool:
        counts = self._database_counts()
        return counts["images"] >= 2 and counts["keypoints"] > 0

    def _database_has_matches(self) -> bool:
        counts = self._database_counts()
        return self._database_has_features() and counts["matches"] > 0

    def _image_input_signature(self) -> str:
        image_stats = [
            (
                path.name,
                path.stat().st_size,
                path.stat().st_mtime_ns,
            )
            for path in sorted(self.config.image_dir.iterdir())
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS
        ]
        signature_data = json.dumps(
            [str(self.config.image_dir.resolve()), image_stats],
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(signature_data).hexdigest()

    @staticmethod
    def _artifact_signature(paths: tuple[Path, ...], settings: object = None) -> str:
        artifact_stats = []
        for path in paths:
            if path.is_file():
                artifact_stats.append(
                    (str(path), path.stat().st_size, path.stat().st_mtime_ns)
                )
            elif path.is_dir():
                artifact_stats.append(
                    (
                        str(path),
                        [
                            (
                                str(child.relative_to(path)),
                                child.stat().st_size,
                                child.stat().st_mtime_ns,
                            )
                            for child in sorted(path.rglob("*"))
                            if child.is_file()
                        ],
                    )
                )
            else:
                artifact_stats.append((str(path), None, None))
        value = json.dumps(
            [artifact_stats, settings],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(value).hexdigest()

    def _write_metadata(self) -> None:
        self.config.run_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = self.metadata_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(self._metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(self.metadata_path)

    def _run_stage(
        self,
        name: str,
        operation: Callable[[], None],
        is_complete: Callable[[], bool],
        outputs: tuple[Path, ...] = (),
        *,
        allow_existing_outputs: bool = False,
        input_signature: str | None = None,
    ) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        stage_metrics = self._metadata["stages"].setdefault(name, {})
        if is_complete() and (
            input_signature is None
            or stage_metrics.get("input_signature") == input_signature
        ):
            stage_metrics.update(
                status="skipped",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            self._write_metadata()
            print(f"Skipping completed stage: {name}")
            return

        if (
            is_complete()
            and input_signature is not None
            and stage_metrics.get("input_signature") != input_signature
        ):
            raise FileExistsError(
                f"Stage '{name}' outputs were produced from different inputs "
                "or settings. Use a new run name to preserve the existing run."
            )

        if not self.overwrite and not allow_existing_outputs:
            existing_outputs = [
                path
                for path in outputs
                if path.exists()
                and (not path.is_dir() or any(path.iterdir()))
            ]
            if existing_outputs:
                raise FileExistsError(
                    f"Stage '{name}' has existing incomplete outputs: "
                    + ", ".join(str(path) for path in existing_outputs)
                    + ". Use overwrite=True to replace them."
                )

        started = time.perf_counter()
        stage_metrics.update(
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        if input_signature is not None:
            stage_metrics["input_signature"] = input_signature
        self._active_stage = name
        self._write_metadata()
        try:
            operation()
            if not is_complete():
                raise RuntimeError(f"Stage '{name}' did not produce valid outputs.")
        except Exception as exc:
            stage_metrics.update(
                status="failed",
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=str(exc),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            self._write_metadata()
            raise
        else:
            stage_metrics.update(
                status="completed",
                elapsed_seconds=round(time.perf_counter() - started, 3),
                outputs=[str(path) for path in outputs],
                output_sizes_bytes={
                    str(path): (
                        path.stat().st_size
                        if path.is_file()
                        else sum(
                            child.stat().st_size
                            for child in path.rglob("*")
                            if child.is_file()
                        )
                        if path.is_dir()
                        else 0
                    )
                    for path in outputs
                },
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            self._write_metadata()
        finally:
            self._active_stage = None

    def _log_path(self) -> Path | None:
        if self._active_stage is None:
            return None
        return self.logs_dir / f"{self._active_stage}.log"

    def _colmap_help(self, command: str) -> str:
        if command not in self._colmap_help_cache:
            self._colmap_help_cache[command] = self.runner.help_text(command)
        return self._colmap_help_cache[command]

    def _colmap_supports_option(self, command: str, option: str) -> bool:
        return option in self._colmap_help(command)

    def record_stage_result(self, name: str, metrics: dict) -> None:
        self._metadata["stages"][name] = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            **metrics,
        }
        self._write_metadata()

    def _require_file(self, path: Path, description: str) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(
                f"{description} was not produced or is empty: {path}"
            )

    def _run_external(self, executable: str | Path, arguments: list[str]) -> None:
        executable = str(executable)
        resolved = shutil.which(executable)
        if resolved is None and Path(executable).is_file():
            resolved = str(Path(executable).resolve())
        if not resolved:
            raise RuntimeError(f"Required executable not found: {executable}")
        command = [resolved, *arguments]
        if (
            os.name == "nt"
            and Path(resolved).suffix.lower() in {".bat", ".cmd"}
        ):
            command = [
                "cmd.exe",
                "/d",
                "/s",
                "/c",
                subprocess.list2cmdline(command),
            ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        log_path = self._log_path()
        command_output = "\n".join(
            output for output in (result.stdout, result.stderr) if output
        )
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(command_output, encoding="utf-8")
        if result.returncode != 0:
            tail = "\n".join(command_output.splitlines()[-30:])
            raise RuntimeError(
                f"Command failed with exit code {result.returncode}: "
                f"{subprocess.list2cmdline(command)}\n{tail}"
            )

    def _validate_openmvs_options(
        self, executable: str | Path, options: tuple[str, ...]
    ) -> None:
        option_names = [
            option.split("=", maxsplit=1)[0]
            for option in options
            if option.startswith("-")
        ]
        if not option_names:
            return
        executable = str(executable)
        resolved = shutil.which(executable)
        if resolved is None and Path(executable).is_file():
            resolved = str(Path(executable).resolve())
        if not resolved:
            raise RuntimeError(f"Required executable not found: {executable}")
        command = [resolved, "-h"]
        if os.name == "nt" and Path(resolved).suffix.lower() in {".bat", ".cmd"}:
            command = [
                "cmd.exe",
                "/d",
                "/s",
                "/c",
                subprocess.list2cmdline(command),
            ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        help_text = f"{result.stdout}\n{result.stderr}"
        if not help_text.strip():
            raise RuntimeError(
                f"Unable to inspect supported options for {executable}."
            )
        unsupported = [option for option in option_names if option not in help_text]
        if unsupported:
            raise ValueError(
                f"{executable} does not advertise configured option(s): "
                + ", ".join(unsupported)
            )

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

            if all(p.is_file() and p.stat().st_size > 0 for p in bin_files):
                registered_images, point_count = self._sparse_model_counts(model_dir)
                if registered_images > 0 and point_count > 0:
                    valid_models.append((model_dir, point_count))
            elif all(p.is_file() and p.stat().st_size > 0 for p in txt_files):
                registered_images, point_count = self._sparse_model_counts(model_dir)
                if registered_images > 0 and point_count > 0:
                    valid_models.append((model_dir, point_count))

        if not valid_models:
            raise RuntimeError(
                "COLMAP did not produce a valid sparse model in "
                f"{self.config.sparse_dir}"
            )

        # Prefer the model containing the greatest number of reconstructed points.
        best_model = max(valid_models, key=lambda item: item[1])[0]
        return best_model

    def _sparse_model_counts(self, model_dir: Path) -> tuple[int, int]:
        images_bin = model_dir / "images.bin"
        points_bin = model_dir / "points3D.bin"
        if images_bin.is_file() and points_bin.is_file():
            with images_bin.open("rb") as file:
                image_header = file.read(8)
            with points_bin.open("rb") as file:
                point_header = file.read(8)
            if len(image_header) == 8 and len(point_header) == 8:
                return (
                    struct.unpack("<Q", image_header)[0],
                    struct.unpack("<Q", point_header)[0],
                )

        images_text = model_dir / "images.txt"
        points_text = model_dir / "points3D.txt"
        registered = 0
        point_count = 0
        if images_text.is_file():
            with images_text.open(encoding="utf-8") as file:
                registered = sum(
                    1
                    for line in file
                    if line.strip()
                    and not line.lstrip().startswith("#")
                    and len(line.split()) >= 10
                )
        if points_text.is_file():
            with points_text.open(encoding="utf-8") as file:
                point_count = sum(
                    1
                    for line in file
                    if line.strip() and not line.lstrip().startswith("#")
                )
        return registered, point_count

    def _representative_image_dimensions(self) -> tuple[int, int] | None:
        image_paths = sorted(
            path
            for path in self.config.image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS
        )
        if not image_paths:
            return None
        from .video import cv2

        if cv2 is None:
            return None
        image = cv2.imread(str(image_paths[0]))
        if image is None:
            return None
        height, width = image.shape[:2]
        return width, height

    def _sparse_model_is_valid(self) -> bool:
        try:
            self.verify_reconstruction()
        except RuntimeError:
            return False
        return True

    def _undistorted_scene_is_valid(self) -> bool:
        image_dir = self.dense_dir / "images"
        sparse_dir = self.dense_dir / "sparse"
        if not image_dir.is_dir() or not sparse_dir.is_dir():
            return False

        image_count = sum(
            1
            for path in image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS
        )
        for model_dir in [sparse_dir, *sparse_dir.iterdir()]:
            if not model_dir.is_dir():
                continue
            binary_model = ("cameras.bin", "images.bin", "points3D.bin")
            text_model = ("cameras.txt", "images.txt", "points3D.txt")
            model_exists = any(
                all(
                    (model_dir / filename).is_file()
                    and (model_dir / filename).stat().st_size > 0
                    for filename in model_files
                )
                for model_files in (binary_model, text_model)
            )
            if model_exists:
                registered_images, point_count = self._sparse_model_counts(model_dir)
                return image_count >= 2 and registered_images > 0 and point_count > 0
        return False

    def _extract_features(self) -> None:
        print("Step 1/7: Extracting image features...")
        input_signature = self._artifact_signature(
            (self.config.image_dir,),
            {
                "images": self._image_input_signature(),
                "gpu": self.use_gpu,
                "threads": self.config.num_threads,
            },
        )

        def extract() -> None:
            command = "feature_extractor"
            arguments = [
                command,
                "--database_path", str(self.config.database_path),
                "--image_path", str(self.config.image_dir),
            ]
            optional_values = [
                ("--ImageReader.single_camera", "1"),
                ("--FeatureExtraction.use_gpu", self._gpu_flag()),
                (
                    "--FeatureExtraction.gpu_index",
                    "0" if self.use_gpu else "-1",
                ),
                (
                    "--FeatureExtraction.num_threads",
                    str(self.config.num_threads),
                ),
            ]
            for option, value in optional_values:
                if self._colmap_supports_option(command, option):
                    arguments.extend([option, value])
                elif option == "--FeatureExtraction.use_gpu" and self.use_gpu:
                    raise RuntimeError(
                        "This COLMAP build does not expose GPU feature extraction."
                    )
                else:
                    print(f"COLMAP does not expose {option}; using its default.")
            self.runner.run(arguments, log_path=self._log_path())

        self._run_stage(
            "feature_extraction",
            extract,
            self._database_has_features,
            (self.config.database_path,),
            allow_existing_outputs=True,
            input_signature=input_signature,
        )

    def _match_features(self) -> None:
        print("Step 2/7: Matching image features...")
        if not self._database_has_features():
            raise RuntimeError("Feature extraction must complete before matching.")
        matcher_command = f"{self.config.matching_strategy}_matcher"
        input_signature = self._artifact_signature(
            (self.config.image_dir,),
            {
                "images": self._image_input_signature(),
                "strategy": self.config.matching_strategy,
                "overlap": self.config.sequential_overlap,
                "threads": self.config.num_threads,
            },
        )

        def match() -> None:
            arguments = [
                matcher_command,
                "--database_path", str(self.config.database_path),
            ]
            help_text = self._colmap_help(matcher_command)
            overlap_option = "--SequentialMatching.overlap"
            if (
                self.config.matching_strategy == "sequential"
                and overlap_option in help_text
            ):
                arguments.extend(
                    [overlap_option, str(self.config.sequential_overlap)]
                )
            elif self.config.matching_strategy == "sequential":
                print(
                    "Installed COLMAP does not expose sequential overlap; "
                    "using its default."
                )
            threads_option = "--FeatureMatching.num_threads"
            if threads_option in help_text:
                arguments.extend(
                    [threads_option, str(self.config.num_threads)]
                )
            self.runner.run(arguments, log_path=self._log_path())

        self._run_stage(
            "sequential_matching",
            match,
            self._database_has_matches,
            (self.config.database_path,),
            allow_existing_outputs=True,
            input_signature=input_signature,
        )

    def _build_sparse_model(self) -> Path:
        print("Step 3/7: Building sparse reconstruction...")
        if not self._database_has_matches():
            raise RuntimeError("Feature matching must complete before sparse mapping.")
        input_signature = self._artifact_signature(
            (self.config.image_dir,),
            {
                "images": self._image_input_signature(),
                "strategy": self.config.matching_strategy,
                "overlap": self.config.sequential_overlap,
                "threads": self.config.num_threads,
            },
        )
        self._run_stage(
            "sparse_mapping",
            lambda: self.runner.run(
                [
                    "mapper",
                    "--database_path", str(self.config.database_path),
                    "--image_path", str(self.config.image_dir),
                    "--output_path", str(self.config.sparse_dir),
                ],
                log_path=self._log_path(),
            ),
            self._sparse_model_is_valid,
            (self.config.sparse_dir,),
            input_signature=input_signature,
        )
        sparse_model = self.verify_reconstruction()
        registered_images, point_count = self._sparse_model_counts(sparse_model)
        self._metadata["stages"]["sparse_mapping"].update(
            input_images=len(
                [
                    path
                    for path in self.config.image_dir.iterdir()
                    if path.is_file()
                    and path.suffix.lower() in self.SUPPORTED_EXTENSIONS
                ]
            ),
            input_resolution=self._representative_image_dimensions(),
            registered_images=registered_images,
            reconstructed_points=point_count,
        )
        self._write_metadata()
        print(f"Sparse model verified: {sparse_model}")
        return sparse_model

    def _export_sparse_to_ply(self, sparse_model: Path) -> Path:
        print("Step 4/7: Exporting sparse points to PLY...")
        ply_output = sparse_model / "points.ply"
        input_signature = self._artifact_signature(
            tuple(
                path
                for filename in (
                    "cameras.bin",
                    "images.bin",
                    "points3D.bin",
                    "cameras.txt",
                    "images.txt",
                    "points3D.txt",
                )
                if (path := sparse_model / filename).is_file()
            ),
            {"export_type": "PLY"},
        )

        def export() -> None:
            self.runner.run(
                [
                    "model_converter",
                    "--input_path", str(sparse_model),
                    "--output_path", str(ply_output),
                    "--output_type", "PLY",
                ],
                log_path=self._log_path(),
            )

        self._run_stage(
            "sparse_ply_export",
            export,
            lambda: ply_output.is_file() and ply_output.stat().st_size > 0,
            (ply_output,),
            input_signature=input_signature,
        )
        print(f"Sparse point cloud exported: {ply_output}")
        return ply_output

    def _undistort_images(self, sparse_model: Path) -> None:
        print("Undistorting images for OpenMVS...")
        self.config.openmvs_dir.mkdir(parents=True, exist_ok=True)
        input_signature = self._artifact_signature(
            (sparse_model, self.config.image_dir),
            {
                "images": self._image_input_signature(),
                "max_image_size": self.config.max_image_size,
            },
        )

        def undistort() -> None:
            command = "image_undistorter"
            arguments = [
                command,
                "--image_path", str(self.config.image_dir),
                "--input_path", str(sparse_model),
                "--output_path", str(self.dense_dir),
                "--output_type", "COLMAP",
            ]
            option = "--max_image_size"
            if self._colmap_supports_option(command, option):
                arguments.extend([option, str(self.config.max_image_size)])
            else:
                print("COLMAP does not expose --max_image_size; using its default.")
            self.runner.run(arguments, log_path=self._log_path())

        self._run_stage(
            "colmap_image_undistortion",
            undistort,
            self._undistorted_scene_is_valid,
            (self.dense_dir / "images", self.dense_dir / "sparse"),
            input_signature=input_signature,
        )

    def _import_openmvs_scene(self) -> Path:
        if not self._undistorted_scene_is_valid():
            raise RuntimeError(
                "Undistorted COLMAP images and sparse model are required for OpenMVS."
            )
        input_signature = self._artifact_signature(
            (self.dense_dir / "images", self.dense_dir / "sparse"),
            {"importer": str(self.config.interface_colmap_executable)},
        )

        def import_scene() -> None:
            self._validate_openmvs_options(
                self.config.interface_colmap_executable,
                ("--input-file", "--output-file", "--image-folder"),
            )
            self._run_external(
                self.config.interface_colmap_executable,
                [
                    "--input-file", str(self.dense_dir / "sparse"),
                    "--output-file", str(self.config.openmvs_scene),
                    "--image-folder", str(self.dense_dir / "images"),
                ],
            )

        self._run_stage(
            "openmvs_scene_import",
            import_scene,
            lambda: self.config.openmvs_scene.is_file()
            and self.config.openmvs_scene.stat().st_size > 0,
            (self.config.openmvs_scene,),
            input_signature=input_signature,
        )
        return self.config.openmvs_scene

    def _build_mesh(self, sparse_model: Path) -> Path:
        print("Step 5/7: Generating OpenMVS dense cloud and mesh...")
        self._undistort_images(sparse_model)
        scene_path = self._import_openmvs_scene()
        dense_input_signature = self._artifact_signature(
            (scene_path,), self.config.densify_options
        )

        def densify() -> None:
            self._validate_openmvs_options(
                self.config.densify_point_cloud_executable,
                ("--output-file", *self.config.densify_options),
            )
            self._run_external(
                self.config.densify_point_cloud_executable,
                [
                    str(scene_path),
                    "--output-file", str(self.config.dense_scene),
                    *self.config.densify_options,
                ],
            )

        self._run_stage(
            "dense_point_cloud",
            densify,
            lambda: self.config.dense_scene.is_file()
            and self.config.dense_scene.stat().st_size > 0,
            (self.config.dense_scene,),
            input_signature=dense_input_signature,
        )
        mesh_input_signature = self._artifact_signature(
            (self.config.dense_scene,), self.config.reconstruct_mesh_options
        )

        def reconstruct_mesh() -> None:
            self._validate_openmvs_options(
                self.config.reconstruct_mesh_executable,
                ("--output-file", *self.config.reconstruct_mesh_options),
            )
            self._run_external(
                self.config.reconstruct_mesh_executable,
                [
                    str(self.config.dense_scene),
                    "--output-file", str(self.config.mesh_scene),
                    *self.config.reconstruct_mesh_options,
                ],
            )

        self._run_stage(
            "mesh_reconstruction",
            reconstruct_mesh,
            lambda: self.config.mesh_scene.is_file()
            and self.config.mesh_scene.stat().st_size > 0,
            (self.config.mesh_scene,),
            input_signature=mesh_input_signature,
        )
        self._require_file(self.config.mesh_scene, "OpenMVS mesh scene")
        print(f"OpenMVS mesh scene generated: {self.config.mesh_scene}")
        return self.config.mesh_scene

    def _textured_asset_is_valid(self) -> bool:
        obj_path = self.config.textured_obj
        if not obj_path.is_file() or obj_path.stat().st_size == 0:
            return False
        material_names = self._reference_values(obj_path, "mtllib")
        if not material_names:
            return False
        for material_name in material_names:
            material_path = obj_path.parent / material_name
            if not material_path.is_file() or material_path.stat().st_size == 0:
                return False
            texture_names = self._reference_values(material_path, "map_Kd")
            if not texture_names or any(
                not (material_path.parent / texture_name).is_file()
                or (material_path.parent / texture_name).stat().st_size == 0
                for texture_name in texture_names
            ):
                return False
        return True

    @staticmethod
    def _reference_values(path: Path, directive: str) -> list[str]:
        values = []
        with path.open(encoding="utf-8", errors="replace") as file:
            for line in file:
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2 and parts[0] == directive:
                    values.append(parts[1])
        return values

    def _textured_bundle_paths(self) -> tuple[Path, ...]:
        obj_path = self.config.textured_obj
        bundle_paths = [obj_path]
        if not obj_path.is_file():
            return tuple(bundle_paths)
        material_names = self._reference_values(obj_path, "mtllib")
        for material_name in material_names:
            material_path = obj_path.parent / material_name
            bundle_paths.append(material_path)
            if material_path.is_file():
                bundle_paths.extend(
                    material_path.parent / texture_name
                    for texture_name in self._reference_values(
                        material_path, "map_Kd"
                    )
                )
        return tuple(bundle_paths)

    def _build_textured_mesh(self) -> None:
        print("Step 6/7: Texturing surface mesh...")
        self.textured_mesh_dir.mkdir(parents=True, exist_ok=True)
        input_signature = self._artifact_signature(
            (self.config.mesh_scene,), self.config.texture_options
        )

        def texture() -> None:
            self._validate_openmvs_options(
                self.config.texture_mesh_executable,
                (
                    "--output-file",
                    "--export-type",
                    *self.config.texture_options,
                ),
            )
            self._run_external(
                self.config.texture_mesh_executable,
                [
                    str(self.config.mesh_scene),
                    "--output-file", str(self.config.textured_obj_base),
                    "--export-type", "obj",
                    *self.config.texture_options,
                ],
            )

        self._run_stage(
            "texture_baking",
            texture,
            self._textured_asset_is_valid,
            (
                self.config.textured_obj,
                self.config.textured_obj.with_suffix(".mtl"),
                self.config.textured_mvs_scene,
                self.textured_mesh_dir,
            ),
            input_signature=input_signature,
        )
        self._require_file(self.config.textured_obj, "Textured OBJ mesh")
        print(f"Textured OBJ mesh: {self.config.textured_obj}")
        self._validate_textured_obj_with_blender()

    def _validate_textured_obj_with_blender(self) -> None:
        if not self.blender_executable:
            self._metadata["stages"]["blender_validation"] = {
                "status": "skipped",
                "reason": "Blender executable not found.",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            self._write_metadata()
            print("Blender validation skipped: executable not found.")
            return

        obj_path = json.dumps(str(self.config.textured_obj))
        blender_script = f"""
import bpy

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
try:
    bpy.ops.wm.obj_import(filepath={obj_path})
except AttributeError:
    bpy.ops.import_scene.obj(filepath={obj_path})

mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
if not mesh_objects:
    raise RuntimeError("OBJ import produced no mesh objects")
if not any(obj.data.materials for obj in mesh_objects):
    raise RuntimeError("OBJ import produced no assigned materials")
"""
        input_signature = self._artifact_signature(self._textured_bundle_paths())
        stage_metrics = self._metadata["stages"].setdefault(
            "blender_validation", {}
        )

        def validate() -> bool:
            return (
                stage_metrics.get("validation_succeeded") is True
                and stage_metrics.get("input_signature") == input_signature
                and stage_metrics.get("status")
                in {"running", "completed", "skipped"}
            )

        def validate_with_blender() -> None:
            self._run_external(
                self.blender_executable,
                ["--background", "--python-expr", blender_script],
            )
            stage_metrics["validation_succeeded"] = True

        self._run_stage(
            "blender_validation",
            validate_with_blender,
            validate,
            input_signature=input_signature,
        )

    def _export_glb_impl(self) -> Path:
        print("Step 7/7: Converting to web-ready GLB model...")
        self.web_asset_dir.mkdir(parents=True, exist_ok=True)
        if not self._textured_asset_is_valid():
            raise RuntimeError(
                f"A valid textured OBJ/MTL/texture bundle is required: "
                f"{self.config.textured_obj}"
            )

        try:
            import trimesh
            mesh = trimesh.load(str(self.config.textured_obj))
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
    bpy.ops.wm.obj_import(filepath={json.dumps(str(self.config.textured_obj))})
except Exception:
    bpy.ops.import_scene.obj(filepath={json.dumps(str(self.config.textured_obj))})

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

        self._require_file(self.final_glb, "Final GLB model")
        size_mb = self.final_glb.stat().st_size / (1024 * 1024)
        print(f"Final 3D Web Model: {self.final_glb} ({size_mb:.2f} MB)")

        # 3. Create an HTML 3D Web Viewer
        self._create_web_viewer()
        return self.final_glb

    def _export_glb(self) -> Path:
        input_signature = self._artifact_signature(
            self._textured_bundle_paths(),
            {
                "gltf_transform": self.gltf_transform_executable,
                "blender": self.blender_executable,
            },
        )
        self._run_stage(
            "final_export",
            self._export_glb_impl,
            lambda: self.final_glb.is_file()
            and self.final_glb.stat().st_size > 0
            and (self.web_asset_dir / "index.html").is_file(),
            (self.final_glb, self.web_asset_dir / "index.html"),
            input_signature=input_signature,
        )
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

    def run(self, stage: str = "all") -> None:
        if stage not in {"all", "sparse", "dense", "mesh", "texture", "export", "view"}:
            raise ValueError(f"Unsupported pipeline stage: {stage}")
        if stage == "view":
            viewer = self._create_web_viewer()
            print(f"Open in browser: file:///{viewer.as_posix()}")
            return

        sparse_model: Path | None = None
        if stage in {"all", "sparse"}:
            self.validate_inputs()
            self.config.prepare_directories()
            self._extract_features()
            self._match_features()
            sparse_model = self._build_sparse_model()
            self._export_sparse_to_ply(sparse_model)
            if stage == "sparse":
                return
        elif stage in {"dense", "mesh"}:
            sparse_model = self.verify_reconstruction()

        if stage in {"all", "dense", "mesh"}:
            if sparse_model is None:
                raise RuntimeError("A valid sparse model is required for dense stages.")
            self._build_mesh(sparse_model)
            if stage in {"dense", "mesh"}:
                return

        if stage in {"all", "texture"}:
            if not self.config.mesh_scene.is_file():
                raise FileNotFoundError(
                    f"OpenMVS mesh scene is required: {self.config.mesh_scene}"
                )
            self._build_textured_mesh()
            if stage == "texture":
                return

        if stage in {"all", "export"}:
            self._export_glb()
        print("Pipeline execution completed successfully!")