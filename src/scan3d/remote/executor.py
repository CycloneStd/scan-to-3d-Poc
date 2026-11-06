from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .bundle import split_file

log = logging.getLogger("scan3d.remote")
ENTRY = Path(__file__).with_name("colab_entry.py")
LAUNCH_CODE = """
import subprocess, sys
p = subprocess.run(f"nohup {sys.executable} /content/colab_entry.py > /content/job.log 2>&1 & echo $!",
                   shell=True, capture_output=True, text=True)
print('@@PID@@' + p.stdout.strip())
"""

POLL_CODE = """
import json, os
pid, offset = __PID__, __OFFSET__

def alive(pid):
    try:
        return open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return False

chunk, new_offset = '', offset
try:
    with open('/content/job.log', 'rb') as f:
        f.seek(offset)
        data = f.read(6000)
        new_offset = offset + len(data)
        chunk = data.decode('utf-8', 'replace')
except OSError:
    pass
print('@@STATE@@' + json.dumps({'done': os.path.exists('/content/result.json'), 'alive': alive(pid),
                                'chunk': chunk, 'offset': new_offset}))
"""


class SessionLost(RuntimeError):
    """The Colab VM no longer exists on the server (reclaimed or disconnected)."""


class ColabExecutor:
    """Thin adapter over the `colab` CLI. Fire-and-forget commands, JSON job protocol."""

    def __init__(self, session: str, gpu: str | None = "T4", high_mem: bool = True,
                 auth: str | None = None, fallback_gpus=(), io_timeout: int = 180):
        self.session, self.gpu, self.high_mem, self.auth = session, gpu, high_mem, auth
        self.fallback_gpus = list(fallback_gpus)
        self.io_timeout = io_timeout
        self.active_gpu = None

    def _base(self) -> list[str]:
        return ["colab"] + (["--auth", self.auth] if self.auth else [])

    def _try_colab(self, *args: str, timeout: int | None = None) -> bool:
        cmd = self._base() + list(args)
        log.info("$ %s", " ".join(cmd))
        try:
            return subprocess.run(cmd, timeout=timeout).returncode == 0
        except subprocess.TimeoutExpired:
            log.warning("colab %s timed out after %ss", " ".join(args[:2]), timeout)
            return False

    def _colab(self, *args: str, timeout: int | None = None) -> None:
        if not self._try_colab(*args, timeout=timeout):
            raise RuntimeError(f"colab command failed: colab {' '.join(args[:4])}")

    def alive(self) -> bool:
        try:
            p = subprocess.run(self._base() + ["sessions"], capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return False
        return self.session in (p.stdout + p.stderr)

    def new(self, retries: int = 2, wait_s: int = 45) -> None:
        combos = [(g, hm) for g in [self.gpu] + self.fallback_gpus
                  for hm in ([True, False] if self.high_mem else [False])]
        for attempt in range(retries + 1):
            for gpu, hm in combos:
                args = ["new", "-s", self.session]
                if gpu:
                    args += ["--gpu", gpu]
                if hm:
                    args += ["--high-mem"]
                if self._try_colab(*args, timeout=300):
                    self.active_gpu = gpu
                    log.info("Allocated runtime: gpu=%s high_mem=%s", gpu, hm)
                    return
                log.warning("Allocation failed for gpu=%s high_mem=%s", gpu, hm)
            if attempt < retries:
                log.info("Waiting %ds before retrying allocation...", wait_s)
                time.sleep(wait_s)
        raise RuntimeError("Could not allocate a Colab runtime. Check `colab sessions` and `colab usage`.")

    def upload(self, local: Path, remote: str) -> None:
        self._colab("upload", "-s", self.session, str(local), remote, timeout=self.io_timeout)

    def download(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        self._colab("download", "-s", self.session, remote, str(local), timeout=self.io_timeout)

    def exec_file(self, script: Path) -> None:
        self._colab("exec", "-s", self.session, "-f", str(script))     # long jobs: no timeout

    def ping(self) -> None:
        """Trivial kernel execution, to keep the session active during long file transfers."""
        try:
            subprocess.run(self._base() + ["exec", "-s", self.session], input="print('keepalive')\n",
                           text=True, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            log.warning("keepalive ping timed out")

    def _exec_code(self, code: str, timeout: int = 120) -> str:
        p = subprocess.run(self._base() + ["exec", "-s", self.session], input=code, text=True,
                           capture_output=True, timeout=timeout)
        if p.returncode != 0:
            raise RuntimeError(f"colab exec failed: {(p.stderr or p.stdout)[-300:]}")
        return p.stdout

    def run_background(self, poll_s: int = 30, max_hours: float = 8.0) -> None:
        """Launch colab_entry.py detached on the VM, then poll with short calls until it finishes."""
        self.upload(ENTRY, "/content/colab_entry.py")
        m = re.search(r"@@PID@@(\d+)", self._exec_code(LAUNCH_CODE))
        if not m:
            raise RuntimeError("could not launch the remote job")
        pid, offset, failures = int(m.group(1)), 0, 0
        deadline = time.time() + max_hours * 3600
        while time.time() < deadline:
            try:
                out = self._exec_code(POLL_CODE.replace("__PID__", str(pid)).replace("__OFFSET__", str(offset)))
                st = json.loads(out.split("@@STATE@@", 1)[1].strip().splitlines()[0])
                failures = 0
            except (RuntimeError, subprocess.TimeoutExpired, IndexError, ValueError):
                failures += 1
                if failures >= 8 and not self.alive():
                    raise SessionLost(f"Session '{self.session}' disappeared while the job was running")
                if failures >= 30:
                    raise RuntimeError("lost contact with the remote job")
                time.sleep(poll_s)
                continue
            if st["chunk"]:
                print(st["chunk"], end="", flush=True)
            offset = st["offset"]
            if st["done"]:
                return
            if not st["alive"]:
                raise RuntimeError("the remote job exited without writing a result; see the log above")
            if len(st["chunk"]) < 6000:
                time.sleep(poll_s)
        raise RuntimeError(f"the remote job did not finish within {max_hours} hours")

    def upload_chunked(self, local: Path, prefix: str, chunk_mb: int = 4, retries: int = 3) -> int:
        tmp = Path(tempfile.mkdtemp(prefix="scan3d-up-"))
        try:
            parts = split_file(local, tmp, prefix, chunk_mb * 1024 * 1024)
            started, sent = time.time(), 0
            for i, part in enumerate(parts, 1):
                size = part.stat().st_size
                for attempt in range(1, retries + 1):
                    try:
                        self.upload(part, f"/content/{part.name}")
                        break
                    except RuntimeError:
                        if not self.alive():
                            raise SessionLost(f"Session '{self.session}' disappeared while uploading {part.name}")
                        if attempt == retries:
                            raise
                        log.warning("upload of %s failed (attempt %d), retrying", part.name, attempt)
                sent += size
                part.unlink()
                log.info("uploaded part %d/%d (%.2f MB/s average)", i, len(parts),
                         sent / 1e6 / max(time.time() - started, 1e-6))
                if i % 5 == 0:
                    self.ping()
            return len(parts)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def download_chunked(self, prefix: str, n: int, dest: Path, retries: int = 3) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="scan3d-dl-"))
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as out:
                for i in range(n):
                    name = f"{prefix}{i:03d}"
                    for attempt in range(1, retries + 1):
                        try:
                            self.download(f"/content/{name}", tmp / name)
                            break
                        except RuntimeError:
                            if not self.alive():
                                raise SessionLost(f"Session '{self.session}' disappeared while downloading {name}")
                            if attempt == retries:
                                raise
                            log.warning("download of %s failed (attempt %d), retrying", name, attempt)
                    out.write((tmp / name).read_bytes())
                    (tmp / name).unlink()
                    log.info("downloaded part %d/%d", i + 1, n)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @contextmanager
    def open_session(self, keep: bool = False):
        self.new()
        try:
            yield self
        finally:
            if keep:
                log.warning("Session '%s' left running. Release it with: colab stop -s %s",
                            self.session, self.session)
            elif not self._try_colab("stop", "-s", self.session, timeout=120):
                log.warning("Could not stop session '%s' (it may already be gone). "
                            "Check `colab sessions`.", self.session)

    def run_job(self, job: dict, out_dir: Path, uploads: dict[Path, str] | None = None) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        job_file = out_dir / "job.json"
        job_file.write_text(json.dumps(job, indent=2))
        self.upload(job_file, "/content/job.json")
        for local, remote in (uploads or {}).items():
            self.upload(local, remote)
        self.run_background()
        self.download("/content/result.json", out_dir / "result.json")
        return json.loads((out_dir / "result.json").read_text())