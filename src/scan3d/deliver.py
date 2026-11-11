from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

from .ar import estimate_up, orient_obj
from .project import Manifest

DESCRIPTIONS = {
    "mesh/model.obj": "Editable textured mesh (OBJ), upright, ground at Y=0",
    "mesh/model.mtl": "Material file for model.obj",
    "mesh/texture.png": "Texture image for model.obj",
    "ar/model_ar.glb": "AR/web-sized mesh (GLB): Android Scene Viewer, WebXR, model-viewer",
    "ar/model_ar.usdz": "AR-sized mesh (USDZ): iPhone/iPad AR Quick Look",
    "ar/ar_report.json": "Face count, texture size and scale status of the AR files",
    "splat/scene.spz": "Gaussian splat, SPZ format (web viewers)",
    "splat/scene.compressed.ply": "Gaussian splat, PlayCanvas compressed PLY (web viewers)",
    "splat/scene.ply": "Gaussian splat, standard PLY (Blender 3DGS add-on)",
    "splat/stats.json": "Held-out-view quality numbers from training",
    "report/report.md": "Stage-by-stage timings and metrics",
    "report/blender_report.json": "Blender import check of the full mesh",
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deliver(run_dir: Path, out: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    requested_out = Path(out).expanduser().absolute()
    if requested_out.is_symlink():
        raise ValueError("Delivery output must not be a symlink")
    out = requested_out.resolve()
    if out == run_dir or out in run_dir.parents or run_dir in out.parents:
        raise ValueError("Delivery output must not overlap the source run directory")

    stages = Manifest(run_dir / "manifest.json").data["stages"]
    metrics = lambda name: (stages.get(name) or {}).get("metrics") or {}

    ar_report = {}
    if (run_dir / "11_ar" / "ar_report.json").exists():
        ar_report = json.loads((run_dir / "11_ar" / "ar_report.json").read_text())
    scale = ar_report.get("scale_factor")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    missing: list[str] = []

    wanted = {
        "ar/model_ar.glb": run_dir / "11_ar" / "model_ar.glb",
        "ar/model_ar.usdz": run_dir / "11_ar" / "model_ar.usdz",
        "ar/ar_report.json": run_dir / "11_ar" / "ar_report.json",
        "splat/scene.spz": run_dir / "09_splat" / "scene.spz",
        "splat/scene.compressed.ply": run_dir / "09_splat" / "scene.compressed.ply",
        "splat/scene.ply": run_dir / "09_splat" / "scene.ply",
        "splat/stats.json": run_dir / "09_splat" / "stats.json",
        "report/report.md": run_dir / "report.md",
        "report/blender_report.json": run_dir / "08_export" / "blender_report.json",
    }
    for path in sorted((run_dir / "08_export").glob("view_*.png")):
        wanted[f"report/{path.name}"] = path
    for relative, source in wanted.items():
        if source.exists():
            (out / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, out / relative)
        elif relative in DESCRIPTIONS and not relative.endswith("scene.ply"):
            missing.append(relative)

    mesh_src = run_dir / "08_export" / "exports" / "textured"
    mesh_note = "not included"
    if all((mesh_src / name).exists() for name in ("model.obj", "model.mtl", "texture.png")):
        (out / "mesh").mkdir()
        for name in ("model.obj", "model.mtl", "texture.png"):
            shutil.copy2(mesh_src / name, out / "mesh" / name)
        mapper = (stages.get("sparse") or {}).get("metrics", {}).get("mapper", "incremental")
        images_txt = run_dir / f"04_sparse_{mapper}" / "best_model_txt" / "images.txt"
        if images_txt.exists():
            up, _, _ = estimate_up(images_txt)
            info = orient_obj(out / "mesh" / "model.obj", up, scale)
            mesh_note = (f"upright, size x/y/z = {info['size_x_y_z']} "
                         f"({'scaled' if scale else 'UNSCALED model units'})")
        else:
            mesh_note = "NOT oriented (camera file missing)"
    else:
        missing += ["mesh/model.obj", "mesh/model.mtl", "mesh/texture.png"]

    sparse_metrics, splat_metrics, mesh_metrics = metrics("sparse"), metrics("splat"), metrics("mesh")
    best = sparse_metrics.get("best_model") or {}
    manifest = {
        "name": out.name,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_run": run_dir.name,
        "quality": {
            "sparse": {"registered_images": best.get("registered_images"),
                       "by_group": sparse_metrics.get("registered_by_group"),
                       "mean_reprojection_error_px": best.get("mean_reprojection_error")},
            "mesh": {"faces_full": mesh_metrics.get("full_faces"), "faces_editable": mesh_metrics.get("mesh_faces")},
            "ar": {"faces": ar_report.get("faces"), "glb_bytes": ar_report.get("glb_bytes"),
                   "usdz_bytes": ar_report.get("usdz_bytes")},
            "splat": {"gaussians": splat_metrics.get("num_gaussians"), "steps": splat_metrics.get("max_steps"),
                      "image_max_side": splat_metrics.get("max_image_size"), "psnr_db": splat_metrics.get("psnr"),
                      "ssim": splat_metrics.get("ssim"), "lpips": splat_metrics.get("lpips"),
                      "note": "held-out views, measured before cleanup; compare only at equal image size"},
        },
        "scale": ar_report.get("scale", "no AR step run"),
        "orientation": {"mesh": mesh_note, "ar": "upright, ground at Y=0",
                        "splat": "NOT oriented: set up and heading by eye in the viewer; scale is arbitrary"},
        "stages": {name: {"status": record.get("status"), "seconds": record.get("seconds")}
                   for name, record in stages.items()},
        "not_included": missing,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    rows = []
    for path in sorted(out.rglob("*")):
        relative = str(path.relative_to(out))
        if path.is_file() and relative not in ("README.md", "manifest.json"):
            description = DESCRIPTIONS.get(
                relative, "Render of the full mesh (axis-aligned view)" if relative.startswith("report/view_") else "")
            rows.append(f"| `{relative}` | {path.stat().st_size / 1e6:.1f} MB | {description} |")
    (out / "README.md").write_text(
        f"# {out.name}\n\nBuilt from run `{run_dir.name}` on {manifest['created']}.\n\n"
        "## Files\n\n| File | Size | What it is |\n|---|---|---|\n" + "\n".join(rows) + "\n\n"
        "## How to open\n\n"
        "- **Mesh (OBJ):** Blender, File > Import > Wavefront (.obj). Keep the .mtl and texture next to it.\n"
        "- **iPhone/iPad AR:** open `ar/model_ar.usdz` in Files (AR Quick Look).\n"
        "- **Android/web AR:** `ar/model_ar.glb` (Scene Viewer, model-viewer, WebXR).\n"
        "- **Splat:** a Gaussian-splat viewer (SPZ or compressed PLY). In Blender use the 3DGS Render add-on "
        "with a standard PLY.\n\n"
        f"## Scale and orientation\n\n- Scale: {manifest['scale']}\n- Mesh: {mesh_note}\n"
        "- Splat: not oriented, scale arbitrary.\n\n"
        "## Known limits\n\nOnly surfaces seen in the photos are reconstructed (roofs and hidden sides are "
        "missing); glass, foliage and shiny surfaces reconstruct poorly; splats show haze at thinly covered "
        "edges. Full list: `docs/limitations.md` in the repository. See `manifest.json` for checksums, "
        "quality numbers and anything not included.\n")

    manifest["files"] = [
        {"file": str(path.relative_to(out)), "bytes": path.stat().st_size, "sha256": _sha(path)}
        for path in sorted(out.rglob("*")) if path.is_file() and path.name != "manifest.json"
    ]
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
