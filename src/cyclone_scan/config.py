from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScanConfig:
    project_root: Path
    colmap_executable: Path
    run_name: str = "test-object"
    input_dir: Path | None = None

    @property
    def image_dir(self) -> Path:
        if self.input_dir is not None:
            return self.input_dir
        return self.project_root / "data" / "input"

    @property
    def run_dir(self) -> Path:
        return self.project_root / "data" / "runs" / self.run_name

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
