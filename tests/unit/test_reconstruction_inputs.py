from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from scan3d.config import load_config
from scan3d.pipeline import Context, execute
from scan3d.project import Manifest, RunDir
from scan3d.remote.colab_entry import dense_view_names
from scan3d.stages import REGISTRY
from scan3d.stages.features import effective_matcher


def test_mixed_photo_inputs_survive_validation(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    Image.new("RGB", (100, 100), "grey").save(photos / "soft bridge.jpg")
    Image.new("RGB", (900, 700), "white").save(photos / "bright.jpg")
    (photos / "broken.jpg").write_bytes(b"invalid")
    cfg = load_config(Path(__file__).parents[2] / "configs" / "house.yaml")
    cfg["inputs"] = {"photos_dir": str(photos), "videos": []}
    run = RunDir(tmp_path / "run")
    ctx = Context(cfg, run, Manifest(run.manifest_path))
    execute(ctx, ["ingest", "validate"], REGISTRY)
    metrics = ctx.manifest.get("validate")["metrics"]
    assert sorted(metrics["accepted"].values()) == [0, 1, 1]
    assert metrics["quality_flags"]["blurry"] == 2
    assert metrics["quality_flags"]["unreadable"] == 1
    assert effective_matcher(cfg) == "exhaustive"


def test_dense_selection_tracks_motion_and_keeps_small_sets(tmp_path):
    model = tmp_path / "images.txt"
    names = [f"photos/{i}.jpg" for i in range(6)]
    def write(positions):
        model.write_text("".join(f"{i+1} 1 0 0 0 {-x} 0 0 1 {n}\n\n"
                                 for i, (x, n) in enumerate(zip(positions, names))))
    write([0, 0, 2, 2, 4, 4])
    chosen, registered = dense_view_names(model, [names[1], names[3], names[5]], 3)
    assert set(chosen) == set(names[::2])
    assert registered == names
    assert set(dense_view_names(model, names, 0)[0]) == set(names)
    write(np.zeros(6))
    with pytest.raises(ValueError, match="Move around"):
        dense_view_names(model, [], 4)

