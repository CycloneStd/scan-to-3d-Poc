from __future__ import annotations

from pathlib import Path


def ply_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with open(path, "rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", "ignore").strip()
            if line.startswith("element "):
                _, name, n = line.split()
                counts[name] = int(n)
            if line == "end_header":
                break
    return counts