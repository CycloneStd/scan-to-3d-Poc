# Cyclone Scan-to-3D

Cyclone Scan-to-3D reconstructs a scene from photographs or sampled video frames.
COLMAP estimates camera poses and sparse geometry; OpenMVS creates a dense point
cloud, mesh, and textured OBJ asset. Each reconstruction is stored under
`data/runs/<run-name>/` so intermediate results can be inspected and reused.

## Pipeline

1. **Video preprocessing (optional):** OpenCV samples chronological frames,
   downsizes large images, and writes deterministic `frame_000000.jpg` names.
2. **COLMAP sparse reconstruction:** feature extraction, sequential matching,
   mapping, and sparse model verification.
3. **COLMAP-to-OpenMVS conversion:** `image_undistorter` writes a COLMAP
   workspace; `InterfaceCOLMAP` imports its sparse model and undistorted images.
4. **OpenMVS reconstruction:** `DensifyPointCloud`, `ReconstructMesh`, and
   `TextureMesh` produce the textured mesh and its external material/texture
   files. No extra mesh-refinement operation is enabled by default.
5. **Export:** the textured OBJ bundle is checked for its MTL and referenced
   texture files, then exported to the existing web GLB/viewer output when
   `trimesh` or Blender is available.

## Setup

Create the Python environment:

```powershell
conda env create -f environment.yml
conda activate cyclone-scan
```

COLMAP and OpenMVS are external executables and are not installed by the Python
environment. Install compatible builds separately, then provide their paths
using command-line options or environment variables:

- `COLMAP_EXECUTABLE`
- `INTERFACE_COLMAP_EXECUTABLE`
- `DENSIFY_POINT_CLOUD_EXECUTABLE`
- `RECONSTRUCT_MESH_EXECUTABLE`
- `TEXTURE_MESH_EXECUTABLE`
- Optional: `BLENDER_EXECUTABLE`, `GLTF_TRANSFORM_EXECUTABLE`

The pipeline uses argument lists rather than shell command strings. Windows
COLMAP `.bat` launchers are supported by `ColmapRunner`; Linux/Colab binaries
can be selected with the same options.

## Run locally

For a directory of still photographs:

```powershell
python scripts/reconstruct.py `
  --run-name south-building `
  --input-dir D:\datasets\south-building\images `
  --colmap C:\tools\COLMAP\COLMAP.bat `
  --interface-colmap C:\tools\OpenMVS\InterfaceCOLMAP.exe `
  --densify-point-cloud C:\tools\OpenMVS\DensifyPointCloud.exe `
  --reconstruct-mesh C:\tools\OpenMVS\ReconstructMesh.exe `
  --texture-mesh C:\tools\OpenMVS\TextureMesh.exe
```

For video, frame extraction runs before reconstruction. Sampling defaults are
3 FPS, a 1920-pixel maximum dimension, JPEG output, and quality 95:

```powershell
python scripts/reconstruct.py `
  --run-name south-building `
  --input-video D:\datasets\south-building.mp4 `
  --target-fps 3 `
  --max-image-dimension 1920 `
  --colmap C:\tools\COLMAP\COLMAP.bat `
  --interface-colmap C:\tools\OpenMVS\InterfaceCOLMAP.exe `
  --densify-point-cloud C:\tools\OpenMVS\DensifyPointCloud.exe `
  --reconstruct-mesh C:\tools\OpenMVS\ReconstructMesh.exe `
  --texture-mesh C:\tools\OpenMVS\TextureMesh.exe
```

Use `--stage preprocess` with `--input-video` to only extract frames. A
preprocessing manifest binds existing frames to the source file and sampling
settings; matching frames are reused, while a different source/settings
combination is refused unless `--overwrite` is explicitly supplied for frame
replacement. Use a new run name when changing the source so COLMAP outputs are
not mixed with the previous reconstruction.

Available reconstruction stages are `sparse`, `dense` (or its `mesh` alias),
`texture`, and `export`. Run a later stage directly to resume from its validated
upstream artifact, for example:

```powershell
python scripts/reconstruct.py --run-name south-building --stage dense
python scripts/reconstruct.py --run-name south-building --stage texture
python scripts/reconstruct.py --run-name south-building --stage export
```

The COLMAP sequential matcher defaults to an overlap of 5 images and uses no
matching GPU flags. `--matching-strategy` selects a COLMAP matcher identifier;
sequential matching is the default and exhaustive matching is intentionally
disabled. The installed COLMAP help is inspected before optional overlap,
thread, feature-extraction, and image-size arguments are passed. Set
`--use-gpu` to request GPU feature extraction; a build without that capability
fails clearly. `--num-threads` controls supported COLMAP thread settings.

OpenMVS uses conservative executable defaults. Only add tuning values after
checking the installed binary's `--help` output. The CLI accepts each argument
token through repeatable options; for example:

```powershell
python scripts/reconstruct.py --run-name south-building `
  --stage dense `
  --densify-option=--resolution-level `
  --densify-option=2
```

The standard OpenMVS importer and OBJ export options follow the upstream
[InterfaceCOLMAP](https://github.com/cdcseacave/openMVS/blob/master/apps/InterfaceCOLMAP/InterfaceCOLMAP.cpp)
and [TextureMesh](https://github.com/cdcseacave/openMVS/blob/master/apps/TextureMesh/TextureMesh.cpp)
interfaces. The build installed on a user's machine must still be checked
because CLI options can differ by version.

## Outputs and resumption

Generated files are stored under `data/runs/<run-name>/` (ignored by Git):

- `frames/` — ordered images and the video preprocessing manifest, if used.
- `database.db`, `sparse/` — COLMAP database and sparse models.
- `dense/images/`, `dense/sparse/` — undistorted COLMAP workspace.
- `dense/openmvs/` — imported, dense, and mesh `.mvs` scenes.
- `dense/textured/model.obj`, `model.mtl`, and texture image(s) — Blender-ready
  textured mesh bundle with relative references.
- `web/model.glb`, `web/index.html` — optional web export and viewer.
- `logs/` and `metadata.json` — command output, per-stage status/timing, image
  counts, reconstruction counts, and output sizes.

Successful stages whose expected outputs validate are skipped on subsequent
runs, and their input signatures prevent a database or scene from being reused
for a different image set or stage configuration. Use a new `--run-name` when
changing the source images/video or sampling settings; this preserves the
previous reconstruction instead of mixing its database with new frames.
Failed stages record their error and elapsed time. Existing incomplete outputs
are preserved and cause an error unless `--overwrite` is explicitly provided;
the pipeline never removes a complete reconstruction automatically. Keep the
OBJ, MTL, and referenced texture images together when moving an asset.

To inspect the final asset in Blender, open `dense/textured/model.obj`; Blender
resolves the adjacent MTL and texture files using their relative paths. Confirm
that the material is assigned and textures appear in Material Preview. The
pipeline validates the OBJ/MTL/texture references itself and, when Blender is
available, performs a headless OBJ import/material check. A GUI visual check
remains a separate manual step.

## Google Colab

The steps below run the reconstruction in Colab and save results to Google
Drive. Your local Conda environment and desktop Blender are not available
inside Colab; you can use desktop Blender later to inspect the downloaded OBJ.

```python
from google.colab import drive
drive.mount("/content/drive")
```

### 1. Prepare Drive and install the project

Upload either a folder of overlapping photos (for example
`MyDrive/scan-input/images/`) or a video (for example
`MyDrive/scan-input/scene.mp4`) to Google Drive. The image folder must contain
at least two supported images. In Colab, choose **Runtime → Change runtime
type → T4 GPU** if available.

The pipeline has been merged into `main`. Run this cell to get the code,
install Colab's Python packages, and run the unit tests:

```bash
!git clone --branch main https://github.com/CycloneStd/scan-to-3d-Poc.git /content/scan-to-3d-Poc
%cd /content/scan-to-3d-Poc
!python -m pip install opencv-python-headless pillow trimesh pytest
!python -m pytest -q
```

Your local Conda environment is not used in Colab.

### 2. Install COLMAP and OpenMVS

These are command-line programs, separate from the Python packages above.
Install [COLMAP from Conda-forge](https://anaconda.org/conda-forge/colmap) and
download the official [OpenMVS Ubuntu x64 release](https://github.com/cdcseacave/openMVS/releases/tag/v2.4.0).
Colab itself does not start with Conda installed, so this cell uses the small
`micromamba` executable to create a separate environment for COLMAP:

```bash
!mkdir -p /content/micromamba
!curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj -C /content/micromamba bin/micromamba
!MAMBA_ROOT_PREFIX=/content/mamba-root /content/micromamba/bin/micromamba create -y -p /content/recon-env -c conda-forge colmap
!sudo apt-get update -qq
!sudo apt-get install -y unzip
!wget -q --show-progress https://github.com/cdcseacave/openMVS/releases/download/v2.4.0/OpenMVS_Ubuntu_x64.zip -O /content/OpenMVS_Ubuntu_x64.zip
!mkdir -p /content/openmvs
!unzip -q -o /content/OpenMVS_Ubuntu_x64.zip -d /content/openmvs
```

Check that COLMAP starts:

```bash
!/content/recon-env/bin/colmap -h
!nvidia-smi
```

Find and test all four OpenMVS programs. This Python cell also sets the library
search path for libraries shipped inside the OpenMVS archive and verifies that
the executables start. Run it again after reconnecting to a new Colab runtime:

```python
import os
import subprocess
from pathlib import Path

openmvs_root = Path("/content/openmvs")
openmvs_tools = {}
for name in ("InterfaceCOLMAP", "DensifyPointCloud", "ReconstructMesh", "TextureMesh"):
    matches = [
        path
        for path in openmvs_root.rglob(name)
        if path.is_file() and os.access(path, os.X_OK)
    ]
    if not matches:
        raise FileNotFoundError(f"{name} was not found in the OpenMVS archive")
    openmvs_tools[name] = matches[0]
    print(f"{name}: {matches[0]}")

library_dirs = sorted(
    {str(path.parent) for path in openmvs_root.rglob("*.so*") if path.is_file()}
)
existing_library_path = os.environ.get("LD_LIBRARY_PATH", "")
os.environ["LD_LIBRARY_PATH"] = ":".join(
    library_dirs + ([existing_library_path] if existing_library_path else [])
)

for name, executable in openmvs_tools.items():
    result = subprocess.run(
        [str(executable), "-h"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if "available options:" not in result.stdout.lower():
        raise RuntimeError(f"{name} could not start:\n{result.stdout[-3000:]}")
    print(f"{name}: help displayed (exit code {result.returncode})")
```

OpenMVS may return a nonzero exit code for its help option even when it started
correctly. This check therefore looks for the actual help text instead of
requiring exit code zero. If the check reports that help text is missing, do
not continue; the output should help identify a missing shared library or an
incompatible binary. Colab sessions are temporary, so install COLMAP and
download OpenMVS again after a runtime reset.

### 3. First run: use images

Set `--input-dir` to the Drive folder containing your photos. Do not pass
`--input-video` for an image run:

```bash
!python scripts/reconstruct.py \
  --run-name first-image-test \
  --project-root /content/drive/MyDrive/scan-to-3d-output \
  --input-dir /content/drive/MyDrive/scan-input/images \
  --colmap /content/recon-env/bin/colmap \
  --interface-colmap "$(find /content/openmvs -type f -name InterfaceCOLMAP -print -quit)" \
  --densify-point-cloud "$(find /content/openmvs -type f -name DensifyPointCloud -print -quit)" \
  --reconstruct-mesh "$(find /content/openmvs -type f -name ReconstructMesh -print -quit)" \
  --texture-mesh "$(find /content/openmvs -type f -name TextureMesh -print -quit)"
```

This runs all stages. Start with a small set of good, overlapping photos. The
run's files are saved in
`/content/drive/MyDrive/scan-to-3d-output/data/runs/first-image-test/`.

### 4. Later run: use video

When you are ready to try video, upload it to Drive and use `--input-video`
instead of `--input-dir`. Use a different run name to keep the image and video
results separate:

```bash
!python scripts/reconstruct.py \
  --run-name first-video-test \
  --project-root /content/drive/MyDrive/scan-to-3d-output \
  --input-video /content/drive/MyDrive/scan-input/scene.mp4 \
  --target-fps 3 \
  --max-image-dimension 1920 \
  --colmap /content/recon-env/bin/colmap \
  --interface-colmap "$(find /content/openmvs -type f -name InterfaceCOLMAP -print -quit)" \
  --densify-point-cloud "$(find /content/openmvs -type f -name DensifyPointCloud -print -quit)" \
  --reconstruct-mesh "$(find /content/openmvs -type f -name ReconstructMesh -print -quit)" \
  --texture-mesh "$(find /content/openmvs -type f -name TextureMesh -print -quit)"
```

Video is sampled at 3 frames per second by default. Frames and a manifest are
saved in the run folder, and the same source/settings can reuse them when
resuming.

### 5. Open the result in Blender

In Drive, open the run's `dense/textured/` folder and download the whole folder
so the OBJ, MTL, and texture images stay together. On your computer, open
`model.obj` in your Blender application and check that its textures appear.
Colab cannot use the Blender application installed on your computer.

### If Colab disconnects

Files under `/content` are temporary, but this guide stores run outputs on
Drive. After reconnecting, mount Drive again, clone the repository and install
Python packages as above. COLMAP and OpenMVS must also be made available again
in the new runtime. Rerun the same command with the same project root, run
name, and input path; the pipeline reuses completed stages when their outputs
still validate. Use a new run name if you change the input or video sampling
settings. Do not use `--overwrite` unless you intend to replace incomplete
outputs or extracted frames.

## Validation status and limitations

Unit tests use small mocked video/subprocess fixtures and do not require a GPU
or a full reconstruction. Actual COLMAP and OpenMVS runs, OpenMVS version
compatibility, Blender import, and Colab timings require the external tools and
dataset; they are not established by unit tests. Architectural geometry,
watertightness, and manifoldness are not guaranteed.
