from __future__ import annotations 

import logging 
import time 
from abc import ABC, abstractmethod
from dataclasses import dataclass 
from typing import Any 

from .project import Manifest, RunDir, fingerprint

log = logging.getLogger("scan3d.pipeline")

@dataclass
class Context:
    cfg: dict
    run: RunDir 
    manifest: Manifest

class Stage(ABC):
    name:str=""
    dir_name=""
    requires:tuple[str,...] = ()

    def config_slice(self,cfg:dict)->Any:
        return {}
    def input_signature(self,ctx:Context)->Any:
        return None
    
    @abstractmethod
    def run(self,ctx:Context)->dict:


def _now()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def execute(ctx:Context,names:list[str],registry:dict[str,Stage],force:Bool=False)->None:
    for name in names:
        stage = registry[name]
        upstream = {}

        for req in stage.requires:
            rec = ctx.manifest.get(req)
            if not rec or rec.get("status") != "done":
                raise RuntimeError(f"Stage '{name}' needs '{req}' to be completed first")
            upstream[req]=rec["fingerprint"]
        
        fp = fingerprint(
            {"cfg": stage.config_slice(ctx.cfg), "inputs": stage.input_signature(ctx), "upstream": upstream}
        )
        rec = ctx.manifest.get(name)
        if not force and rec and rec.get("status") == "done" and rec.get("fingerprint") == fp:
            log.info("[%s] up to date, skipping", name)
            continue
        log.info("[%s] running",name)

        ctx.manifest.update(name,status="running",fingerprint=fp,started=_now(),error=None)
        t0 = time.perf_counter()

        try:
            metrics = stage.run(ctx)
        except Exception as exc:
            ctx.manifest.update(name,status="failed",error=repr(exc),seconds=round(time.perf_counter() - t0, 2))
            log.exception("[%s] failed", name)
            raise
        ctx.manifest.update(
            name,status="done",metrics=metrics,seconds=round(time.perf_counter() - t0 , 2), finished=_now()
        )

        log.info("[%s] **done** :%s",name,metrics)