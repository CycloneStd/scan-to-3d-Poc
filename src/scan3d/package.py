from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .project import Manifest

ASSETS = ("scene.spz", "scene.compressed.ply", "scene.ply")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_package(run_dir: Path, out: Path) -> Path:
    mf = Manifest(run_dir / "manifest.json")
    splat = mf.get("splat")
    if not splat or splat.get("status") != "done":
        raise SystemExit("Run the splat stage to completion first.")
    src = run_dir / "09_splat"
    out.mkdir(parents=True, exist_ok=True)

    assets = {}
    for name in ASSETS:
        p = src / name
        if p.exists():
            shutil.copy2(p, out / name)
            with open(p, "rb") as fh:
                magic = fh.read(8).hex()
            assets[name] = {"bytes": p.stat().st_size, "sha256": _sha256(p), "first_bytes_hex": magic}
    if not assets:
        raise SystemExit(f"No splat assets found in {src}")

    ar_dir = run_dir / "11_ar"
    ar_files = []
    for name in ("model_ar.glb", "model_ar.usdz", "ar_report.json"):
        if (ar_dir / name).exists():
            (out / "ar").mkdir(exist_ok=True)
            shutil.copy2(ar_dir / name, out / "ar" / name)
            ar_files.append(name)

    m = splat.get("metrics", {})
    manifest = {
        "format_version": 2,
        "source_run": run_dir.name,
        "assets": assets,
        "ar_files": ar_files,
        "gaussians": m.get("num_gaussians"),
        "training": {"steps": m.get("max_steps"), "image_max_side": m.get("max_image_size"),
                     "extra_args": m.get("extra_args"), "psnr_db": m.get("psnr"), "ssim": m.get("ssim"),
                     "lpips": m.get("lpips"), "note": "held-out views (every 8th image), measured before cleanup"},
        "coordinate_system": {
            "status": "NOT PROVIDED",
            "note": "The splat is in the trainer's normalised frame: up and heading must be set by eye in the "
                    "viewer. Scale is arbitrary, not metres. The AR files are upright, with their scale "
                    "stated in ar/ar_report.json.",
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (out / "README.md").write_text(
        "# Handoff folder\n\n"
        "- `scene.spz`, `scene.compressed.ply`, or fallback `scene.ply`: Gaussian splat for web viewers "
        "(see manifest for included files, sizes, and checksums). If one format fails to load, try another "
        "and report the viewer name and version.\n"
        "- `ar/`: `model_ar.glb` (Android / web) and `model_ar.usdz` (iPad / iPhone AR Quick Look), with "
        "`ar_report.json`. Check its `scale` line: it says whether the size is real or arbitrary.\n"
        "- The splat's orientation is not provided; rotate it by eye in the viewer.\n")
    return out
