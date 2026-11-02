import pytest

from scan3d.pipeline import Context, Stage, execute
from scan3d.project import Manifest, RunDir, fingerprint


class Counter(Stage):
    name = "a"
    dir_name = "01_a"
    calls = 0

    def config_slice(self, cfg):
        return cfg.get("a")

    def run(self, ctx):
        Counter.calls += 1
        return {"n": Counter.calls}


class Dependent(Stage):
    name = "b"
    dir_name = "02_b"
    requires = ("a",)

    def run(self, ctx):
        return {}


def make_ctx(tmp_path, cfg):
    run = RunDir(tmp_path / "run")
    return Context(cfg, run, Manifest(run.manifest_path))


def test_fingerprint_is_stable():
    assert fingerprint({"x": 1, "y": [2]}) == fingerprint({"y": [2], "x": 1})


def test_skip_rerun_and_invalidate(tmp_path):
    Counter.calls = 0
    reg = {"a": Counter()}
    ctx = make_ctx(tmp_path, {"a": 1})
    execute(ctx, ["a"], reg)
    execute(ctx, ["a"], reg)
    assert Counter.calls == 1                       # second run skipped
    ctx.cfg["a"] = 2
    execute(ctx, ["a"], reg)
    assert Counter.calls == 2                       # config change re-runs
    execute(ctx, ["a"], reg, force=True)
    assert Counter.calls == 3                       # force re-runs


def test_missing_upstream_fails(tmp_path):
    ctx = make_ctx(tmp_path, {})
    with pytest.raises(RuntimeError):
        execute(ctx, ["b"], {"b": Dependent()})