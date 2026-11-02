from scan3d.config import apply_overrides
from scan3d.stages.sparse import parse_stats,registered_per_group


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

def test_registered_per_group(tmp_path):
    f = tmp_path / "images.txt"
    f.write_text(
        "# header\n# more\n"
        "1 1 0 0 0 0 0 0 1 photos/a.jpg\n1.0 2.0 5\n"
        "2 1 0 0 0 0 0 0 1 photos/b.jpg\n\n"          # image with an empty points line
        "3 2 0 0 0 0 0 0 2 video_x/c.jpg\n3.0 4.0 7\n"
    )
    assert registered_per_group(f) == {"photos": 2, "video_x": 1}