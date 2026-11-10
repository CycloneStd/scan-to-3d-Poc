from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from pathlib import Path

from .bundle import sha256
from .executor import ENTRY, ColabExecutor

log = logging.getLogger("scan3d.roundtrip")


class JobFailed(RuntimeError):
    """The remote job ran and reported an error (not a connectivity problem, so not retried)."""


def roundtrip(cfg: dict, out: Path, tar: Path, digest: str, job_extra: dict, result_prefix: str):
    """Upload inputs, run a remote job, download its result. Resumable at every step; finished remote
    work is never discarded because of a transient connection problem. Returns (data, result_tar)."""
    r = cfg["remote"]
    chunk_mb = int(r.get("chunk_mb", 2))
    workers = int(r.get("upload_workers", 1))
    ex = ColabExecutor(r["session"], r.get("gpu"), r.get("high_mem", True), r.get("auth"),
                       fallback_gpus=r.get("gpu_fallbacks", []), io_timeout=int(r.get("io_timeout", 600)))
    entry_hash = hashlib.sha256(ENTRY.read_bytes()).hexdigest()[:8]
    job_id = hashlib.sha256((digest + json.dumps(job_extra, sort_keys=True) + entry_hash).encode()).hexdigest()[:16]
    parts_dir = out / f"result_parts_{job_id}"
    remote_dir = out / "remote"
    result_tar = out / "result.tar.gz"
    deadline = time.time() + float(r.get("max_hours_total", 6)) * 3600
    tm = {"upload_s": 0.0, "job_s": 0.0, "download_s": 0.0}
    t_all = time.time()
    result_ready, done, attempt = False, False, 0
    try:
        while True:
            attempt += 1
            try:
                ex.ensure_session()
                st = ex.remote_status()
                if st["result_job_id"] == job_id:
                    log.info("The VM already holds this job's result")
                elif st["pid"] and st["job_json_id"] == job_id:
                    log.info("Attaching to the job that is already running")
                    t0 = time.time()
                    ex.run_background(attach_pid=st["pid"])
                    tm["job_s"] += time.time() - t0
                else:
                    inputs = st["inputs"] or {}
                    if inputs.get("digest") == digest:
                        n = inputs["parts"]
                        log.info("Inputs are already on the VM (%d parts)", n)
                    else:
                        ex.clean_remote()
                        t0 = time.time()
                        n = ex.upload_chunked(tar, "ws.part", chunk_mb, workers=workers)
                        tm["upload_s"] += time.time() - t0
                        ex.mark_inputs(digest, n)
                    ex.put_job({"workspace_tar": "/content/workspace.tar.gz", "parts_prefix": "ws.part",
                                "num_parts": n, "sha256": digest, "chunk_bytes": chunk_mb * 1024 * 1024,
                                "job_id": job_id, **job_extra}, remote_dir)
                    t0 = time.time()
                    ex.run_background()
                    tm["job_s"] += time.time() - t0

                result = ex.fetch_result(remote_dir)
                result_ready = bool(result.get("ok"))
                if not result_ready:
                    raise JobFailed("Remote job failed:\n" + result.get("error", "unknown error"))
                data = result["data"]
                t0 = time.time()
                ex.download_parts(result_prefix, data["result_parts"], parts_dir)
                tm["download_s"] += time.time() - t0
                with open(result_tar, "wb") as fh:
                    for i in range(data["result_parts"]):
                        fh.write((parts_dir / f"{result_prefix}{i:03d}").read_bytes())
                if sha256(result_tar) != data["result_sha256"]:
                    shutil.rmtree(parts_dir, ignore_errors=True)
                    raise RuntimeError("downloaded result failed its checksum; downloading again")
                done = True
                break
            except JobFailed:
                raise
            except RuntimeError as exc:
                log.warning("Attempt %d interrupted: %s", attempt, exc)
                if time.time() > deadline:
                    raise
                time.sleep(min(30 * attempt, 180))
    finally:
        if done or not result_ready or not r.get("keep_on_failure", True):
            ex.release()
        else:
            log.warning("The finished result is still on the Colab VM. Re-run the same command to resume the "
                        "download. If you do not want to resume, stop the VM: colab stop -s %s", r["session"])
    shutil.rmtree(parts_dir, ignore_errors=True)
    data = {**data, "timing": {k: round(v, 1) for k, v in tm.items()},
            "wall_s": round(time.time() - t_all, 1), "bundle_mb": round(tar.stat().st_size / 1e6, 1),
            "upload_workers": workers, "chunk_mb": chunk_mb}
    return data, result_tar
