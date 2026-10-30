from __future__ import annotations 
from pathlib import Path

import yaml

REQUIRED = {
    "project" :["name"],
    "inputs" :["photos_dir", "videos"],
    "video" : ["fps","jpeg_quality"],
    "validation" : ["min_short_side","blur_ratio","min_brightness","max_brightness"],
    "remote" : ["session", "gpu"],
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