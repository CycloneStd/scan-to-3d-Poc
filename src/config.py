from pathlib import Path
from dataclasses import dataclass

@dataclass
class ScanConfig:
    project_root: Path
    colmap_executable: Path

    @property
    def image_dir(self)-> Path:
        return self.project_root / "data" / "input"

    @property
    def database_dir(self)-> Path:
        return self.run_dir / "database.db"