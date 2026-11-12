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
from sqlalchemy import delete, select

from .config import get_settings
from .db import SessionLocal
from .models import AuthToken, Scan, ScanArtifact, ScanAsset, ScanJob, utcnow
from .services.storage import storage

logger = logging.getLogger(__name__)
TRACK_STAGES = {
    "mesh": ["ingest", "validate", "features", "sparse", "undistort", "dense", "mesh", "export", "ar"],
    "splat": ["ingest", "validate", "features", "sparse", "undistort", "splat"],
}
ARTIFACT_SUFFIXES = {".glb", ".gltf", ".obj", ".ply", ".usdz", ".spz"}


def _set_job(job_id: uuid.UUID, **updates) -> None:
    with SessionLocal() as db:
        job = db.get(ScanJob, job_id)
        if not job:
            return
        for key, value in updates.items():
            setattr(job, key, value)
        db.commit()


def _progress_from_manifest(manifest_path: Path, stages: list[str]) -> tuple[int, str | None, dict]:
    if not manifest_path.exists():
        return 0, "starting", {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0, "starting", {}
    records = data.get("stages", {})
    done = sum(records.get(name, {}).get("status") == "done" for name in stages)
    current = next((name for name in stages if records.get(name, {}).get("status") == "running"), None)
    percent = min(99, int(done * 100 / max(len(stages), 1)))
    return percent, current or (stages[done] if done < len(stages) else None), records


def _copy_inputs(job_id: uuid.UUID, job_dir: Path, assets: list[ScanAsset]) -> tuple[Path | None, list[str]]:
    photos_dir = job_dir / "inputs" / "photos"
    videos_dir = job_dir / "inputs" / "videos"
    photo_assets = [item for item in assets if item.content_type.startswith("image/")]
    video_assets = [item for item in assets if item.content_type.startswith("video/")]
    if photo_assets and video_assets:
        raise ValueError("A scan must use photos or one video, not both")
    if video_assets and len(video_assets) != 1:
        raise ValueError("A scan can include only one video")
    for asset in photo_assets:
        name = f"{asset.id.hex}_{Path(asset.original_name).name}"
        storage.download_file(asset.storage_key, photos_dir / name)
    video_paths = []
    for asset in video_assets:
        name = f"{asset.id.hex}_{Path(asset.original_name).name}"
        path = videos_dir / name
        storage.download_file(asset.storage_key, path)
        video_paths.append(str(path.resolve()))
    return (photos_dir.resolve() if photo_assets else None), video_paths


def _create_config(job_dir: Path, scan: Scan, photos_dir: Path | None, videos: list[str]) -> Path:
    settings = get_settings()
    template = settings.pipeline_config_template.resolve()
    if not template.is_file():
        raise FileNotFoundError(f"Pipeline config template was not found: {template}")
    config = yaml.safe_load(template.read_text(encoding="utf-8"))
    config["project"]["name"] = f"scan-{scan.id.hex}"
    config["inputs"]["photos_dir"] = str(photos_dir) if photos_dir else None
    config["inputs"]["videos"] = videos
    out = job_dir / "config.yaml"
    out.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return out


def _upload_artifacts(job: ScanJob, scan: Scan, run_dir: Path) -> list[ScanArtifact]:
    search_roots = [run_dir / "08_export", run_dir / "09_splat", run_dir / "11_ar"]
    files = [path for root in search_roots if root.exists() for path in root.rglob("*")
             if path.is_file() and path.suffix.lower() in ARTIFACT_SUFFIXES]
    if not files:
        raise RuntimeError("The pipeline completed but did not produce a downloadable model artifact")
    artifacts: list[ScanArtifact] = []
    for path in files:
        kind = "model" if path.suffix.lower() in {".glb", ".gltf", ".obj", ".usdz"} else "point_cloud"
        key = f"users/{scan.owner_id}/scans/{scan.id}/artifacts/{job.id}/{path.name}"
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
        )))
        keys = [asset.storage_key for asset in expired]
        for asset in expired:
            db.delete(asset)
        db.commit()
    deleted_objects = 0
    for key in keys:
        try:
            storage.delete(key)
            deleted_objects += 1
        except Exception:
            logger.exception("Could not remove expired upload object")
    return {"expired_sessions": len(keys), "deleted_objects": deleted_objects}


@shared_task(name="app.tasks.purge_old_pipeline_work")
def purge_old_pipeline_work():
    settings = get_settings()
    cutoff = utcnow() - timedelta(days=settings.pipeline_work_retention_days)
    with SessionLocal() as db:
        ids = list(db.scalars(select(ScanJob.id).where(
            ScanJob.status.in_(["succeeded", "failed"]), ScanJob.finished_at < cutoff
        )))
    root = settings.pipeline_work_root.resolve()
    removed = 0
    for job_id in ids:
        path = (root / str(job_id)).resolve()
        if path.is_relative_to(root) and path.exists():
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
        scan = db.get(Scan, job.scan_id)
        if not scan:
            _set_job(job_id, status="failed", error_code="SCAN_NOT_FOUND", error_message="The scan no longer exists", finished_at=utcnow())
            return {"status": "failed"}
        assets = list(db.scalars(select(ScanAsset).where(ScanAsset.scan_id == scan.id, ScanAsset.role == "input", ScanAsset.status == "uploaded")))
        owner_id, scan_id = scan.owner_id, scan.id
        if not assets:
            _set_job(job_id, status="failed", error_code="NO_INPUTS", error_message="No uploaded source files were found", finished_at=utcnow())
            scan.status = "failed"
            db.commit()
            return {"status": "failed"}
        scan_name = scan.name
        scan_type = scan.subject_type
        description = scan.description

    job_dir = settings.pipeline_work_root.resolve() / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    process = None
    try:
        photos_dir, videos = _copy_inputs(job_id, job_dir, assets)
        config_path = _create_config(job_dir, scan, photos_dir, videos)
        (job_dir / "scan-meta.json").write_text(json.dumps({"name": scan_name, "type": scan_type, "description": description}), encoding="utf-8")
        run_dir = job_dir / "runs" / str(job_id)
        manifest_path = run_dir / "manifest.json"
        stages = TRACK_STAGES[settings.pipeline_track]
        log_path = job_dir / "pipeline.log"
        _set_job(job_id, status="running", progress=0, current_stage="ingest", started_at=utcnow())
        with SessionLocal() as db:
            scan_record = db.get(Scan, scan_id)
            if scan_record:
                scan_record.status = "processing"
                db.commit()
        started = time.monotonic()
        with log_path.open("wb") as log_file:
            process = subprocess.Popen(
                ["scan3d", "run", "--config", str(config_path), "--run-id", str(job_id), "--track", settings.pipeline_track],
                cwd=job_dir, stdout=log_file, stderr=subprocess.STDOUT, shell=False, start_new_session=True,
            )
            last_state: tuple[int, str | None] | None = None
            while process.poll() is None:
                if time.monotonic() - started > settings.pipeline_timeout_seconds:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                    raise TimeoutError("The scan exceeded the configured processing time limit")
                progress, current_stage, metrics = _progress_from_manifest(manifest_path, stages)
                state = (progress, current_stage)
                if state != last_state:
                    _set_job(job_id, status="running", progress=progress, current_stage=current_stage, metrics={"stages": metrics})
                    last_state = state
                time.sleep(3)
        if process.returncode != 0:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            logger.error("scan3d failed for job %s: %s", job_id, tail)
            raise RuntimeError("The reconstruction pipeline failed. Review the job details and retry.")

        _, _, stage_metrics = _progress_from_manifest(manifest_path, stages)
        artifacts = _upload_artifacts(job, scan, run_dir)
        with SessionLocal() as db:
            db.add_all(artifacts)
            job_record = db.get(ScanJob, job_id)
            scan_record = db.get(Scan, scan_id)
            if job_record:
                job_record.status = "succeeded"
                job_record.progress = 100
                job_record.current_stage = "complete"
                job_record.metrics = {"stages": stage_metrics, "artifact_count": len(artifacts)}
                job_record.finished_at = utcnow()
            if scan_record:
                scan_record.status = "ready"
            db.commit()
        return {"status": "succeeded", "artifacts": len(artifacts)}
    except Exception as exc:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        logger.exception("Scan job %s failed", job_id)
        with SessionLocal() as db:
            job_record = db.get(ScanJob, job_id)
            scan_record = db.get(Scan, scan_id)
            if job_record:
                job_record.status = "failed"
                job_record.error_code = "PIPELINE_FAILED"
                job_record.error_message = "The scan could not be completed. Contact support with the job ID."
                job_record.finished_at = utcnow()
            if scan_record:
                scan_record.status = "failed"
            db.commit()
        return {"status": "failed"}
