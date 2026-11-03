from __future__ import annotations

import os
from pathlib import Path

import yaml

REQUIRED = {
    "project": ["name"],
    "inputs": ["photos_dir", "videos"],
    "video": ["fps", "jpeg_quality"],
    "validation": ["min_short_side", "blur_ratio", "min_brightness", "max_brightness"],
    "remote": ["session", "gpu"],
    "colmap": ["binary"],
    "features": ["camera_model", "use_gpu"],
    "sparse": ["mapper"],
}

DEFAULTS = {
    "undistort": {"max_image_size": 2000},
    "dense": {"geom_consistency": True,
              "colmap_specs": ["colmap=4.2.1=cuda_129*", "colmap=4.2.1=cuda_130*"]},
    "mesh": {"texture": True,"target_face_ratio":0.05},
    "blender": {"binary": "blender"},
    "export": {"flip_v": False},
    "video": {"select": "sharpest", "oversample": 3},
    "features": {"matcher": "auto", "sequential_overlap": 15},
    "splat": {"max_steps": 30000, "data_factor": 1, "upload_jpeg_quality": 90,
              "download_ply": False, "compress": ["sog", "spz"]},
}


def _expand(value: str, key: str) -> str:
    out = os.path.expanduser(os.path.expandvars(value))
    if "$" in out:
        raise ValueError(f"{key} uses an environment variable that is not set: {value}")
    return out


def load_config(path: str | Path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    problems = []
    for section, keys in REQUIRED.items():
        if section not in cfg:
            problems.append(f"missing section '{section}'")
            continue
        problems += [f"missing '{section}.{k}'" for k in keys if k not in cfg[section]]
    if problems:
        raise ValueError(f"Invalid config {path}: " + "; ".join(problems))
    for section, values in DEFAULTS.items():
        node = cfg.setdefault(section, {})
        for k, v in values.items():
            node.setdefault(k, v)
    cfg["colmap"]["binary"] = _expand(cfg["colmap"]["binary"], "colmap.binary")
    cfg["blender"]["binary"] = _expand(cfg["blender"]["binary"], "blender.binary")
    return cfg


def apply_overrides(cfg: dict, overrides: list[str] | None) -> dict:
    for item in overrides or []:
        key, sep, raw = item.partition("=")
        if not sep:
            raise ValueError(f"Override must look like section.key=value, got '{item}'")
        node = cfg
        *parents, leaf = key.split(".")
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = yaml.safe_load(raw)
    return cfg