from __future__ import annotations

from functools import lru_cache

from .proc import capture


@lru_cache(maxsize=None)
def help_text(binary: str, command: str) -> str:
    return capture([binary, command, "-h"])[1]


def version(binary: str) -> str:
    _, out = capture([binary, "-h"])
    return next((ln.strip() for ln in out.splitlines() if "COLMAP" in ln), "unknown")


def gpu_flag(binary: str, command: str, kind: str) -> str:
    old = {"FeatureExtraction": "SiftExtraction", "FeatureMatching": "SiftMatching"}[kind]
    text = help_text(binary, command)
    for prefix in (kind, old):
        if f"--{prefix}.use_gpu" in text:
            return f"--{prefix}.use_gpu"
    raise RuntimeError(f"Could not find a use_gpu option in `{binary} {command} -h`")