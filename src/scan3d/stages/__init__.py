from .dense import DenseStage
from .ar import ArStage
from .export import ExportStage
from .features import FeaturesStage
from .ingest import IngestStage
from .mesh import MeshStage
from .sparse import SparseStage
from .splat import SplatStage
from .undistort import UndistortStage
from .validate import ValidateStage
from .reconstruction import ReconstructionStage

REGISTRY = {s.name: s for s in (
    IngestStage(), ValidateStage(), FeaturesStage(), SparseStage(),
    UndistortStage(), DenseStage(), ReconstructionStage(), MeshStage(), ExportStage(), SplatStage(), ArStage(),
)}

ORDER = list(REGISTRY)

TRACKS = {
    "mesh": ["ingest", "validate", "reconstruction", "mesh", "export", "ar"],
    "splat": ["ingest", "validate", "features", "sparse", "undistort", "splat"],
}
