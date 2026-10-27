from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScanConfig:
    project_root: Path
    colmap_executable: Path
    run_name: str = "test-object"
    input_dir: Path | None = None
    interface_colmap_executable: str | Path = "InterfaceCOLMAP"
    densify_point_cloud_executable: str | Path = "DensifyPointCloud"
    reconstruct_mesh_executable: str | Path = "ReconstructMesh"
    texture_mesh_executable: str | Path = "TextureMesh"
    matching_strategy: str = "sequential"
    sequential_overlap: int = 5
    num_threads: int = 8
    max_image_size: int = 1920
    densify_options: tuple[str, ...] = ()
    reconstruct_mesh_options: tuple[str, ...] = ()
    texture_options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.matching_strategy != "sequential":
            raise ValueError(
                "Only sequential matching is currently supported."
            )
        if self.sequential_overlap <= 0:
            raise ValueError("sequential_overlap must be positive")
        if self.num_threads <= 0:
            raise ValueError("num_threads must be positive")
        if self.max_image_size <= 0:
            raise ValueError("max_image_size must be positive")

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
    def openmvs_dir(self) -> Path:
        return self.dense_dir / "openmvs"

    @property
    def openmvs_scene(self) -> Path:
        return self.openmvs_dir / "scene.mvs"

    @property
    def dense_scene(self) -> Path:
        return self.openmvs_dir / "scene_dense.mvs"

    @property
    def mesh_scene(self) -> Path:
        return self.openmvs_dir / "scene_mesh.mvs"

    @property
    def textured_dir(self) -> Path:
        return self.dense_dir / "textured"

    @property
    def textured_obj_base(self) -> Path:
        return self.textured_dir / "model"

    @property
    def textured_obj(self) -> Path:
        return self.textured_obj_base.with_suffix(".obj")

    @property
    def textured_mvs_scene(self) -> Path:
        return self.textured_obj_base.with_suffix(".mvs")

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
        self.openmvs_dir.mkdir(parents=True, exist_ok=True)
        self.textured_dir.mkdir(parents=True, exist_ok=True)
        self.web_dir.mkdir(parents=True, exist_ok=True)
