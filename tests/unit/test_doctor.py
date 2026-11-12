from types import SimpleNamespace

from scan3d.system import doctor


def test_collect_uses_existing_colmap_env_path(monkeypatch, tmp_path):
    colmap = tmp_path / "colmap"
    colmap.touch()
    monkeypatch.setenv("COLMAP_BIN", str(colmap))
    monkeypatch.setattr(doctor.shutil, "which", lambda tool: None)
    monkeypatch.setattr(doctor.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))

    calls = []

    def fake_capture(command, timeout=60):
        calls.append(command)
        if command[-1] == "-h":
            return 0, "COLMAP 4.2.1"
        return 0, "global_mapper help"

    monkeypatch.setattr(doctor, "capture", fake_capture)

    info = doctor.collect()

    assert info["tools"]["colmap"] == str(colmap)
    assert info["colmap_version"] == "COLMAP 4.2.1"
    assert info["colmap_has_global_mapper"] is True
    assert calls == [[str(colmap), "-h"], [str(colmap), "global_mapper", "-h"]]


def test_collect_keeps_colmap_missing_for_invalid_env_path(monkeypatch):
    monkeypatch.setenv("COLMAP_BIN", "/path/that/does/not/exist")
    monkeypatch.setattr(doctor.shutil, "which", lambda tool: None)
    monkeypatch.setattr(doctor.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))

    info = doctor.collect()

    assert info["tools"]["colmap"] is None
    assert "colmap_version" not in info
