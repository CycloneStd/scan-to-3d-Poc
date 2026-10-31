from __future__ import annotations

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
}


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