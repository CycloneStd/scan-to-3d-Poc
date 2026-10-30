from .ingest import Ingestage
from .validate import ValidateStage

REGISTRY ={s.name: s for s in (IngestStage(),ValidateStage())}
ORDER = list(REGISTRY)