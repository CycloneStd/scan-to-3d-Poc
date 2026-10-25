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
            return Path(self.input_dir)
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

    @property
    def dense_dir(self) -> Path:
        return self.run_dir / "dense"

    @property
    def textured_dir(self) -> Path:
        return self.dense_dir / "textured"

    @property
    def textured_mesh(self) -> Path:
        return self.textured_dir / "mesh.ply"

    @property
    def texture_atlas(self) -> Path:
        return self.textured_dir / "texture.png"

    @property
    def web_dir(self) -> Path:
        return self.run_dir / "web"

    @property
    def final_glb(self) -> Path:
        return self.web_dir / "model.glb"

    def prepare_directories(self) -> None:
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.sparse_dir.mkdir(parents=True, exist_ok=True)
        self.dense_dir.mkdir(parents=True, exist_ok=True)
        self.textured_dir.mkdir(parents=True, exist_ok=True)
        self.web_dir.mkdir(parents=True, exist_ok=True)
