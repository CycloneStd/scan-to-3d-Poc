from __future__ import annotations

import hashlib
import json 
import os 
from pathlib import Path
from typing import Any, Iterable


def fingerprint(obj: Any)->str:
    blob = json.dumps(obj, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]

def files_signature(paths: Iterable[Path]) -> list:
    sig = []
    for p in sorted(Path(x) for x in paths):
        st = p.stat()
        sig.append([str(p.resolve()), st.st_size, st.st_mtime_ns])
    return sig

class RunDir:
    def __init__(self, root:Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "logs").mkdir(exist_ok=True)

    def stage_dir(self, name:str) -> Path:
        p = self.root / name
        p.mkdir(exist_ok=True)
        return p

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

class Manifest:
    def __init__(self,path:Path):
        self.path = Path(path)
        self.data = {"stages": {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def get(self,name:str) -> dict | None:
        return self.data["stages"].get(name)

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, default=str))
        os.replace(tmp, self.path)