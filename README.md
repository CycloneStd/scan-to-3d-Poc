# Cyclone Studios Scan-to-3D

Photos (or video frames) to a textured 3D mesh that opens in Blender.

## Requirements
- Linux, conda, ffmpeg, Blender 4+ (`blender` on PATH)
- COLMAP >= 4.0 in its own conda env: `conda create -n colmap4 -c conda-forge colmap=4.2`
- `export COLMAP_BIN=$HOME/anaconda3/envs/colmap4/bin/colmap`
- In the config you run, set `colmap.binary: ${COLMAP_BIN}` so the pipeline uses that version rather than another `colmap` on `PATH`.
- A Google Colab account with compute units and the `colab` CLI (`uv tool install google-colab-cli`); run `colab sessions` once to authorize

## Install
```bash
conda env create -f environment.yml && conda activate <env>
pip install -e . && pytest -q
scan3d doctor
```

## Run
Put photos in a folder and copy `configs/house.yaml`, setting `project.name` and `inputs.photos_dir`.
```bash
scan3d run --config configs/mine.yaml --stages ingest,validate,features,sparse   # free CPU gate
scan3d status --run-id <id>        # want: ~all images registered, 1 model
scan3d run --config configs/mine.yaml --run-id <id>                              # GPU + mesh stages
scan3d report --run-id <id>
```
Outputs: `runs/<id>/08_export/` (OBJ, GLB, renders) and `runs/<id>/report.md`.
Stages are cached; rerun the same command with the same `--run-id` to resume.

## Notes
See `docs/limitations.md`. A 125-photo dense run used about 80 minutes of T4 time.