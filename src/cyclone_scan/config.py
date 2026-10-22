from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScanConfig:
    project_root: Path
    colmap_executable: Path

    @property
    def image_dir(self) -> Path:
        return self.project_root / "data" / "input"

    @property
    def run_dir(self) -> Path:
        return self.project_root / "data" / "runs" / "test-object"

    @property
    def database_path(self) -> Path:
        return self.run_dir / "database.db"

    @property
    def sparse_dir(self) -> Path:
        return self.run_dir / "sparse"

    def prepare_directories(self) -> None:
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.sparse_dir.mkdir(parents=True, exist_ok=True)