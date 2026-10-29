# Splat Reconstruction

One supported workflow: FFmpeg/OpenCV image preparation → COLMAP camera poses
and sparse points → gsplat Gaussian-splat training. There is one entry point:
`scripts/reconstruct.py`. The old mesh/OpenMVS and experimental VGGT pipelines
are removed; they are not alternate ways to run this project.

## What you need

- Linux with an NVIDIA GPU for gsplat training (Google Colab GPU runtime is
  supported). Training will stop during preflight if CUDA is unavailable.
- CUDA-enabled PyTorch and `gsplat`, installed in the same Python environment.
- COLMAP on `PATH` or its executable path. The default mapper is COLMAP's
  `global_mapper` (GLOMAP functionality integrated into COLMAP). For older
  COLMAP versions, select `--mapper mapper`.
- FFmpeg and ffprobe on `PATH` when using a video.
- At least two overlapping photos, or a video that contains overlapping views.

The 7,000-step default is a starting point, not a 15-minute guarantee. Actual
time and quality depend on GPU, image resolution/count, camera motion, scene
texture, and COLMAP version. This repository's local tests do not train a
Gaussian scene.

## Google Colab quick start

1. Select **Runtime → Change runtime type → GPU**. Mount Google Drive:

   ```python
   from google.colab import drive
   drive.mount("/content/drive")
   ```

2. Clone this repository and move into its directory:

   ```bash
   !git clone https://github.com/CycloneStd/scan-to-3d-Poc.git /content/scan-to-3d-Poc
   %cd /content/scan-to-3d-Poc
   ```

3. Install COLMAP/FFmpeg and the gsplat trainer. Colab already supplies a
   PyTorch build for its runtime; verify it is CUDA-enabled before proceeding.

   ```bash
   !apt-get update -qq
   !apt-get install -y colmap ffmpeg
   !git clone --depth 1 https://github.com/nerfstudio-project/gsplat.git /content/gsplat
   !python -m pip install -e /content/gsplat opencv-python-headless
   !colmap -h
   !python -c "import torch, gsplat; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no CUDA GPU')"
   ```

   If `colmap -h` does not list `global_mapper`, pass `--mapper mapper` below.
   If the PyTorch check says CUDA is unavailable, stop and select a GPU runtime;
   do not start a reconstruction.

4. Use a new run name for each input/settings combination. For a photo folder:

   ```bash
   !python scripts/reconstruct.py \
     --run-name first-photo-test \
     --project-dir "/content/drive/MyDrive/splat-runs" \
     --input-dir "/content/drive/MyDrive/scan-input/images" \
     --colmap colmap \
     --gsplat-trainer /content/gsplat/examples/simple_trainer.py \
     --steps 7000
   ```

   For a video, use `--input-video` instead of `--input-dir`:

   ```bash
   !python scripts/reconstruct.py \
     --run-name first-video-test \
     --project-dir "/content/drive/MyDrive/splat-runs" \
     --input-video "/content/drive/MyDrive/scan-input/scene.mp4" \
     --colmap colmap \
     --gsplat-trainer /content/gsplat/examples/simple_trainer.py \
     --fps 3 \
     --max-dimension 1920 \
     --min-sharpness 40 \
     --steps 7000
   ```

   For an older COLMAP installation, append `--mapper mapper`. Keep images
   sharply focused, well lit, and overlapping; avoid large jumps between
   consecutive video views. Start with a short clip or a small photo subset
   before submitting a full client dataset.

## Local environment

Python-side tools and COLMAP can be installed from Conda-forge:

```powershell
conda env create -f environment.yml
conda activate splat-reconstruction
```

Install a CUDA-enabled PyTorch version matching the NVIDIA driver in the
environment that will run the CLI, then install gsplat and clone its repository
to obtain `examples/simple_trainer.py`. PyTorch wheels vary by CUDA version, so
they are intentionally not pinned in the general environment file. On Windows,
the FFmpeg and COLMAP programs must be discoverable through `PATH` or supplied
with their CLI options. Gaussian training still requires a supported NVIDIA
CUDA environment.

## Outputs and safe reruns

Each run writes to `<project-dir>/<run-name>/`:

- `images/` — managed source frames; video runs include `video_manifest.json`.
- `database.db` — COLMAP features and verified image matches.
- `sparse/` — COLMAP sparse model with camera poses and 3D points.
- `sparse/0/points.ply` — portable sparse point cloud.
- `cameras_text/` — portable `cameras.txt`, `images.txt`, `points3D.txt`.
- `gsplat/` — gsplat checkpoints, trained splat PLY, and completion marker.
- `logs/` and `metadata.json` — command logs, stage state, and final paths.

The pipeline records completed stages and reuses them only when their inputs
match. It does not overwrite or mix runs: if an input or settings conflict
with existing run data, it stops and asks you to use a new `--run-name`.
Keep each run folder as the source of truth for its cameras, sparse point cloud,
and splat export. The text camera model and sparse cloud are the baseline for
later alignment, mesh/UV work, or GPS anchoring; no GPS transform is inferred
by this pipeline.

## Command reference

```text
python scripts/reconstruct.py --help
```

Common controls:

- `--mapper global_mapper|mapper`: global GLOMAP-style or incremental COLMAP
  camera reconstruction.
- `--matching exhaustive|sequential`: defaults to exhaustive for photos and
  sequential for video.
- `--gpu-features`: request CUDA SIFT extraction from COLMAP when supported.
- `--steps`: gsplat optimization steps (default 7000).
- `--fps`, `--max-dimension`, `--min-sharpness`: video sampling and blur
  filtering. The sharpness threshold is Laplacian variance; adjust it based on
  the video rather than assuming one value works for all cameras.
- `--project-dir`: persistent output root, such as a Google Drive folder.

## Tests

Run the local, GPU-independent checks with:

```powershell
python -m pytest -q
python -m compileall -q src scripts tests
```

These validate configuration, stage safety, metadata, sparse-model handling,
and frame filtering. They do not prove that a particular Colab COLMAP build or
GPU completes a full reconstruction.
