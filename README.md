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

Use Colab as an execution environment; keep the source and changes in GitHub.
Mount Drive in the notebook (not in the reconstruction library), clone or
checkout the feature branch, install Python dependencies, and make compatible
COLMAP/OpenMVS binaries available on `PATH` or pass their paths:

```python
from google.colab import drive
drive.mount("/content/drive")
```

```bash
!git clone https://github.com/CycloneStd/scan-to-3d-Poc.git /content/scan-to-3d-Poc
%cd /content/scan-to-3d-Poc
!git fetch origin feat/hybrid-colmap-openmvs
!git switch --track -c feat/hybrid-colmap-openmvs origin/feat/hybrid-colmap-openmvs
!python -m pip install opencv-python pytest trimesh
```

Install/locate compatible binaries for the current Colab runtime and verify
their help output and GPU availability before starting. Avoid assuming that a
binary package or installation command remains compatible across runtime
images. Then run against a Drive path and persist the run directory to Drive:

```bash
!python scripts/reconstruct.py \
  --run-name south-building \
  --project-root /content/drive/MyDrive/scan-to-3d-output \
  --input-video /content/drive/MyDrive/south-building.mp4 \
  --colmap /usr/local/bin/colmap \
  --interface-colmap /usr/local/bin/InterfaceCOLMAP \
  --densify-point-cloud /usr/local/bin/DensifyPointCloud \
  --reconstruct-mesh /usr/local/bin/ReconstructMesh \
  --texture-mesh /usr/local/bin/TextureMesh
```

`--project-root` places all run data, logs, and metadata on Drive while source
code stays checked out under `/content`. Pass the same project root and run
name after a disconnect, then invoke `--stage dense`, `--stage texture`, or
`--stage export` to continue from the latest validated stage. The under-15-
minute T4 goal is an optimization target only; no runtime claim is made without
a measured comparable run.

### Colab integration procedure

Use a small representative capture after confirming that all four OpenMVS
executables and COLMAP are available. Run each stage with the same project
root, run name, and source; the video manifest reuses the already extracted
frames:

```bash
!python -m pytest -q
!python scripts/reconstruct.py --project-root /content/drive/MyDrive/scan-to-3d-output --run-name colab-check --input-video /content/drive/MyDrive/sample.mp4 --stage sparse --colmap /usr/local/bin/colmap --interface-colmap /usr/local/bin/InterfaceCOLMAP --densify-point-cloud /usr/local/bin/DensifyPointCloud --reconstruct-mesh /usr/local/bin/ReconstructMesh --texture-mesh /usr/local/bin/TextureMesh
!python scripts/reconstruct.py --project-root /content/drive/MyDrive/scan-to-3d-output --run-name colab-check --input-video /content/drive/MyDrive/sample.mp4 --stage dense --colmap /usr/local/bin/colmap --interface-colmap /usr/local/bin/InterfaceCOLMAP --densify-point-cloud /usr/local/bin/DensifyPointCloud --reconstruct-mesh /usr/local/bin/ReconstructMesh --texture-mesh /usr/local/bin/TextureMesh
!python scripts/reconstruct.py --project-root /content/drive/MyDrive/scan-to-3d-output --run-name colab-check --stage texture --colmap /usr/local/bin/colmap --interface-colmap /usr/local/bin/InterfaceCOLMAP --densify-point-cloud /usr/local/bin/DensifyPointCloud --reconstruct-mesh /usr/local/bin/ReconstructMesh --texture-mesh /usr/local/bin/TextureMesh
!python scripts/reconstruct.py --project-root /content/drive/MyDrive/scan-to-3d-output --run-name colab-check --stage export --colmap /usr/local/bin/colmap --interface-colmap /usr/local/bin/InterfaceCOLMAP --densify-point-cloud /usr/local/bin/DensifyPointCloud --reconstruct-mesh /usr/local/bin/ReconstructMesh --texture-mesh /usr/local/bin/TextureMesh
```

Confirm nonempty stage outputs, successful statuses and timings in
`data/runs/colab-check/metadata.json`, inspect the saved logs, and open
`dense/textured/model.obj` in Blender. Run `--stage dense` once more to verify
that valid dense outputs are resumed rather than recomputed. This procedure
has not been run in Colab in this development environment.

## Validation status and limitations

Unit tests use small mocked video/subprocess fixtures and do not require a GPU
or a full reconstruction. Actual COLMAP and OpenMVS runs, OpenMVS version
compatibility, Blender import, and Colab timings require the external tools and
dataset; they are not established by unit tests. Architectural geometry,
watertightness, and manifoldness are not guaranteed.
