"""Generates notebooks/colab_run.ipynb (ordered Colab run). Run: python notebooks/build_notebook.py"""
import json
from pathlib import Path

C = []
def md(s): C.append(("markdown", s))
def code(s): C.append(("code", s))

md("""# Cyclone Scan-to-3D: ordered Colab run
Runtime > Change runtime type > **T4 GPU**. Run cells top to bottom. Every run uses a NEW run name and
writes to Drive; nothing is overwritten. After a runtime reset, re-run cells 0-4 and then the stage cell you were on
(the pipeline resumes completed stages).""")

code("""# 0. Mount Drive + paths
from google.colab import drive
drive.mount('/content/drive')
import os
os.environ['DATASET'] = '/content/drive/MyDrive/Cyclone Studios/Dataset'
os.environ['PROJ'] = '/content/drive/MyDrive/Cyclone Studios/scan-to-3d-output'   # runs go to $PROJ/data/runs/<name>
os.environ['REPO'] = '/content/scan-to-3d-Poc'
!ls "$DATASET" | head -5
!ls "$DATASET" | wc -l""")

code("""# 1. Record the environment (GPU, CUDA, disk, RAM)
!nvidia-smi
!python --version
!nvcc --version | tail -2
!df -h /content | tail -1
!free -g | head -2
import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())""")

code("""# 2. Code (feature branch) + unit tests
!rm -rf "$REPO"
!git clone --branch feat/reconstruction-diagnostics https://github.com/CycloneStd/scan-to-3d-Poc.git "$REPO"
%cd /content/scan-to-3d-Poc
!pip install -q opencv-python-headless pillow trimesh pytest scipy networkx open3d
!python -m pytest -q 2>&1 | tail -5""")

code("""# 3. Install COLMAP (conda-forge) and OpenMVS v2.4.0
!mkdir -p /content/micromamba && curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C /content/micromamba bin/micromamba
!MAMBA_ROOT_PREFIX=/content/mamba-root /content/micromamba/bin/micromamba create -y -p /content/recon-env -c conda-forge colmap
!wget -q https://github.com/cdcseacave/openMVS/releases/download/v2.4.0/OpenMVS_Ubuntu_x64.zip -O /content/omvs.zip
!mkdir -p /content/openmvs && unzip -q -o /content/omvs.zip -d /content/openmvs
!/content/recon-env/bin/colmap -h | head -3""")

code("""# 4. Locate OpenMVS tools, set env vars the pipeline reads, smoke-test them. STOP if any prints FAIL.
import os, subprocess, pathlib
names = {'InterfaceCOLMAP': 'INTERFACE_COLMAP_EXECUTABLE', 'DensifyPointCloud': 'DENSIFY_POINT_CLOUD_EXECUTABLE',
         'ReconstructMesh': 'RECONSTRUCT_MESH_EXECUTABLE', 'RefineMesh': 'REFINE_MESH_EXECUTABLE',
         'TextureMesh': 'TEXTURE_MESH_EXECUTABLE'}
libs = sorted({str(p.parent) for p in pathlib.Path('/content/openmvs').rglob('*.so*')})
os.environ['LD_LIBRARY_PATH'] = ':'.join(libs + [os.environ.get('LD_LIBRARY_PATH', '')])
os.environ['COLMAP_EXECUTABLE'] = '/content/recon-env/bin/colmap'
for n, var in names.items():
    m = [p for p in pathlib.Path('/content/openmvs').rglob(n) if p.is_file()]
    assert m, n + ' not found'
    os.chmod(m[0], 0o755); os.environ[var] = str(m[0])
    r = subprocess.run([str(m[0]), '-h'], capture_output=True, text=True)
    out = (r.stdout + r.stderr)
    print(n, 'OK' if 'available options' in out.lower() else 'FAIL\\n' + out[-500:])""")

code("""# 5. Dataset check + evenly spaced 20-image SUBSET (originals are only read)
import glob, shutil, numpy as np
files = sorted(glob.glob(os.environ['DATASET'] + '/*.[jJ][pP][gG]'))
print(len(files), 'jpgs found')
assert len(files) > 20
shutil.rmtree('/content/subset20', ignore_errors=True); os.makedirs('/content/subset20')
for i in np.linspace(0, len(files) - 1, 20).round().astype(int): shutil.copy(files[i], '/content/subset20')
print(len(os.listdir('/content/subset20')), 'images in subset')""")

code("""# 6. SMOKE TEST: classical COLMAP + OpenMVS on the subset (resolution-level 2 = fast). Expect minutes, not hours.
%cd /content/scan-to-3d-Poc
!python scripts/reconstruct.py --run-name south-building-smoke-01 --project-root "$PROJ" --input-dir /content/subset20 --colmap "$COLMAP_EXECUTABLE" --use-gpu --no-refine --densify-option=--resolution-level --densify-option=2""")

code("""# 7. Inspect smoke output independently of the pipeline
RUN = os.environ['PROJ'] + '/data/runs/south-building-smoke-01'
os.environ['RUN'] = RUN
!ls -la "$RUN/dense/textured" "$RUN/dense/openmvs"
!head -c 3000 "$RUN/metadata.json"
!python scripts/inspect_mesh.py "$RUN/dense/textured/model.obj" --out "$RUN/diagnostics" --json "$RUN/diagnostics/report.json" | head -60""")

code("""# 8. AI candidate feasibility: VGGT (pretrained inference only) on the same 20 images
!git clone -q https://github.com/facebookresearch/vggt /content/vggt
!pip install -q -r /content/vggt/requirements.txt
!pip install -q -e /content/vggt
%cd /content/scan-to-3d-Poc
!python scripts/vggt_reconstruct.py --images /content/subset20 --out "$PROJ/south-building-vggt-test-01" --max-images 20
!python scripts/inspect_mesh.py "$PROJ/south-building-vggt-test-01/mesh.ply" --out "$PROJ/south-building-vggt-test-01/diagnostics" | head -40""")

md("""**STOP and compare.** Send me the output of cells 4, 6, 7 and 8 (and the PNGs in each `diagnostics` folder).
Run cell 9 only if cell 7 shows a dense, textured OBJ.""")

code("""# 9. FULL run, all images. Resume-safe: after a reset, redo cells 0-4 and re-run this cell.
%cd /content/scan-to-3d-Poc
!python scripts/reconstruct.py --run-name south-building-final-01 --project-root "$PROJ" --input-dir "$DATASET" --colmap "$COLMAP_EXECUTABLE" --use-gpu --no-refine""")

code("""# 10. Validate final mesh and bundle for Blender (keep OBJ + MTL + PNG together)
RUN = os.environ['PROJ'] + '/data/runs/south-building-final-01'
os.environ['RUN'] = RUN
!python scripts/inspect_mesh.py "$RUN/dense/textured/model.obj" --out "$RUN/diagnostics" --json "$RUN/diagnostics/report.json"
!cd "$RUN/dense" && zip -r "$RUN/model_bundle.zip" textured
from google.colab import files; files.download(RUN + '/model_bundle.zip')""")

nb = {"nbformat": 4, "nbformat_minor": 5,
      "metadata": {"accelerator": "GPU", "colab": {"provenance": []},
                   "kernelspec": {"name": "python3", "display_name": "Python 3"}},
      "cells": []}
for kind, src in C:
    cell = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
    if kind == "code":
        cell.update(outputs=[], execution_count=None)
    nb["cells"].append(cell)
Path(__file__).with_name("colab_run.ipynb").write_text(json.dumps(nb, indent=1), encoding="utf-8")
print(len(nb["cells"]), "cells written")
