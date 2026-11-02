from .dense import DenseStage
from .export import ExportStage
from .features import FeaturesStage
from .ingest import IngestStage
from .mesh import MeshStage
from .sparse import SparseStage
from .undistort import UndistortStage
from .validate import ValidateStage

REGISTRY = {s.name: s for s in (
    IngestStage(), ValidateStage(), FeaturesStage(), SparseStage(),
    UndistortStage(), DenseStage(), MeshStage(), ExportStage(),
)}
ORDER = list(REGISTRY)