from .ingest import IngestStage
from .validate import ValidateStage
from .features import FeaturesStage
from .sparse import SparseStage
 
REGISTRY ={s.name: s for s in(IngestStage(),ValidateStage(),FeaturesStage(),SparseStage())}
ORDER = list(REGISTRY)