# Moving to a GPU production machine (design, not implemented)

## What "everything on the GPU" can mean
GPU: splat training, dense depth maps (PatchMatch), optional SIFT feature matching.
CPU even on a GPU server: bundle adjustment (mostly), Poisson meshing, simplification, texturing, Blender export.
So the goal is: the whole pipeline runs on one machine that has a GPU, with no laptop and no Colab in between.

## What worked on the development setup (Colab T4, 16 GB)
- COLMAP 4.2.1 CUDA build (conda-forge), gsplat 1.5.3 + its example requirements (CUDA extension compiles on first use)
- Blender 5.x (headless export), ffmpeg, Node only for splat-transform (SPZ / compressed PLY)

## Code changes needed (estimate: small, but untested)
1. A local executor that runs the dense and splat jobs on the same machine (no upload/download).
2. `features.use_gpu: true` with the CUDA COLMAP build.
3. A container image holding the installs above, so no per-run setup.
4. A job queue and status API around `scan3d run` (later sprint).

## Open questions
Which machine (GPU model and memory), where captures are stored, retention policy, who may access results.
