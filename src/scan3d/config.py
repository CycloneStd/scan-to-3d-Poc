from __future__ import annotations

import os
from copy import deepcopy
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
    "undistort": {"max_image_size": 2400},
    "dense": {"backend": "colmap", "geom_consistency": True, "min_registered_fraction": 0.2, "view_limit": 40, "source_views": 6, "window_step": 2, "max_image_size": 1024, "colmap_specs": ["colmap=4.2.1=cuda_129*"]},
    "mesh": {"texture": True, "target_face_ratio": 0.15, "poisson_depth": 11, "poisson_trim": 7, "max_edge_factor": 6.0, "min_component_faces": 150},
    "blender": {"binary": "blender"},
    "export": {"flip_v": False},
    "video": {"select": "motion_sharpest", "oversample": 3},
    "features": {"learned_recovery": True, "matcher": "auto", "sequential_overlap": 15, "max_image_size": 2000, "num_threads": 1},
    "remote": {"high_mem": False, "chunk_mb": 4, "io_timeout": 600, "max_hours_total": 6, "keep_on_failure": True,
               "upload_workers": 4},
    "splat": {"max_steps": 30000, "data_factor": 1, "upload_jpeg_quality": 90,
              "max_image_size": None,
              "extra_args": [],
              "download_ply": False, "compress": ["spz", "compressed.ply"],
              "clean": {"min_opacity": 0.3, "max_scale_frac": 0.05, "crop_factor": 1.5}},
              
    "ar": {"target_faces": 120000, "texture_px": 4096, "jpeg_quality": 90, "scale_factor": None},
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
            if k not in node:
                node[k] = deepcopy(v)
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
