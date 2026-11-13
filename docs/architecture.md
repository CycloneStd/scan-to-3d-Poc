# Architecture

One command runs a chain of stages. Each stage reads the previous stage's folder, writes its own, and records
timing and metrics in `runs/<id>/manifest.json`. A stage whose inputs and settings did not change is skipped.

| Stage | Runs on | Folder in runs/<id>/ | Produces |
|---|---|---|---|
| ingest | local CPU | 01_ingest | photos / video frames |
| validate | local CPU | 02_validate | accepted image list (blur, exposure, size) |
| reconstruction | GPU (Colab) | 06_reconstruction | features, camera poses, undistorted workspace, fused dense point cloud |
| mesh | local CPU | 07_mesh | Poisson mesh, simplified and textured |
| export | local CPU + Blender | 08_export | OBJ, GLB, renders, Blender check |
| splat | GPU (Colab) | 09_splat | Gaussian splat (.spz, compressed .ply) |
| ar | local CPU + Blender | 11_ar | AR-sized GLB and USDZ |

(Folder 10 is unused.) The mesh track sends accepted images to one Colab job for feature extraction, matching,
sparse reconstruction, undistortion, and dense reconstruction. Railway/local processing handles upload, validation,
mesh generation, and export. The splat track still uses the individual `features`, `sparse`, and `undistort` stages
before its Colab training job. Tracks: `--track mesh` (default) and `--track splat`.

## Outputs
`runs/<id>/` holds the workings. `scan3d deliver --run-id <id> --name <name>` builds the clean handoff folder
`deliverables/<name>/` (mesh/, ar/, splat/, report/, README.md, manifest.json).

## Rules
- One config per subject: copy `configs/house.yaml`, change `project.name` and `inputs.photos_dir`.
- Re-running the same command resumes; `--force` repeats a stage.
- Never edit files inside `runs/`; re-run the stage instead.
