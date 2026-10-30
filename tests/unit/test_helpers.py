from scan3d.config import apply_overrides
from scan3d.stages.sparse import parse_stats


def test_overrides():
    cfg = {"sparse": {"mapper": "incremental"}, "inputs": {"videos": ["a.mp4"]}}
    apply_overrides(cfg, ["sparse.mapper=global", "inputs.videos=[]", "new.key=3"])
    assert cfg["sparse"]["mapper"] == "global"
    assert cfg["inputs"]["videos"] == []
    assert cfg["new"]["key"] == 3


def test_parse_stats():
    text = "I2026 model_analyzer.cc:1] Registered images: 148\nI2026 x.cc:2] Mean reprojection error: 0.71px\n"
    s = parse_stats(text)
    assert s["registered_images"] == 148 and s["mean_reprojection_error"] == 0.71