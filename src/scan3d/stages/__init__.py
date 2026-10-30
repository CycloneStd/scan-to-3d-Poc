from .ingest import IngestStage
from .validate import ValidateStage

REGISTRY = {s.name: s for s in (IngestStage(), ValidateStage())}
ORDER = list(REGISTRY)