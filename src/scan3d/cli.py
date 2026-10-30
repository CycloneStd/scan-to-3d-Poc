from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import yaml

from .config import load_config,apply_overrides
from .logging_setup import setup_logging
from .pipeline import Context, execute
from .project import Manifest, RunDir
from .stages import ORDER, REGISTRY
from .system import doctor as doctor_mod

RUNS = Path("runs")


def _new_run(cfg: dict, run_id: str | None, prefix: str | None = None) -> RunDir:
    run_id = run_id or f"{prefix or cfg['project']['name']}-{time.strftime('%Y%m%d-%H%M%S')}"
    run = RunDir(RUNS / run_id)
    setup_logging(run.root / "logs" / "pipeline.log")
    print(f"Run directory: {run.root}")
    return run


def cmd_doctor(args):
    setup_logging()
    info = doctor_mod.collect()
    doctor_mod.print_report(info)
    if args.out:
        Path(args.out).write_text(json.dumps(info, indent=2))


def cmd_run(args):
    cfg = load_config(args.config)
    apply_overrides(cfg,args.set)
    run = _new_run(cfg, args.run_id)
    (run.root / "config.snapshot.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    requested = args.stages.split(",") if args.stages else ORDER
    unknown = [s for s in requested if s not in REGISTRY]
    if unknown:
        raise SystemExit(f"Unknown stage(s): {unknown}. Available: {ORDER}")
    names = [s for s in ORDER if s in requested]
    execute(Context(cfg, run, Manifest(run.manifest_path)), names, REGISTRY, force=args.force)


def cmd_status(args):
    manifest = Manifest(RUNS / args.run_id / "manifest.json")
    for name, rec in manifest.data["stages"].items():
        print(f"{name:<10} {rec.get('status'):<8} {rec.get('seconds', '-')}s  {rec.get('metrics', '')}")


def cmd_remote_probe(args):
    from .remote.executor import ColabExecutor

    cfg = load_config(args.config)
    run = _new_run(cfg, args.run_id, prefix="probe")
    r = cfg["remote"]
    ex = ColabExecutor(r["session"], r.get("gpu"), r.get("high_mem", True), r.get("auth"))
    with ex.open_session(keep=args.keep):
        result = ex.run_job({"action": "probe"}, run.root / "remote")
    print(json.dumps(result, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="scan3d")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="inspect local hardware and tools")
    d.add_argument("--out", help="write report JSON here")
    d.set_defaults(fn=cmd_doctor)

    r = sub.add_parser("run", help="run pipeline stages")
    r.add_argument("--config", default="configs/default.yaml")
    r.add_argument("--run-id", help="reuse an existing run to resume")
    r.add_argument("--stages", help=f"comma list from: {','.join(ORDER)}")
    r.add_argument("--force", action="store_true", help="re-run even if up to date")
    r.add_argument("--set",action="append",metavar="KEY=VALUE",help="override a config value, e.g. --set sparse.mapper=global")
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("status", help="show stage status of a run")
    s.add_argument("--run-id", required=True)
    s.set_defaults(fn=cmd_status)

    rp = sub.add_parser("remote-probe", help="start a Colab GPU VM, report its capabilities, stop it")
    rp.add_argument("--config", default="configs/default.yaml")
    rp.add_argument("--run-id")
    rp.add_argument("--keep", action="store_true", help="leave the VM running afterwards")
    rp.set_defaults(fn=cmd_remote_probe)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()