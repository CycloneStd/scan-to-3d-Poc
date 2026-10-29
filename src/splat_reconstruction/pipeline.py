from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import time
from typing import Callable

from .video import VideoConfig, extract_video


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


@dataclass(frozen=True)
class PipelineConfig:
    project_dir: Path
    run_name: str
    colmap: str
    gsplat_trainer: Path
    python: str = sys.executable
    input_dir: Path | None = None
    input_video: Path | None = None
    mapper: str = "global_mapper"
    matching: str | None = None
    overlap: int = 5
    threads: int = 8
    gpu_features: bool = False
    max_steps: int = 7000
    video: VideoConfig = VideoConfig()

    def __post_init__(self) -> None:
        if (self.input_dir is None) == (self.input_video is None):
            raise ValueError("Provide exactly one input image directory or video.")
        if self.mapper not in {"global_mapper", "mapper"}:
            raise ValueError("mapper must be 'global_mapper' or 'mapper'")
        if self.matching not in {None, "exhaustive", "sequential"}:
            raise ValueError("matching must be exhaustive or sequential")
        if self.overlap <= 0 or self.threads <= 0 or self.max_steps <= 0:
            raise ValueError("overlap, threads, and max_steps must be positive")
        if not self.run_name or self.run_name in {".", ".."} or any(
            character in self.run_name for character in '<>:"/\\|?*'
        ):
            raise ValueError("run_name must be a single safe path component")

    @property
    def run_dir(self) -> Path:
        return Path(self.project_dir) / self.run_name

    @property
    def image_dir(self) -> Path:
        return self.run_dir / "images"

    @property
    def database(self) -> Path:
        return self.run_dir / "database.db"

    @property
    def sparse_dir(self) -> Path:
        return self.run_dir / "sparse"

    @property
    def logs_dir(self) -> Path:
        return self.run_dir / "logs"

    @property
    def metadata_path(self) -> Path:
        return self.run_dir / "metadata.json"

    @property
    def gsplat_dir(self) -> Path:
        return self.run_dir / "gsplat"


class SplatPipeline:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.config.run_dir.mkdir(parents=True, exist_ok=True)
        self.config.logs_dir.mkdir(parents=True, exist_ok=True)
        if self.config.metadata_path.is_file():
            self.metadata = json.loads(
                self.config.metadata_path.read_text(encoding="utf-8")
            )
        else:
            self.metadata = {"run_name": config.run_name, "stages": {}}
        self.metadata.setdefault("stages", {})

    @staticmethod
    def _signature(value: object) -> str:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _image_files(self, directory: Path) -> list[Path]:
        return sorted(
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )

    def _image_signature(self, paths: list[Path]) -> str:
        return self._signature(
            [
                (path.name, path.stat().st_size, path.stat().st_mtime_ns)
                for path in paths
            ]
        )

    def _write_metadata(self) -> None:
        temporary = self.config.metadata_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(self.metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.config.metadata_path)

    @staticmethod
    def _platform_command(command: list[str]) -> list[str]:
        if os.name == "nt" and Path(command[0]).suffix.lower() in {".bat", ".cmd"}:
            return [
                "cmd.exe",
                "/d",
                "/s",
                "/c",
                subprocess.list2cmdline(command),
            ]
        return command

    @staticmethod
    def _headless_subprocess_environment() -> dict[str, str]:
        environment = os.environ.copy()
        for name in ("QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_FONTDIR"):
            environment.pop(name, None)
        return environment

    def _stage(
        self,
        name: str,
        signature: str,
        valid: Callable[[], bool],
        operation: Callable[[], object],
        outputs: list[Path],
    ) -> None:
        stage = self.metadata["stages"].setdefault(name, {})
        if stage.get("status") == "completed" and stage.get("signature") == signature:
            if valid():
                print(f"Skipping completed stage: {name}")
                return
            raise RuntimeError(
                f"Completed stage '{name}' is missing or has damaged output. "
                "Use a new --run-name to keep this run intact."
            )
        if stage.get("status") == "completed":
            raise FileExistsError(
                f"Stage '{name}' belongs to different inputs or settings. "
                "Use a new --run-name to preserve existing outputs."
            )
        existing = [
            path for path in outputs
            if path.is_file() and path.stat().st_size > 0
            or path.is_dir() and any(path.iterdir())
        ]
        if existing:
            raise FileExistsError(
                f"Stage '{name}' has incomplete output: "
                + ", ".join(str(path) for path in existing)
                + ". Use a new --run-name."
            )
        stage.update(status="running", signature=signature, started_at=time.time())
        self._write_metadata()
        try:
            operation()
            if not valid():
                raise RuntimeError(f"Stage '{name}' did not produce valid output.")
        except Exception as exc:
            stage.update(status="failed", error=str(exc), completed_at=time.time())
            self._write_metadata()
            raise
        stage.update(status="completed", completed_at=time.time())
        self._write_metadata()

    def _run_command(self, command: list[str], stage: str, cwd: Path | None = None) -> str:
        log_path = self.config.logs_dir / f"{stage}.log"
        resolved = shutil.which(command[0])
        executable = Path(command[0])
        if resolved:
            command[0] = resolved
        elif executable.is_file():
            command[0] = str(executable.resolve())
        else:
            raise FileNotFoundError(f"Required executable was not found: {command[0]}")

        collected: list[str] = []
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                self._platform_command(command),
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=self._headless_subprocess_environment(),
            )
            if process.stdout is not None:
                for line in process.stdout:
                    collected.append(line)
                    log.write(line)
                    sys.stdout.write(line)
                    sys.stdout.flush()
            process.wait()
        output = "".join(collected)
        if process.returncode:
            raise RuntimeError(
                f"{stage} failed with exit code {process.returncode}; "
                f"see {log_path}.\n{''.join(collected[-30:])}"
            )
        return output

    def _run_help(self, command: str) -> str:
        executable = shutil.which(self.config.colmap)
        if executable is None and Path(self.config.colmap).is_file():
            executable = str(Path(self.config.colmap).resolve())
        if executable is None:
            raise FileNotFoundError(
                f"COLMAP executable was not found: {self.config.colmap}"
            )
        result = subprocess.run(
            self._platform_command([executable, command, "-h"]),
            capture_output=True,
            text=True,
            check=False,
            env=self._headless_subprocess_environment(),
        )
        text = f"{result.stdout}\n{result.stderr}"
        if not text.strip():
            raise RuntimeError(
                f"Could not inspect COLMAP help for {command}: {text}"
            )
        return text

    def _stage_input(self) -> dict:
        self.config.image_dir.mkdir(parents=True, exist_ok=True)
        if self.config.input_video is not None:
            metrics = extract_video(
                Path(self.config.input_video),
                self.config.image_dir,
                self.config.video,
            )
            signature = self._signature(
                [
                    metrics,
                    Path(self.config.input_video).resolve(),
                    Path(self.config.input_video).stat().st_size,
                    Path(self.config.input_video).stat().st_mtime_ns,
                ]
            )
            self.metadata["stages"]["input"] = {
                "status": "completed",
                "signature": signature,
                **metrics,
            }
            self._write_metadata()
            return metrics

        assert self.config.input_dir is not None
        source = Path(self.config.input_dir)
        if not source.is_dir():
            raise FileNotFoundError(f"Input image directory does not exist: {source}")
        if source.resolve() == self.config.image_dir.resolve():
            raise ValueError("Input images cannot be the managed run images directory.")
        files = self._image_files(source)
        if len(files) < 2:
            raise ValueError(f"At least two images are required in {source}")
        signature = self._signature(
            [
                str(source.resolve()),
                [
                    (path.name, path.stat().st_size, path.stat().st_mtime_ns)
                    for path in files
                ],
            ]
        )
        manifest_path = self.config.image_dir / "input_manifest.json"
        existing = self._image_files(self.config.image_dir)
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            names = [f"image_{index:06d}{path.suffix.lower()}" for index, path in enumerate(files)]
            if (
                manifest.get("signature") == signature
                and [path.name for path in existing] == names
                and all(path.stat().st_size > 0 for path in existing)
            ):
                return {
                    "images": len(existing),
                    "source": str(source.resolve()),
                    "reused": True,
                }
            raise FileExistsError(
                "This run name already contains different source images. "
                "Use a new --run-name."
            )
        if existing:
            raise FileExistsError(
                "Run image directory is not empty. Use a new --run-name."
            )
        staged = []
        for index, path in enumerate(files):
            destination = self.config.image_dir / f"image_{index:06d}{path.suffix.lower()}"
            shutil.copy2(path, destination)
            staged.append(destination)
        if any(path.stat().st_size == 0 for path in staged):
            raise RuntimeError("One or more staged images are empty.")
        temporary_manifest = manifest_path.with_suffix(".json.tmp")
        temporary_manifest.write_text(
            json.dumps(
                {"signature": signature, "source": str(source.resolve())},
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_manifest.replace(manifest_path)
        metrics = {"images": len(staged), "source": str(source.resolve()), "reused": False}
        self.metadata["stages"]["input"] = {
            "status": "completed",
            "signature": signature,
            **metrics,
        }
        self._write_metadata()
        return metrics

    def _database_counts(self) -> tuple[int, int, int]:
        if not self.config.database.is_file():
            return 0, 0, 0
        with sqlite3.connect(self.config.database) as database:
            tables = {
                row[0]
                for row in database.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "images" not in tables or "keypoints" not in tables:
                return 0, 0, 0
            images = int(database.execute("SELECT COUNT(*) FROM images").fetchone()[0])
            features = int(
                database.execute(
                    "SELECT COUNT(*) FROM keypoints WHERE rows > 0"
                ).fetchone()[0]
            )
            matches = 0
            for table in ("two_view_geometries", "matches"):
                if table in tables:
                    matches = int(
                        database.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE rows > 0 AND cols > 0"
                        ).fetchone()[0]
                    )
                    if matches:
                        break
            return images, features, matches

    def _sparse_models(self) -> list[Path]:
        if not self.config.sparse_dir.is_dir():
            return []
        valid = []
        for model in self.config.sparse_dir.iterdir():
            if not model.is_dir():
                continue
            required = [model / name for name in ("cameras.bin", "images.bin", "points3D.bin")]
            if all(path.is_file() and path.stat().st_size >= 8 for path in required):
                with required[2].open("rb") as file:
                    point_count = struct.unpack("<Q", file.read(8))[0]
                if point_count:
                    valid.append((point_count, model))
        return [model for _, model in sorted(valid, reverse=True)]

    def _extract_features(self, images_signature: str) -> None:
        signature = self._signature([images_signature, self.config.gpu_features])
        command = [
            self.config.colmap, "feature_extractor",
            "--database_path", str(self.config.database),
            "--image_path", str(self.config.image_dir),
        ]
        help_text = self._run_help("feature_extractor")
        options = {
            "--ImageReader.single_camera": "1",
            "--FeatureExtraction.num_threads": str(self.config.threads),
        }
        gpu_option = next(
            (
                option for option in (
                    "--FeatureExtraction.use_gpu",
                    "--SiftExtraction.use_gpu",
                )
                if option in help_text
            ),
            None,
        )
        if gpu_option is not None:
            options[gpu_option] = "1" if self.config.gpu_features else "0"
        elif self.config.gpu_features:
            raise RuntimeError("This COLMAP build does not support GPU feature extraction.")
        command.extend(
            item for option, value in options.items()
            if option in help_text
            for item in (option, value)
        )
        self._stage(
            "feature_extraction",
            signature,
            lambda: self._database_counts()[0] >= 2 and self._database_counts()[1] > 0,
            lambda: self._run_command(command, "feature_extraction"),
            [self.config.database],
        )

    def _match(self, images_signature: str, strategy: str) -> None:
        command_name = f"{strategy}_matcher"
        signature = self._signature(
            [images_signature, strategy, self.config.overlap, self.config.threads]
        )
        command = [
            self.config.colmap, command_name,
            "--database_path", str(self.config.database),
        ]
        help_text = self._run_help(command_name)
        if strategy == "sequential" and "--SequentialMatching.overlap" in help_text:
            command.extend(["--SequentialMatching.overlap", str(self.config.overlap)])
        if "--FeatureMatching.num_threads" in help_text:
            command.extend(["--FeatureMatching.num_threads", str(self.config.threads)])
        self._stage(
            "feature_matching",
            signature,
            lambda: self._database_counts()[2] > 0,
            lambda: self._run_command(command, "feature_matching"),
            [],
        )

    def _map(self, images_signature: str, strategy: str) -> Path:
        command_name = self.config.mapper
        signature = self._signature(
            [images_signature, strategy, command_name, self.config.overlap]
        )
        command = [
            self.config.colmap, command_name,
            "--database_path", str(self.config.database),
            "--image_path", str(self.config.image_dir),
            "--output_path", str(self.config.sparse_dir),
        ]
        self.config.sparse_dir.mkdir(parents=True, exist_ok=True)
        self._stage(
            "sparse_mapping",
            signature,
            lambda: bool(self._sparse_models()),
            lambda: self._run_command(command, "sparse_mapping"),
            [self.config.sparse_dir],
        )
        models = self._sparse_models()
        if not models:
            raise RuntimeError("COLMAP did not produce a valid sparse model.")
        return models[0]

    def _export_sparse(self, model: Path, images_signature: str) -> Path:
        point_cloud = model / "points.ply"
        signature = self._signature([images_signature, str(model.resolve()), "PLY"])

        def export() -> None:
            self._run_command(
                [
                    self.config.colmap, "model_converter",
                    "--input_path", str(model),
                    "--output_path", str(point_cloud),
                    "--output_type", "PLY",
                ],
                "sparse_ply_export",
            )

        self._stage(
            "sparse_ply_export",
            signature,
            lambda: point_cloud.is_file() and point_cloud.stat().st_size > 3,
            export,
            [point_cloud],
        )

        text_dir = self.config.run_dir / "cameras_text"
        text_files = [text_dir / name for name in ("cameras.txt", "images.txt", "points3D.txt")]

        def export_text() -> None:
            text_dir.mkdir(parents=True, exist_ok=True)
            self._run_command(
                [
                    self.config.colmap, "model_converter",
                    "--input_path", str(model),
                    "--output_path", str(text_dir),
                    "--output_type", "TXT",
                ],
                "camera_export",
            )

        self._stage(
            "camera_export",
            self._signature([images_signature, str(model.resolve()), "TXT"]),
            lambda: all(path.is_file() and path.stat().st_size > 0 for path in text_files),
            export_text,
            text_files,
        )
        return point_cloud

    def _cuda_preflight(self) -> None:
        check = (
            "import torch, gsplat; "
            "assert torch.cuda.is_available(), 'CUDA is unavailable to PyTorch'; "
            "print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0))"
        )
        result = subprocess.run(
            [self.config.python, "-c", check],
            capture_output=True,
            text=True,
            check=False,
        )
        log = self.config.logs_dir / "gpu_preflight.log"
        log.write_text(f"{result.stdout}\n{result.stderr}".strip(), encoding="utf-8")
        if result.returncode:
            raise RuntimeError(
                f"CUDA/gsplat preflight failed; see {log}.\n{result.stderr.strip()}"
            )

    def _trainer_flags(self) -> dict[str, str]:
        trainer = Path(self.config.gsplat_trainer)
        if not trainer.is_file():
            raise FileNotFoundError(f"gsplat trainer not found: {trainer}")
        result = subprocess.run(
            [self.config.python, str(trainer), "default", "--help"],
            cwd=trainer.resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        help_text = f"{result.stdout}\n{result.stderr}"
        if result.returncode:
            raise RuntimeError(f"Could not read gsplat trainer help:\n{help_text[-3000:]}")
        flags = {}
        for name in ("data_dir", "result_dir", "max_steps", "save_ply", "ply_steps"):
            choices = (f"--{name}", f"--{name.replace('_', '-')}")
            flag = next(
                (
                    candidate for candidate in choices
                    if re.search(re.escape(candidate) + r"(?=$|[\s=,:)\]])", help_text)
                ),
                None,
            )
            if flag is None:
                raise RuntimeError(f"gsplat trainer is missing required option {name}.")
            flags[name] = flag
        return flags

    def _ply_outputs(self) -> list[Path]:
        if not self.config.gsplat_dir.is_dir():
            return []
        outputs = []
        for path in self.config.gsplat_dir.rglob("*.ply"):
            if path.is_file() and path.stat().st_size > 3:
                with path.open("rb") as file:
                    if file.read(3) == b"ply":
                        outputs.append(path)
        return sorted(outputs, key=lambda path: path.stat().st_mtime_ns)

    def _train(self, images_signature: str) -> Path:
        signature = self._signature(
            [
                images_signature,
                self.config.max_steps,
                str(Path(self.config.gsplat_trainer).resolve()),
                self.config.python,
            ]
        )
        marker = self.config.gsplat_dir / "training_complete.json"

        def completed() -> bool:
            if not marker.is_file():
                return False
            data = json.loads(marker.read_text(encoding="utf-8"))
            if data.get("signature") != signature:
                return False
            outputs = data.get("outputs", [])
            if not outputs:
                return False
            for item in outputs:
                path = Path(item["path"])
                if not path.is_file() or path.stat().st_size != item["size"]:
                    return False
                with path.open("rb") as file:
                    if file.read(3) != b"ply":
                        return False
            return True

        def train() -> None:
            self._cuda_preflight()
            flags = self._trainer_flags()
            self.config.gsplat_dir.mkdir(parents=True, exist_ok=True)
            command = [
                self.config.python,
                str(Path(self.config.gsplat_trainer).resolve()),
                "default",
                flags["data_dir"], str(self.config.run_dir.resolve()),
                flags["result_dir"], str(self.config.gsplat_dir.resolve()),
                flags["max_steps"], str(self.config.max_steps),
                flags["save_ply"],
                flags["ply_steps"], str(self.config.max_steps),
            ]
            self._run_command(
                command,
                "gsplat_training",
                cwd=Path(self.config.gsplat_trainer).resolve().parents[1],
            )
            outputs = self._ply_outputs()
            if not outputs:
                raise RuntimeError(
                    "gsplat completed without a PLY export; inspect the training log."
                )
            marker.parent.mkdir(parents=True, exist_ok=True)
            temporary = marker.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "signature": signature,
                        "outputs": [
                            {
                                "path": str(path.resolve()),
                                "size": path.stat().st_size,
                            }
                            for path in outputs
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary.replace(marker)

        self.config.gsplat_dir.mkdir(parents=True, exist_ok=True)
        self._stage(
            "gsplat_training",
            signature,
            completed,
            train,
            [self.config.gsplat_dir],
        )
        outputs = self._ply_outputs()
        if not outputs:
            raise RuntimeError("No valid Gaussian splat PLY was found.")
        return outputs[-1]

    def run(self) -> Path:
        input_metrics = self._stage_input()
        images = self._image_files(self.config.image_dir)
        if len(images) < 2:
            raise ValueError("At least two usable images are required.")
        image_signature = self._image_signature(images)
        strategy = self.config.matching or (
            "sequential" if self.config.input_video else "exhaustive"
        )

        self._extract_features(image_signature)
        self._match(image_signature, strategy)
        model = self._map(image_signature, strategy)
        sparse_ply = self._export_sparse(model, image_signature)
        splat_ply = self._train(image_signature)

        self.metadata["summary"] = {
            "input": input_metrics,
            "source_images": len(images),
            "matching": strategy,
            "mapper": self.config.mapper,
            "sparse_model": str(model.resolve()),
            "sparse_point_cloud": str(sparse_ply.resolve()),
            "splat_ply": str(splat_ply.resolve()),
            "training_steps": self.config.max_steps,
        }
        self._write_metadata()
        print(f"Reconstruction complete. Gaussian splat: {splat_ply}")
        return splat_ply
