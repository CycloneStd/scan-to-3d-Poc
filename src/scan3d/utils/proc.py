from __futures__ import annotations 

import logging 
import resources 
import subprocess
import time 

from dataclasses import dataclass
from pathlib import Path 
from typing import Sequence

log = logging.getLogger("scan3d.proc")


@dataclass
class ProcResult:
    returncode: int
    seconds: float
    peak_children_rss_md: float

def run(cmd: Sequence, *, log_file: Path | None = None, cwd=None, check: bool = True) -> ProcResult:
    cmd = [str(c) for c in cmd]
    log.info("$ %s", " ".join(cmd))
    start = time.perf_counter()

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "ab") as fh:
            proc = subprocess.run(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT)

    else:
        proc = subprocess.run(cmd, cwd=cwd)
    
    res = ProcResult(
        proc.returncode,
        round(time.perf_counter() - start, 2),
        round(resources.getrusage(resources.RUSAGE_CHILDREN).ru_maxrss / 1024, 1)
    )
    if check and proc.returncode != 0:
        where = f" (see {log_file})" if log_file else ""
        raise RuntimeError(f"Command failed with Exit {proc.returncode}: {' '.join(cmd)}{where}")
    return res

def capture(cmd: Sequence2, timeout: int = 60) -> tuple[int,str]:
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    
    except(FileNotFoundError, subprocess.TimeoutExprired) as exec:
        return -1, str(exec)