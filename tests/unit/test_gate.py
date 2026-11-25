from scan3d.stages.sparse import gate_status


def test_gate():
    assert gate_status({"photos": {"registered": 125, "input": 125}}, 0.9)["passed"]
    assert not gate_status({"photos": {"registered": 48, "input": 125}}, 0.9)["passed"]
    assert not gate_status({"photos": {"registered": 125, "input": 125}, "video": {"registered": 0, "input": 25}}, 0.9)["passed"]
    assert not gate_status({}, 0.9)["passed"]
