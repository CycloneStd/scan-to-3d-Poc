from __future__ import annotations

import os
import platform
import shutil
import sys

from ..utils.proc import capture

TOOLS = ["git", "ffmpeg", "ffprobe", "colmap", "blender", "colab", "nvidia-smi", "nvcc"]


def _mem_gb() -> float | None:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                return round(int(line.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    return None


def collect() -> dict:
    tools = {t: shutil.which(t) for t in TOOLS}
    info: dict = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "ram_gb": _mem_gb(),
        "disk_free_gb": round(shutil.disk_usage(".").free / 1e9, 1),
        "tools": tools,
    }
    if tools["nvidia-smi"]:
        info["gpu"] = capture(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])[1]
    else:
        info["gpu"] = None
    if tools["colmap"]:
        _, out = capture(["colmap", "-h"])
        banner = next((ln for ln in out.splitlines() if "COLMAP" in ln), "")
        info["colmap_version"] = banner.strip()
        rc, gm = capture(["colmap", "global_mapper", "-h"])
        info["colmap_has_global_mapper"] = rc == 0 and "not recognized" not in gm
    if tools["blender"]:
        _, out = capture(["blender", "--version"], timeout=120)
        info["blender_version"] = out.splitlines()[0] if out else None
    return info


def print_report(info: dict) -> None:
    for k, v in info.items():
        if k == "tools":
            for t, path in v.items():
                print(f"  {'OK ' if path else 'MISSING'} {t:<12} {path or ''}")
        else:
            print(f"{k}: {v}")