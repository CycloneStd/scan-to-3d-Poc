import json
import logging
import mimetypes
import os
import shutil
import signal
import subprocess
import time
import uuid
from datetime import timedelta
from pathlib import Path

import yaml
from celery import shared_task
from sqlalchemy import delete, select, update

from .config import get_settings
from .db import SessionLocal
from .models import AuthToken, Scan, ScanArtifact, ScanAsset, ScanJob, utcnow
from .services.storage import storage
from .services.uploads import validate_magic

logger = logging.getLogger(__name__)
TRACK_STAGES = {
    "mesh": ["ingest", "validate", "features", "sparse", "undistort", "dense", "mesh", "export", "ar"],
    "splat": ["ingest", "validate", "features", "sparse", "undistort", "splat"],
}
ARTIFACT_SUFFIXES = {".glb", ".gltf", ".obj", ".zip", ".ply", ".usdz", ".spz", ".png", ".jpg", ".webp"}


def _job_cancelled_or_deleted(job_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        active = db.scalar(select(ScanJob.id).join(Scan).where(
            ScanJob.id == job_id, ScanJob.status == "running", Scan.status != "deleting"
        ))
        return active is None


def _terminate_pipeline(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    except ProcessLookupError:
        pass


def _cancel_remote_job(job_id: uuid.UUID, config_path: Path) -> None:
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        remote = config.get("remote") or {}
        if remote.get("session") != f"scan3d-{job_id.hex}":
            return
        from scan3d.remote.executor import ColabExecutor

        executor = ColabExecutor(remote["session"], remote.get("gpu"), remote.get("high_mem", False),
                                 remote.get("auth"), fallback_gpus=remote.get("gpu_fallbacks", []))
        executor.release()
        logger.info("Terminated Colab runtime for scan job %s", job_id)
    except Exception:
        logger.exception("Could not stop Colab runtime for scan job %s", job_id)


def _progress_from_manifest(manifest_path: Path, stages: list[str]) -> tuple[int, str | None, dict]:
    if not manifest_path.exists():
        return 0, "starting", {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0, "starting", {}
    records = data.get("stages", {})
    remote = records.get("reconstruction", {})
    if "dense" in stages and "splat" not in stages and remote:
        remote_stages = ("features", "sparse", "undistort", "dense", "mesh")
        current_remote = remote.get("remote_stage")
        if remote.get("status") == "done":
            for stage in remote_stages[:-1]:
                records[stage] = {"status": "done"}
        elif remote.get("status") == "running" and current_remote in remote_stages:
            for stage in remote_stages:
                if stage == current_remote:
                    records[stage] = {"status": "running"}
                    break
                records[stage] = {"status": "done"}
    done = sum(records.get(name, {}).get("status") == "done" for name in stages)
    current = next((name for name in stages if records.get(name, {}).get("status") == "running"), None)
    percent = min(99, int(done * 100 / max(len(stages), 1)))
    return percent, current or (stages[done] if done < len(stages) else None), records


def _copy_inputs(job_dir: Path, assets: list[ScanAsset]) -> tuple[Path | None, list[str]]:
    photos_dir = job_dir / "inputs" / "photos"
    videos_dir = job_dir / "inputs" / "videos"
    photo_assets = [item for item in assets if item.content_type.startswith("image/")]
    video_assets = [item for item in assets if item.content_type.startswith("video/") or item.content_type == "application/mp4"]
    if len(photo_assets) + len(video_assets) != len(assets):
        raise ValueError("Unsupported source media type")
    if photo_assets and video_assets:
        raise ValueError("A scan must use photos or one video, not both")
    if len(video_assets) > 1:
        raise ValueError("A scan can include only one video")
    video_paths = []
    for asset in assets:
        # Keep the working filename within filesystem limits, including for long upload names.
        filename = f"{asset.id.hex}{Path(asset.original_name).suffix.lower()}"
        path = (photos_dir if asset.content_type.startswith("image/") else videos_dir) / filename
        storage.download_file(asset.storage_key, path)
        with path.open("rb") as body:
            if path.stat().st_size != asset.size_bytes or not validate_magic(asset.content_type, body.read(32)):
                raise ValueError("Stored input no longer matches the completed upload")
        if path.parent == videos_dir:
            video_paths.append(str(path.resolve()))
    return (photos_dir.resolve() if photo_assets else None), video_paths


def _create_config(job_dir: Path, scan: Scan, photos_dir: Path | None, videos: list[str]) -> Path:
    settings = get_settings()
    template = settings.pipeline_config_template.resolve()
    if not template.is_file():
        raise FileNotFoundError(f"Pipeline config template was not found: {template}")
    config = yaml.safe_load(template.read_text(encoding="utf-8"))
    config["project"]["name"] = f"scan-{scan.id.hex}"
    config["remote"]["session"] = f"scan3d-{uuid.UUID(job_dir.name).hex}"
    config["inputs"]["photos_dir"] = str(photos_dir) if photos_dir else None
    config["inputs"]["videos"] = videos
    out = job_dir / "config.yaml"
    out.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return out


def _upload_artifacts(job: ScanJob, scan: Scan, run_dir: Path) -> list[ScanArtifact]:
    search_roots = [run_dir / "08_export", run_dir / "09_splat", run_dir / "11_ar"]
    files = [path for root in search_roots if root.exists() for path in root.rglob("*")
             if path.is_file() and path.suffix.lower() in ARTIFACT_SUFFIXES]
    if not any(path.suffix.lower() in {".glb", ".gltf", ".obj", ".ply", ".spz", ".usdz"} for path in files):
        raise RuntimeError("The pipeline completed but did not produce a downloadable model artifact")
    artifacts: list[ScanArtifact] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".webp"}:
            if "view_" in path.name or "thumbnail" in path.name or "preview" in path.name:
                kind = "thumbnail"
            elif "texture" in path.name:
                kind = "texture"
            else:
                kind = "thumbnail"
        elif suffix in {".glb", ".gltf", ".obj", ".zip", ".usdz"}:
            kind = "model"
        else:
            kind = "point_cloud"
        key = f"users/{scan.owner_id}/scans/{scan.id}/artifacts/{job.id}/{path.relative_to(run_dir).as_posix()}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        storage.upload_file(key, path, content_type)
        artifacts.append(ScanArtifact(scan_id=scan.id, job_id=job.id, owner_id=scan.owner_id,
                                      kind=kind, filename=path.name, content_type=content_type,
                                      size_bytes=path.stat().st_size, storage_key=key))
    return artifacts


@shared_task(name="app.tasks.purge_expired_auth_tokens")
def purge_expired_auth_tokens():
    cutoff = utcnow()
    with SessionLocal() as db:
        result = db.execute(delete(AuthToken).where(AuthToken.expires_at < cutoff))
        db.commit()
        return {"deleted": result.rowcount or 0}


@shared_task(name="app.tasks.purge_expired_upload_sessions")
def purge_expired_upload_sessions():
    with SessionLocal() as db:
        expired = list(db.scalars(select(ScanAsset).where(
            ScanAsset.status == "pending", ScanAsset.expires_at < utcnow()
        ).with_for_update(skip_locked=True)))
        deleted_objects = 0
        for asset in expired:
            try:
                storage.delete(asset.storage_key)
            except Exception:
                logger.exception("Could not remove expired upload object")
                continue
            db.delete(asset)
            deleted_objects += 1
        db.commit()
    return {"expired_sessions": len(expired), "deleted_objects": deleted_objects}


@shared_task(name="app.tasks.purge_old_pipeline_work")
def purge_old_pipeline_work():
    settings = get_settings()
    cutoff = utcnow() - timedelta(days=settings.pipeline_work_retention_days)
    with SessionLocal() as db:
        ids = list(db.scalars(select(ScanJob.id).where(
            ScanJob.status.in_(["succeeded", "failed", "cancelled"]), ScanJob.finished_at < cutoff
        )))
    root = settings.pipeline_work_root.resolve()
    removed = 0
    for job_id in ids:
        path = (root / str(job_id)).resolve()
        if path.parent == root and path.exists():
            shutil.rmtree(path)
            removed += 1
    return {"removed_work_directories": removed}


@shared_task(name="app.tasks.run_scan_job", bind=True, max_retries=0, acks_late=True)
def run_scan_job(self, job_id_text: str):
    job_id = uuid.UUID(job_id_text)
    settings = get_settings()
    with SessionLocal() as db:
        job = db.get(ScanJob, job_id)
        if not job:
            return {"status": "missing"}
        scan = db.get(Scan, job.scan_id, with_for_update=True)
        if not scan:
            return {"status": "missing"}
        db.refresh(job)
        if job.status in ("cancelled", "failed", "succeeded") or scan.status in ("deleting", "failed"):
            return {"status": job.status}
        assets = list(db.scalars(select(ScanAsset).where(ScanAsset.scan_id == scan.id, ScanAsset.role == "input", ScanAsset.status == "uploaded")))
        scan_id = scan.id
        if not assets:
            job.status = "failed"
            job.error_code = "NO_INPUTS"
            job.error_message = "No uploaded source files were found"
            job.finished_at = utcnow()
            scan.status = "failed"
            db.commit()
            return {"status": "failed"}
        scan_name = scan.name
        scan_type = scan.subject_type
        description = scan.description
        job.status = "running"
        job.progress = 0
        job.current_stage = "ingest"
        job.started_at = job.started_at or utcnow()
        scan.status = "processing"
        db.commit()

    job_dir = settings.pipeline_work_root.resolve() / str(job_id)
    process = None
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        photos_dir, videos = _copy_inputs(job_dir, assets)
        if _job_cancelled_or_deleted(job_id):
            shutil.rmtree(job_dir, ignore_errors=True)
            return {"status": "cancelled"}
        config_path = _create_config(job_dir, scan, photos_dir, videos)
        (job_dir / "scan-meta.json").write_text(json.dumps({"name": scan_name, "type": scan_type, "description": description}), encoding="utf-8")
        run_dir = job_dir / "runs" / str(job_id)
        manifest_path = run_dir / "manifest.json"
        stages = TRACK_STAGES[settings.pipeline_track]
        log_path = job_dir / "pipeline.log"
        started = time.monotonic()
        logger.info("[job %s] Starting pipeline for scan %s (%s) with %d input asset(s)",
                    str(job_id)[:8], scan_id, scan_name, len(assets))
        with log_path.open("wb") as log_file:
            process = subprocess.Popen(
                ["scan3d", "run", "--config", str(config_path), "--run-id", str(job_id), "--track", settings.pipeline_track],
                cwd=job_dir, stdout=log_file, stderr=subprocess.STDOUT, shell=False, start_new_session=True,
            )
            last_state: tuple[int, str | None] | None = None
            log_pos = 0
            while process.poll() is None:
                if _job_cancelled_or_deleted(job_id):
                    _terminate_pipeline(process)
                    _cancel_remote_job(job_id, config_path)
                    shutil.rmtree(job_dir, ignore_errors=True)
                    return {"status": "cancelled"}
                if time.monotonic() - started > settings.pipeline_timeout_seconds:
                    _terminate_pipeline(process)
                    _cancel_remote_job(job_id, config_path)
                    raise TimeoutError("The scan exceeded the configured processing time limit")

                # Stream key milestone lines from pipeline.log to Celery worker stdout
                if log_path.exists():
                    try:
                        with log_path.open("r", encoding="utf-8", errors="replace") as reader:
                            reader.seek(log_pos)
                            chunk = reader.read(256 * 1024)
                            log_pos = reader.tell()
                            for line in chunk.splitlines():
                                line_str = line.strip()
                                if not line_str:
                                    continue
                                if any(kw in line_str for kw in ("scan3d.pipeline: [", "opened Colab session", "job completed on Colab", "colab_seconds", "Stopping session", "fused_points", "ERROR", "failed")):
                                    if not any(noise in line_str for noise in ("downloaded part", "uploading part", "part 0")):
                                        logger.info("[job %s] %s", str(job_id)[:8], line_str)
                    except Exception:
                        pass

                progress, current_stage, metrics = _progress_from_manifest(manifest_path, stages)
                state = (progress, current_stage)
                if state != last_state:
                    with SessionLocal() as db:
                        db.execute(update(ScanJob).where(ScanJob.id == job_id, ScanJob.status == "running").values(
                            progress=progress, current_stage=current_stage, metrics={"stages": metrics}))
                        db.commit()
                    logger.info("[job %s] Stage: %s (%d%%)", str(job_id)[:8], current_stage or "starting", progress)
                    last_state = state
                time.sleep(3)
        if process.returncode != 0:
            with log_path.open("rb") as log_file:
                log_file.seek(max(0, log_path.stat().st_size - 4000))
                tail = log_file.read().decode("utf-8", errors="replace")
            logger.error("scan3d failed for job %s: %s", job_id, tail)
            _cancel_remote_job(job_id, config_path)
            raise RuntimeError("The reconstruction pipeline failed. Review the job details and retry.")

        if _job_cancelled_or_deleted(job_id):
            shutil.rmtree(job_dir, ignore_errors=True)
            return {"status": "cancelled"}

        _, _, stage_metrics = _progress_from_manifest(manifest_path, stages)
        artifacts = _upload_artifacts(job, scan, run_dir)
        cancelled = False
        with SessionLocal() as db:
            scan_record = db.get(Scan, scan_id, with_for_update=True)
            job_record = db.get(ScanJob, job_id)
            if (not job_record or job_record.status == "cancelled" or not scan_record
                    or scan_record.status == "deleting"):
                cancelled = True
            else:
                # On retry, remove any previous artifacts from earlier attempts of this scan
                old_artifacts = list(db.scalars(select(ScanArtifact).where(ScanArtifact.scan_id == scan.id)))
                for old in old_artifacts:
                    db.delete(old)

                retired_keys = {old.storage_key for old in old_artifacts} - {item.storage_key for item in artifacts}
                db.flush()
                db.add_all(artifacts)
                job_record.status = "succeeded"
                job_record.progress = 100
                job_record.current_stage = "complete"
                job_record.metrics = {"stages": stage_metrics, "artifact_count": len(artifacts)}
                job_record.finished_at = utcnow()
                scan_record.status = "ready"
                db.commit()
                logger.info("[job %s] Scan %s finished successfully in %.1fs with %d artifacts",
                            str(job_id)[:8], scan_id, time.monotonic() - started, len(artifacts))
        if cancelled:
            for artifact in artifacts:
                try:
                    storage.delete(artifact.storage_key)
                except Exception:
                    logger.exception("Could not remove artifact from cancelled scan %s", scan_id)
            shutil.rmtree(job_dir, ignore_errors=True)
            return {"status": "cancelled"}
        for key in retired_keys:
            try:
                storage.delete(key)
            except Exception:
                logger.exception("Could not remove retired artifact for scan %s", scan_id)
        return {"status": "succeeded", "artifacts": len(artifacts)}
    except Exception:
        if process is not None:
            _terminate_pipeline(process)
        if _job_cancelled_or_deleted(job_id):
            if "config_path" in locals() and config_path.is_file():
                _cancel_remote_job(job_id, config_path)
            shutil.rmtree(job_dir, ignore_errors=True)
            return {"status": "cancelled"}
        logger.exception("Scan job %s failed", job_id)
        with SessionLocal() as db:
            scan_record = db.get(Scan, scan_id, with_for_update=True)
            job_record = db.get(ScanJob, job_id)
            if not scan_record or scan_record.status == "deleting" or not job_record or job_record.status != "running":
                return {"status": "cancelled"}
            job_record.status = "failed"
            job_record.error_code = "PIPELINE_FAILED"
            job_record.error_message = "The scan could not be completed. Contact support with the job ID."
            job_record.finished_at = utcnow()
            scan_record.status = "failed"
            db.commit()
        return {"status": "failed"}
