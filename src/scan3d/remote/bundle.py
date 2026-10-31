from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path


def pack(sources: dict[str, Path], out: Path) -> str:
    with tarfile.open(out, "w:gz", dereference=True) as tar:
        for arcname, src in sources.items():
            tar.add(src, arcname=arcname)
    return sha256(out)


def unpack(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(dest, filter="data")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def split_file(path: Path, out_dir: Path, prefix: str, chunk_bytes: int) -> list[Path]:
    parts: list[Path] = []
    with open(path, "rb") as fh:
        i = 0
        while True:
            data = fh.read(chunk_bytes)
            if not data:
                break
            p = out_dir / f"{prefix}{i:03d}"
            p.write_bytes(data)
            parts.append(p)
            i += 1
    return parts