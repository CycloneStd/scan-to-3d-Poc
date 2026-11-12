import asyncio
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..dependencies import require_verified_user
from ..models import Scan, ScanArtifact, ScanAsset, ScanJob, User, utcnow
from ..rate_limit import rate_limit
from ..schemas import (ArtifactResponse, AssetResponse, JobResponse, ScanCreate, ScanDetailResponse,
                       ScanResponse, UploadInitRequest, UploadInitResponse)
from ..services.storage import storage
from ..services.uploads import validate_magic, validate_upload
from ..worker import celery_app

router = APIRouter(tags=["scans"])


def owned_scan(db: Session, scan_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False) -> Scan:
    statement = select(Scan).where(Scan.id == scan_id, Scan.owner_id == user_id)
    if lock:
        statement = statement.with_for_update()
    scan = db.scalar(statement)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


def _asset_response(asset: ScanAsset) -> AssetResponse:
    return AssetResponse(id=asset.id, filename=asset.original_name, content_type=asset.content_type,
                         size_bytes=asset.size_bytes, status=asset.status, created_at=asset.created_at)


def _job_response(job: ScanJob) -> JobResponse:
    return JobResponse(id=job.id, scan_id=job.scan_id, status=job.status, progress=job.progress,
                       current_stage=job.current_stage, error_code=job.error_code, error_message=job.error_message,
                       metrics=job.metrics or {}, created_at=job.created_at, started_at=job.started_at,
                       finished_at=job.finished_at)


@router.post("/scans", response_model=ScanResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("create-scan", 20))])
def create_scan(payload: ScanCreate, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    scan = Scan(owner_id=user.id, name=payload.name, subject_type=payload.subject_type,
                subject=payload.subject, description=payload.description)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


@router.get("/scans", response_model=list[ScanResponse])
def list_scans(limit: int = 50, offset: int = 0, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="limit must be 1-100 and offset must be non-negative")
    return list(db.scalars(select(Scan).where(Scan.owner_id == user.id).order_by(Scan.updated_at.desc()).limit(limit).offset(offset)))


@router.get("/scans/{scan_id}", response_model=ScanDetailResponse)
def get_scan(scan_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    scan = owned_scan(db, scan_id, user.id)
    assets = list(db.scalars(select(ScanAsset).where(ScanAsset.scan_id == scan.id).order_by(ScanAsset.created_at)))
    jobs = list(db.scalars(select(ScanJob).where(ScanJob.scan_id == scan.id).order_by(ScanJob.created_at.desc())))
    artifacts = list(db.scalars(select(ScanArtifact).where(ScanArtifact.scan_id == scan.id).order_by(ScanArtifact.created_at)))
    return ScanDetailResponse(
        id=scan.id, name=scan.name, subject_type=scan.subject_type, subject=scan.subject,
        description=scan.description, status=scan.status, created_at=scan.created_at, updated_at=scan.updated_at,
        assets=[_asset_response(item) for item in assets], jobs=[_job_response(item) for item in jobs],
        artifacts=[ArtifactResponse(id=item.id, kind=item.kind, filename=item.filename, content_type=item.content_type,
                                    size_bytes=item.size_bytes,
                                    download_url=f"{get_settings().api_prefix}/artifacts/{item.id}/download") for item in artifacts],
    )


@router.patch("/scans/{scan_id}", response_model=ScanResponse)
def rename_scan(scan_id: uuid.UUID, payload: ScanCreate, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    scan = owned_scan(db, scan_id, user.id)
    if scan.status not in {"draft", "failed", "ready"}:
        raise HTTPException(status_code=409, detail="A running scan cannot be edited")
    scan.name = payload.name
    scan.subject_type = payload.subject_type
    scan.subject = payload.subject
    scan.description = payload.description
    scan.updated_at = utcnow()
    db.commit()
    db.refresh(scan)
    return scan


@router.delete("/scans/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scan(scan_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    scan = owned_scan(db, scan_id, user.id, lock=True)
    if scan.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Wait for the queued or running job before deleting this scan")
    assets = list(db.scalars(select(ScanAsset).where(ScanAsset.scan_id == scan.id)))
    artifacts = list(db.scalars(select(ScanArtifact).where(ScanArtifact.scan_id == scan.id)))
    keys = [asset.storage_key for asset in assets] + [artifact.storage_key for artifact in artifacts]
    db.delete(scan)
    db.commit()
    for key in keys:
        try:
            storage.delete(key)
        except Exception:
            # An orphaned object is safe; scheduled bucket lifecycle cleanup can remove it later.
            pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/scans/{scan_id}/uploads", response_model=UploadInitResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("init-upload", 30))])
def initiate_upload(scan_id: uuid.UUID, payload: UploadInitRequest, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    scan = owned_scan(db, scan_id, user.id, lock=True)
    if scan.status not in {"draft", "failed"}:
        raise HTTPException(status_code=409, detail="Files can only be added to a draft or failed scan")
    filename, kind = validate_upload(payload.filename, payload.content_type, payload.size_bytes)
    used_bytes = db.scalar(select(func.coalesce(func.sum(ScanAsset.size_bytes), 0)).where(ScanAsset.owner_id == user.id)) or 0
    used_bytes += db.scalar(select(func.coalesce(func.sum(ScanArtifact.size_bytes), 0)).where(ScanArtifact.owner_id == user.id)) or 0
    if used_bytes + payload.size_bytes > get_settings().user_storage_quota_bytes:
        raise HTTPException(status_code=413, detail="This account has reached its configured storage quota")
    existing = list(db.scalars(select(ScanAsset).where(ScanAsset.scan_id == scan.id, ScanAsset.role == "input")))
    if len(existing) >= get_settings().upload_max_files_per_scan:
        raise HTTPException(status_code=413, detail="The configured maximum number of files for this scan has been reached")
    existing_video = any(asset.content_type.startswith("video/") for asset in existing)
    if (kind == "video" and existing) or (kind == "photos" and existing_video):
        raise HTTPException(status_code=422, detail="Use either multiple photos or one video per scan")
    if kind == "video" and len(existing) > 0:
        raise HTTPException(status_code=422, detail="Only one video can be uploaded per scan")
    asset_id = uuid.uuid4()
    key = f"users/{user.id}/scans/{scan.id}/inputs/{asset_id}/{filename}"
    asset = ScanAsset(id=asset_id, scan_id=scan.id, owner_id=user.id, original_name=filename,
                      content_type=payload.content_type.split(";", 1)[0].lower(), size_bytes=payload.size_bytes,
                      storage_key=key, status="pending",
                      expires_at=utcnow() + timedelta(minutes=get_settings().upload_session_minutes))
    db.add(asset)
    db.commit()
    if get_settings().storage_backend == "s3":
        expires = 900
        url = storage.presign_put(key, asset.content_type, expires)
        return UploadInitResponse(asset_id=asset.id, method="PUT", upload_url=url,
                                  headers={"Content-Type": asset.content_type}, expires_in=expires)
    return UploadInitResponse(asset_id=asset.id, method="PUT",
                              upload_url=f"{get_settings().api_prefix}/uploads/local/{asset.id}",
                              headers={"Content-Type": asset.content_type})


def _get_pending_asset(db: Session, asset_id: uuid.UUID, user_id: uuid.UUID) -> ScanAsset:
    asset = db.scalar(select(ScanAsset).where(ScanAsset.id == asset_id, ScanAsset.owner_id == user_id).with_for_update())
    if not asset:
        raise HTTPException(status_code=404, detail="Upload not found")
    if asset.status != "pending":
        raise HTTPException(status_code=409, detail="Upload is already complete or unavailable")
    if asset.expires_at and asset.expires_at <= utcnow():
        raise HTTPException(status_code=410, detail="Upload session expired. Initialize the upload again.")
    return asset


@router.put("/uploads/local/{asset_id}", status_code=status.HTTP_204_NO_CONTENT,
            dependencies=[Depends(rate_limit("local-upload", 20))])
async def upload_local(asset_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    if get_settings().storage_backend != "local":
        raise HTTPException(status_code=404, detail="Local upload route is disabled")
    asset = _get_pending_asset(db, asset_id, user.id)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type != asset.content_type:
        raise HTTPException(status_code=415, detail="Uploaded content type does not match the initiated upload")
    size = 0
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as body:
        async for chunk in request.stream():
            size += len(chunk)
            if size > get_settings().upload_max_bytes or size > asset.size_bytes:
                raise HTTPException(status_code=413, detail="Uploaded file exceeds its declared or configured size")
            body.write(chunk)
        if size != asset.size_bytes:
            raise HTTPException(status_code=422, detail="Uploaded file size does not match the declared size")
        body.seek(0)
        prefix = body.read(32)
        if not validate_magic(asset.content_type, prefix):
            raise HTTPException(status_code=415, detail="The uploaded file signature does not match its declared media type")
        await asyncio.to_thread(storage.put_fileobj, asset.storage_key, body, asset.content_type)
    asset.status = "uploaded"
    asset.expires_at = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/scans/{scan_id}/uploads/{asset_id}/complete", response_model=AssetResponse,
             dependencies=[Depends(rate_limit("complete-upload", 60))])
def complete_upload(scan_id: uuid.UUID, asset_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    scan = owned_scan(db, scan_id, user.id)
    asset = db.scalar(select(ScanAsset).where(ScanAsset.id == asset_id, ScanAsset.owner_id == user.id).with_for_update())
    if not asset:
        raise HTTPException(status_code=404, detail="Upload not found")
    if asset.scan_id != scan.id:
        raise HTTPException(status_code=404, detail="Upload not found")
    if asset.status == "uploaded":
        return _asset_response(asset)
    if asset.status != "pending":
        raise HTTPException(status_code=409, detail="Upload is unavailable")
    if asset.expires_at and asset.expires_at <= utcnow():
        db.delete(asset)
        db.commit()
        try:
            storage.delete(asset.storage_key)
        except Exception:
            pass
        raise HTTPException(status_code=410, detail="Upload session expired. Initialize the upload again.")
    try:
        size, content_type = storage.head(asset.storage_key)
        prefix = storage.read_prefix(asset.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Uploaded object is not available in storage") from exc
    if size != asset.size_bytes or size > get_settings().upload_max_bytes:
        raise HTTPException(status_code=422, detail="Stored object size does not match the initiated upload")
    if content_type and content_type.split(";", 1)[0].lower() != asset.content_type:
        raise HTTPException(status_code=415, detail="Stored object content type does not match the initiated upload")
    if not validate_magic(asset.content_type, prefix):
        storage.delete(asset.storage_key)
        raise HTTPException(status_code=415, detail="The uploaded file signature does not match its declared media type")
    asset.status = "uploaded"
    asset.expires_at = None
    db.commit()
    db.refresh(asset)
    return _asset_response(asset)


@router.delete("/scans/{scan_id}/uploads/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(scan_id: uuid.UUID, asset_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    scan = owned_scan(db, scan_id, user.id)
    if scan.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Source files cannot be changed while a scan job is queued or running")
    asset = db.scalar(select(ScanAsset).where(ScanAsset.id == asset_id, ScanAsset.scan_id == scan.id,
                                        ScanAsset.owner_id == user.id, ScanAsset.role == "input").with_for_update())
    if not asset:
        raise HTTPException(status_code=404, detail="Upload not found")
    db.delete(asset)
    db.commit()
    try:
        storage.delete(asset.storage_key)
    except Exception:
        pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/scans/{scan_id}/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(rate_limit("start-scan", 5))])
def start_job(scan_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    scan = owned_scan(db, scan_id, user.id, lock=True)
    assets = list(db.scalars(select(ScanAsset).where(ScanAsset.scan_id == scan.id, ScanAsset.role == "input")))
    if not assets or any(asset.status != "uploaded" for asset in assets):
        raise HTTPException(status_code=409, detail="Upload and complete all source files before starting a scan")
    active = db.scalar(select(ScanJob.id).where(ScanJob.scan_id == scan.id, ScanJob.status.in_(["queued", "running"])))
    if active:
        raise HTTPException(status_code=409, detail="A scan job is already queued or running")
    user_active_jobs = db.scalar(select(func.count(ScanJob.id)).where(
        ScanJob.owner_id == user.id, ScanJob.status.in_(["queued", "running"])
    )) or 0
    if user_active_jobs >= get_settings().max_active_jobs_per_user:
        raise HTTPException(status_code=429, detail="Too many scans are already queued for this account")
    job = ScanJob(scan_id=scan.id, owner_id=user.id, status="queued", progress=0)
    scan.status = "queued"
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        task = celery_app.send_task("app.tasks.run_scan_job", args=[str(job.id)])
        job.celery_task_id = task.id
        db.commit()
    except Exception as exc:
        job.status = "failed"
        job.error_code = "QUEUE_UNAVAILABLE"
        job.error_message = "The processing queue is unavailable. Try again later."
        job.finished_at = utcnow()
        scan.status = "failed"
        db.commit()
        raise HTTPException(status_code=503, detail="The processing queue is unavailable") from exc
    db.refresh(job)
    return _job_response(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    job = db.scalar(select(ScanJob).where(ScanJob.id == job_id, ScanJob.owner_id == user.id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(job)


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    artifact = db.scalar(select(ScanArtifact).where(ScanArtifact.id == artifact_id, ScanArtifact.owner_id == user.id))
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if get_settings().storage_backend == "s3":
        return RedirectResponse(storage.presign_get(artifact.storage_key, artifact.filename,
                                                     get_settings().artifact_download_ttl_seconds), status_code=307)
    path = storage._local_path(artifact.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact is missing from storage")
    return FileResponse(path, media_type=artifact.content_type, filename=artifact.filename)


@router.get("/assets/{asset_id}/download")
def download_source_asset(asset_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_verified_user)):
    asset = db.scalar(select(ScanAsset).where(ScanAsset.id == asset_id, ScanAsset.owner_id == user.id,
                               ScanAsset.status == "uploaded"))
    if not asset:
        raise HTTPException(status_code=404, detail="Source file not found")
    if get_settings().storage_backend == "s3":
        return RedirectResponse(storage.presign_get(asset.storage_key, asset.original_name,
                                                     get_settings().artifact_download_ttl_seconds), status_code=307)
    path = storage._local_path(asset.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Source file is missing from storage")
    return FileResponse(path, media_type=asset.content_type, filename=asset.original_name)
