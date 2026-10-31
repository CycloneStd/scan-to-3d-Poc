from __future__ import annotations 

import json 
import logging 
import subprocess
import tempfile
import shutil
from contextlib import contextmanager
from pathlib import Path 

from .bundle import split_file

log = logging.getLogger("scan3d.remote")
ENTRY = Path(__file__).with_name("colab_entry.py")


class ColabExecutor:
    def __init__(self,session:str,gpu:str|None = "T4", high_mem: bool = True, auth: str| None = None):
        self.session, self.gpu, self.high_mem, self.auth = session, gpu, high_mem, auth

    def _colab(self, *args:str)->None:
        cmd = ["colab"] + (["--auth", self.auth] if self.auth else []) + list(args)
        log.info("$ %s", " ".join(cmd))
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            raise RuntimeError(f"Colab command failed (exit {proc.returncode}): {' '.join(cmd)}")

    def new(self)->None:
        args = ["new", "-s", self.session]
        if self.gpu:
            args += ["--gpu", self.gpu]
        if self.high_mem:
            args += ["--high-mem"]
        self._colab(*args)

    def stop(self)->None:
        self._colab("stop","-s", self.session)
    def upload(self,local:Path, remote:str)->None:
        self._colab("upload","-s",self.session,str(local),remote)
    def download(self,remote:str,local:Path)->None:
        local.parent.mkdir(parents=True,exist_ok=True)
        self._colab("download","-s",self.session,remote,str(local))
    def exec_file(self,script:Path)->None:
        self._colab("exec","-s",self.session,"-f",str(script))

    def upload_chunked(self, local: Path, prefix: str, chunk_mb: int = 4, retries: int = 3) -> int:
        tmp = Path(tempfile.mkdtemp(prefix="scan3d-up-"))
        try:
            parts = split_file(local, tmp, prefix, chunk_mb * 1024 * 1024)
            for i, part in enumerate(parts, 1):
                for attempt in range(1, retries + 1):
                    try:
                        self.upload(part, f"/content/{part.name}")
                        break
                    except RuntimeError:
                        if attempt == retries:
                            raise
                        log.warning("upload of %s failed (attempt %d), retrying", part.name, attempt)
                part.unlink()
                log.info("uploaded part %d/%d", i, len(parts))
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
                            if attempt == retries:
                                raise
                            log.warning("download of %s failed (attempt %d), retrying", name, attempt)
                    out.write((tmp / name).read_bytes())
                    (tmp / name).unlink()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    
    @contextmanager
    def open_session(self,keep:bool= False):
        self.new()
        try:
            yield self
        finally:
            if keep:
                log.warning("Session '%s' left running. Release it with: colab stop -s %s", self.session, self.session)
            else:
                self.stop()

    def run_job(self,job:dict,out_dir:Path,uploads: dict[Path,str] | None = None)-> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        job_file = out_dir / "job.json"
        job_file.write_text(json.dumps(job, indent=2))
        self.upload(job_file, "/content/job.json")
        for local, remote in (uploads or {}).items():
            self.upload(local, remote)
        self.exec_file(ENTRY)
        self.download("/content/result.json", out_dir / "result.json")
        return json.loads((out_dir / "result.json").read_text())