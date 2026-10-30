import json
import os
import shutil
import subprocess
import sys
import time
import traceback

JOB = "/content/job.json"
RESULT = "/content/result.json"


def sh(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def probe(job):
    info = {"python": sys.version.split()[0], "cpu_count": os.cpu_count()}
    for line in open("/proc/meminfo"):
        if line.startswith("MemTotal"):
            info["ram_gb"] = round(int(line.split()[1]) / 1024 / 1024, 1)
            break
    du = shutil.disk_usage("/content")
    info["disk_free_gb"] = round(du.free / 1e9, 1)
    info["os"] = sh("grep PRETTY_NAME /etc/os-release")
    info["gpu"] = sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader")
    info["nvcc"] = sh("nvcc --version | tail -1")
    info["tools"] = {t: shutil.which(t) for t in ["colmap", "ffmpeg", "cmake", "ninja", "git", "blender"]}
    try:
        import torch
        info["torch"] = {"version": torch.__version__, "cuda": torch.cuda.is_available(),
                         "cuda_version": torch.version.cuda}
    except Exception as exc:
        info["torch"] = f"not importable: {exc}"
    return info


ACTIONS = {"probe": probe}


def main():
    if os.path.exists(RESULT):
        os.remove(RESULT)
    job = json.load(open(JOB))
    t0 = time.time()
    try:
        result = {"ok": True, "action": job["action"], "data": ACTIONS[job["action"]](job)}
    except Exception:
        result = {"ok": False, "action": job.get("action"), "error": traceback.format_exc()}
    result["seconds"] = round(time.time() - t0, 2)
    json.dump(result, open(RESULT, "w"), indent=2)
    print(json.dumps(result, indent=2))


main()