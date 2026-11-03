from __future__ import annotations

import logging
from pathlib import Path

from .bundle import sha256
from .executor import ColabExecutor

log = logging.getLogger("scan3d.roundtrip")


def roundtrip(cfg: dict, out: Path, tar: Path, digest: str, job_extra: dict, result_prefix: str):
    """Upload `tar` in chunks, run a remote job, download its chunked result. Returns (data, result_tar)."""
    r = cfg["remote"]
    chunk_mb = int(r.get("chunk_mb", 4))
    ex = ColabExecutor(r["session"], r.get("gpu"), r.get("high_mem", True), r.get("auth"),
                       fallback_gpus=r.get("gpu_fallbacks", []))
    result_tar = out / "result.tar.gz"
    result = None
    for attempt in (1, 2, 3):
        try:
            with ex.open_session():
                n = ex.upload_chunked(tar, "ws.part", chunk_mb)
                job = {"workspace_tar": "/content/workspace.tar.gz", "parts_prefix": "ws.part",
                       "num_parts": n, "sha256": digest, "chunk_bytes": chunk_mb * 1024 * 1024, **job_extra}
                result = ex.run_job(job, out / "remote")
                if result.get("ok"):
                    ex.download_chunked(result_prefix, result["data"]["result_parts"], result_tar)
            break
        except RuntimeError as exc:
            log.warning("Remote attempt %d failed: %s", attempt, exc)
            if attempt == 3:
                raise
    if not result or not result.get("ok"):
        raise RuntimeError("Remote job failed:\n" + (result or {}).get("error", "unknown error"))
    if sha256(result_tar) != result["data"]["result_sha256"]:
        raise RuntimeError("Downloaded result failed its checksum; re-run the stage")
    return result["data"], result_tar