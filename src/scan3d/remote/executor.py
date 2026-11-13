from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

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

STATUS_CODE = """
import json, subprocess


def rj(p):
    try:
        return json.load(open(p))
    except Exception:
        return None


res, job, inp = rj('/content/result.json'), rj('/content/job.json'), rj('/content/inputs.json')
pids = subprocess.run("pgrep -f '[c]olab_entry.py'", shell=True, capture_output=True, text=True).stdout.split()
print('@@STATE@@' + json.dumps({'result_job_id': (res or {}).get('job_id'), 'result_ok': (res or {}).get('ok'),
                                'job_json_id': (job or {}).get('job_id'), 'inputs': inp,
                                'pid': int(pids[0]) if pids else None}))
"""

CLEAN_CODE = """
import glob, os
for pat in ('/content/ws.part*', '/content/*_result.part*', '/content/result.json', '/content/inputs.json',
            '/content/job.json', '/content/job.log'):
    for f in glob.glob(pat):
        try:
            os.remove(f)
        except OSError:
            pass
print('@@CLEAN@@')
"""


class SessionLost(RuntimeError):
    """The Colab VM is not reachable (reclaimed, disconnected, or never became ready)."""


class ColabExecutor:
    """Thin adapter over the `colab` CLI. Fire-and-forget commands, JSON job protocol."""

    def __init__(self, session: str, gpu: str | None = "T4", high_mem: bool = True,
                 auth: str | None = None, fallback_gpus=(), io_timeout: int = 180):
        self.session, self.gpu, self.high_mem, self.auth = session, gpu, high_mem, auth
        self.fallback_gpus = list(fallback_gpus)
        self.io_timeout = io_timeout
        self.active_gpu = None
        self.have_session = False
        self.last_output = ""

    # ---- low-level CLI -------------------------------------------------------------------------
    def _base(self) -> list[str]:
        return ["colab"] + (["--auth", self.auth] if self.auth else [])

    def _try_colab(self, *args: str, timeout: int | None = None) -> bool:
        cmd = self._base() + list(args)
        log.info("$ %s", " ".join(cmd))
        try:
            p = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            self.last_output = f"timed out after {timeout}s"
            log.warning("colab %s timed out after %ss", " ".join(args[:2]), timeout)
            return False
        self.last_output = ((p.stdout or "") + (p.stderr or "")).strip()
        if self.last_output:
            print(self.last_output, flush=True)
        return p.returncode == 0

    def _colab(self, *args: str, timeout: int | None = None) -> None:
        if not self._try_colab(*args, timeout=timeout):
            raise RuntimeError(f"colab {' '.join(args[:2])} failed: {self.last_output[-400:]}")

    def _exec_code(self, code: str, timeout: int = 120) -> str:
        p = subprocess.run(self._base() + ["exec", "-s", self.session], input=code, text=True,
                           capture_output=True, timeout=timeout)
        if p.returncode != 0:
            raise RuntimeError(f"colab exec failed: {(p.stderr or p.stdout)[-300:]}")
        return p.stdout

    # ---- session lifecycle ---------------------------------------------------------------------
    def alive(self) -> bool:
        try:
            return "@@ALIVE@@" in self._exec_code("print('@@ALIVE@@')", timeout=90)
        except (RuntimeError, subprocess.TimeoutExpired):
            return False

    def wait_ready(self, tries: int = 6, wait_s: int = 10) -> None:
        for i in range(tries):
            if self.alive():
                return
            log.info("Runtime not answering yet (%d/%d)...", i + 1, tries)
            time.sleep(wait_s)
        raise SessionLost("The runtime was allocated but never became reachable")

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
                    self.have_session = True
                    log.info("Allocated runtime: gpu=%s high_mem=%s", gpu, hm)
                    return
                if "Enter the authorization code:" in self.last_output:
                    raise RuntimeError(
                        "Colab CLI authentication is interactive and cannot run on a Railway worker. "
                        "Authorize Colab on a trusted computer, export its OAuth token to "
                        "~/.config/colab-cli/token.json, and mount that file into the worker."
                    )
                log.warning("Allocation failed for gpu=%s high_mem=%s", gpu, hm)
            if attempt < retries:
                log.info("Waiting %ds before retrying allocation...", wait_s)
                time.sleep(wait_s)
        raise RuntimeError("Could not allocate a Colab runtime. Check `colab sessions` and `colab usage`.")

    def ensure_session(self, lost_after_s: int = 600) -> None:
        """Reuse a live VM if there is one; otherwise allocate. If we had a VM and it goes quiet,
        wait up to `lost_after_s` for it to come back before replacing it (never discard work early)."""
        if not self.have_session:
            if self.alive():
                self.have_session = True
                return
            self.new()
            self.wait_ready()
            return
        started = time.time()
        while not self.alive():
            if time.time() - started >= lost_after_s:
                log.warning("Runtime unreachable for %ds; replacing it", lost_after_s)
                self._try_colab("stop", "-s", self.session, timeout=120)
                self.new()
                self.wait_ready()
                return
            log.info("Runtime not answering; waiting (%ds elapsed)...", int(time.time() - started))
            time.sleep(30)

    def release(self) -> None:
        for _ in range(3):
            if self._try_colab("stop", "-s", self.session, timeout=120):
                self.have_session = False
                return
            time.sleep(10)
        log.error("Could not stop session '%s'. Stop it yourself with `colab stop -s %s`, or terminate it at "
                  "colab.research.google.com (Runtime > Manage sessions). It may still be billing.",
                  self.session, self.session)

    def cancel_job(self, job_id: str) -> bool:
        """Stop the Colab runtime only when it still owns the requested reconstruction job."""
        state = self.remote_status()
        if state.get("job_json_id") != job_id or not state.get("pid"):
            return False
        if not self._try_colab("stop", "-s", self.session, timeout=120):
            raise RuntimeError(f"could not stop Colab session '{self.session}': {self.last_output[-400:]}")
        self.have_session = False
        return True

    @contextmanager
    def open_session(self, keep: bool = False):
        self.new()
        try:
            self.wait_ready()
            yield self
        finally:
            if keep:
                log.warning("Session '%s' left running. Release it with: colab stop -s %s",
                            self.session, self.session)
            else:
                self.release()

    # ---- file transfer -------------------------------------------------------------------------
    def upload(self, local: Path, remote: str) -> None:
        self._colab("upload", "-s", self.session, str(local), remote, timeout=self.io_timeout)

    def download(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        tmp = local.with_name(local.name + ".tmp")
        tmp.unlink(missing_ok=True)
        self._colab("download", "-s", self.session, remote, str(tmp), timeout=self.io_timeout)
        os.replace(tmp, local)

    def ping(self) -> None:
        self.alive()

    def _upload_sequential(self, local: Path, prefix: str, chunk_mb: int = 2, retries: int = 3) -> int:
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
                    except RuntimeError as exc:
                        if not self.alive():
                            raise SessionLost(f"Session '{self.session}' is not answering while uploading "
                                              f"{part.name}. Last CLI message: {exc}")
                        if attempt == retries:
                            raise
                        log.warning("upload of %s failed (attempt %d), retrying: %s", part.name, attempt, exc)
                        time.sleep(5 * attempt)
                sent += size
                part.unlink()
                log.info("uploaded part %d/%d (%.2f MB/s average)", i, len(parts),
                         sent / 1e6 / max(time.time() - started, 1e-6))
                if i % 5 == 0:
                    self.ping()
            return len(parts)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _upload_once(self, part: Path) -> None:
        cmd = self._base() + ["upload", "-s", self.session, str(part), f"/content/{part.name}"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=self.io_timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"upload of {part.name} timed out")
        if p.returncode != 0:
            raise RuntimeError(f"upload of {part.name} failed: {((p.stdout or '') + (p.stderr or ''))[-200:]}")

    def _upload_parallel(self, local: Path, prefix: str, chunk_mb: int, retries: int, workers: int) -> int:
        tmp = Path(tempfile.mkdtemp(prefix="scan3d-up-"))
        try:
            parts = split_file(local, tmp, prefix, chunk_mb * 1024 * 1024)
            started, sent = time.time(), 0

            def send(part: Path) -> int:
                for attempt in range(1, retries + 1):
                    try:
                        self._upload_once(part)
                        return part.stat().st_size
                    except RuntimeError:
                        if attempt == retries:
                            raise
                        time.sleep(5 * attempt)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(send, part) for part in parts]
                for i, future in enumerate(as_completed(futures), 1):
                    sent += future.result()
                    log.info("uploaded %d/%d parts (%.2f MB/s average, %d workers)", i, len(parts),
                             sent / 1e6 / max(time.time() - started, 1e-6), workers)
            return len(parts)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def upload_chunked(self, local: Path, prefix: str, chunk_mb: int = 2, retries: int = 3,
                       workers: int = 1) -> int:
        if workers <= 1:
            return self._upload_sequential(local, prefix, chunk_mb, retries)
        return self._upload_parallel(local, prefix, chunk_mb, retries, workers)

    def download_chunked(self, prefix: str, n: int, dest: Path, retries: int = 3) -> None:
        """Simple (non-resumable) variant, used by the dense stage."""
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
                        except RuntimeError as exc:
                            if not self.alive():
                                raise SessionLost(f"Session '{self.session}' is not answering while "
                                                  f"downloading {name}. Last CLI message: {exc}")
                            if attempt == retries:
                                raise
                            log.warning("download of %s failed (attempt %d), retrying: %s", name, attempt, exc)
                            time.sleep(5 * attempt)
                    out.write((tmp / name).read_bytes())
                    (tmp / name).unlink()
                    log.info("downloaded part %d/%d", i + 1, n)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def download_parts(self, prefix: str, n: int, parts_dir: Path) -> None:
        """Resumable: parts already on disk are skipped."""
        parts_dir.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            p = parts_dir / f"{prefix}{i:03d}"
            if p.exists() and p.stat().st_size > 0:
                continue
            self.download(f"/content/{prefix}{i:03d}", p)
            log.info("downloaded part %d/%d", i + 1, n)

    # ---- remote state --------------------------------------------------------------------------
    def remote_status(self) -> dict:
        out = self._exec_code(STATUS_CODE)
        return json.loads(out.split("@@STATE@@", 1)[1].strip().splitlines()[0])

    def clean_remote(self) -> None:
        self._exec_code(CLEAN_CODE)

    def mark_inputs(self, digest: str, parts: int) -> None:
        code = (f"import json; json.dump({{'digest': {digest!r}, 'parts': {parts}}}, "
                f"open('/content/inputs.json', 'w')); print('@@OK@@')")
        if "@@OK@@" not in self._exec_code(code):
            raise RuntimeError("could not record the upload state on the VM")

    def put_job(self, job: dict, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        job_file = out_dir / "job.json"
        job_file.write_text(json.dumps(job, indent=2))
        self.upload(job_file, "/content/job.json")

    def fetch_result(self, out_dir: Path) -> dict:
        self.download("/content/result.json", out_dir / "result.json")
        return json.loads((out_dir / "result.json").read_text())

    def run_background(self, poll_s: int = 30, max_hours: float = 8.0, attach_pid: int | None = None,
                       on_output: Callable[[str], None] | None = None) -> None:
        """Launch colab_entry.py detached on the VM (or attach to a running one), then poll until it finishes."""
        if attach_pid is None:
            self.upload(ENTRY, "/content/colab_entry.py")
            m = re.search(r"@@PID@@(\d+)", self._exec_code(LAUNCH_CODE))
            if not m:
                raise RuntimeError("could not launch the remote job")
            pid = int(m.group(1))
        else:
            pid = attach_pid
        offset, failures = 0, 0
        deadline = time.time() + max_hours * 3600
        while time.time() < deadline:
            try:
                out = self._exec_code(POLL_CODE.replace("__PID__", str(pid)).replace("__OFFSET__", str(offset)))
                st = json.loads(out.split("@@STATE@@", 1)[1].strip().splitlines()[0])
                failures = 0
            except (RuntimeError, subprocess.TimeoutExpired, IndexError, ValueError):
                failures += 1
                if failures >= 8 and not self.alive():
                    raise SessionLost(f"Session '{self.session}' stopped answering while the job was running")
                time.sleep(poll_s)
                continue
            if st["chunk"]:
                print(st["chunk"], end="", flush=True)
                if on_output:
                    on_output(st["chunk"])
            offset = st["offset"]
            if st["done"]:
                return
            if not st["alive"]:
                raise RuntimeError("the remote job exited without writing a result; see the log above")
            if len(st["chunk"]) < 6000:
                time.sleep(poll_s)
        raise RuntimeError(f"the remote job did not finish within {max_hours} hours")

    def run_job(self, job: dict, out_dir: Path, uploads: dict[Path, str] | None = None,
                on_output: Callable[[str], None] | None = None) -> dict:
        self.put_job(job, out_dir)
        for local, remote in (uploads or {}).items():
            self.upload(local, remote)
        self.run_background(on_output=on_output)
        return self.fetch_result(out_dir)
