import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBXR_DATABASE_URL", "sqlite://")
    monkeypatch.setenv("WEBXR_ENVIRONMENT", "development")
    monkeypatch.setenv("WEBXR_JWT_SECRET", "test-secret-for-isolated-backend-tests")
    monkeypatch.setenv("WEBXR_STORAGE_BACKEND", "local")
    monkeypatch.setenv("WEBXR_STORAGE_LOCAL_ROOT", str(tmp_path))
    from app import tasks
    from app.config import get_settings
    from app.services.storage import Storage

    get_settings.cache_clear()
    monkeypatch.setattr(tasks, "storage", Storage())
    yield tasks
    get_settings.cache_clear()


def test_interrupted_local_upload_and_retry(backend):
    storage = backend.storage
    with pytest.raises(ValueError):
        with storage.local_upload("inputs/source.jpg") as stream:
            stream.write(b"incomplete")
            raise ValueError("size mismatch")
    assert list((storage.root / "inputs").iterdir()) == []
    with storage.local_upload("inputs/source.jpg") as stream:
        stream.write(b"complete")
    assert storage.head("inputs/source.jpg") == (8, None)


def test_worker_accepts_mp4_alias_and_isolates_remote_sessions(backend, tmp_path, monkeypatch):
    content = bytes(4) + b"ftypisom"
    asset = SimpleNamespace(id=uuid.uuid4(), original_name="clip.mp4", content_type="application/mp4",
                            size_bytes=len(content), storage_key="inputs/source.mp4")
    with backend.storage.local_upload(asset.storage_key) as stream:
        stream.write(content)
    template = Path(__file__).resolve().parents[3] / "configs/house.yaml"
    monkeypatch.setattr(backend.get_settings(), "pipeline_config_template", template)
    scan = SimpleNamespace(id=uuid.uuid4())
    sessions = set()
    for _ in range(2):
        job_dir = tmp_path / str(uuid.uuid4())
        photos, videos = backend._copy_inputs(job_dir, [asset])
        assert photos is None and Path(videos[0]).read_bytes() == content
        config = yaml.safe_load(backend._create_config(job_dir, scan, photos, videos).read_text())
        sessions.add(config["remote"]["session"])
    assert len(sessions) == 2
    asset.size_bytes += 1
    with pytest.raises(ValueError, match="no longer matches"):
        backend._copy_inputs(job_dir, [asset])


def test_s3_upload_signature_binds_size_type_and_create_only_header(backend, monkeypatch):
    from app.services.storage import Storage

    settings = backend.get_settings()
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "storage_s3_bucket", "test-uploads")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    url = Storage().presign_put("inputs/file", "image/jpeg", 128)
    headers = parse_qs(urlsplit(url).query)["X-Amz-SignedHeaders"][0].split(";")
    assert {"content-type", "content-length", "if-none-match"} <= set(headers)


def test_private_local_upload_job_lifecycle(backend, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import rate_limit
    from app.api import scans
    from app.db import Base, get_db
    from app.main import app
    from app.models import User, utcnow
    from app.security import create_access_token

    engine = create_engine("sqlite:///" + str(tmp_path / "api.db"))
    sessions = sessionmaker(engine)
    Base.metadata.create_all(engine)
    with sessions.begin() as db:
        owner = User(email="owner@example.org", password_hash="unused", email_verified_at=utcnow())
        guest = User(email="guest@example.org", password_hash="unused", email_verified_at=utcnow())
        db.add_all([owner, guest])
        db.flush()
        owner_headers = {"Authorization": f"Bearer {create_access_token(owner.id)[0]}"}
        guest_headers = {"Authorization": f"Bearer {create_access_token(guest.id)[0]}"}

    def database():
        with sessions() as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, database)
    monkeypatch.setattr(scans, "storage", backend.storage)
    monkeypatch.setattr(rate_limit, "_increment", lambda **kwargs: (1, 60))
    queued = []
    monkeypatch.setattr(scans.celery_app, "send_task", lambda *args, **kwargs: queued.append(kwargs))
    prefix = "/api/v1"
    with TestClient(app, headers=owner_headers) as client:
        created = client.post(f"{prefix}/scans", json={"name": "Test scan"})
        assert created.status_code == 201
        scan_url = f"{prefix}/scans/{created.json()['id']}"
        payload = {"filename": "clip.mp4", "content_type": "application/mp4", "size_bytes": 12}
        reservation = client.post(scan_url + "/uploads", json=payload)
        assert reservation.status_code == 201
        target = reservation.json()
        assert client.post(scan_url + "/uploads", json=payload).status_code == 422
        assert client.put(target["upload_url"], headers=target["headers"], content=b"wrong").status_code == 422
        data = bytes(4) + b"ftypisom"
        assert client.put(target["upload_url"], headers=target["headers"], content=data).status_code == 204
        assert client.post(scan_url + "/uploads/" + target["asset_id"] + "/complete").status_code == 200
        source_url = f"{prefix}/assets/{target['asset_id']}/download"
        assert client.get(source_url).content == data
        assert client.get(source_url, headers=guest_headers).status_code == 404
        started = client.post(scan_url + "/jobs")
        assert started.status_code == 202 and len(queued) == 1
        assert client.post(scan_url + "/jobs").status_code == 409
        assert client.get(scan_url).json()["status"] == "queued"
    engine.dispose()
