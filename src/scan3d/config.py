from __future__ import annotations 
from pathlib import Path

import yaml

REQUIRED = {
    "project" :["name"],
    "inputs" :["photos_dir", "videos"],
    "video" : ["fps","jpeg_quality"],
    "validation" : ["min_short_side","blur_ratio","min_brightness","max_brightness"],
    "remote" : ["session", "gpu"],
    "colmap" :["binary"],
    "features": ["camera_model", "use_gpu"],
    "sparse": ["mapper"],
}

def load_config(path: str| Path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    problems = []
    for section, keys in REQUIRED.items() :
        if section not in cfg:
            problems.append(f"Missing Section '{section}'")
            continue
        problems +=[f"missing '{section}.{k}'" for k in keys if k not in cfg[section]]

    if problems:
        raise ValueError(f"Invalid config {path}: " + "; ".join(problems))

    return cfg


def apply_overrides(cfg:dict,overrides:list[str] | None)->dict:
    for item in overrides or []:
        key,sep,raw = item.partition("=")
        if not sep:
            raise ValueError(f"Override must look like section.key=value, got '{item}'")
        node = cfg
        *parents,leaf = key.split(".")
        for part in parents:
            node = node.setdefault(part,{})
        node[leaf] = yaml.safe_load(raw)

    return cfg