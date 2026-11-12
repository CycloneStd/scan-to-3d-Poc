# WebXR backend

This backend provides account authentication, verification and password reset, scan metadata, private uploads, processing jobs, and model artifact storage. The Vite/React frontend is connected to the auth endpoints; scan and library data remain on their existing frontend implementation.

## Stack

- FastAPI and Pydantic for the JSON API.
- PostgreSQL for users, sessions/tokens, scans, jobs, and artifact metadata.
- Redis and Celery for request throttling and durable long-running jobs.
- Private local filesystem storage for development; S3-compatible storage can be configured for production.
- The existing `scan3d` Python CLI runs in a separate Linux worker. Its current dense reconstruction stage uses the configured Colab adapter.

Passwords use Argon2id. Access tokens are short lived; refresh tokens are random, one-time-rotated values stored only as SHA-256 hashes. Email verification, password reset, refresh, logout, and password change are supported. Authentication and upload routes are rate limited. Each scan and object is checked against the authenticated owner. Uploads are size, type, and file-signature checked; file bytes are never stored in PostgreSQL.

## Local setup with Docker Compose

Run commands from this directory (`webxr/backend`).

1. Copy `.env.example` to `.env`. Generate separate random values for `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, and `WEBXR_JWT_SECRET`. The JWT secret must be at least 32 characters; use URL-safe values for passwords used inside the compose database URL.
2. Set `COLAB_CONFIG_DIR` in `.env` to a private host folder outside this repository (for example, `C:/Users/<you>/.config/colab-docker`). Build the worker, then run `docker compose run --rm --entrypoint micromamba worker run --name base colab sessions` and complete the Google authorization yourself in the interactive terminal. The folder is mounted into the worker so the CLI can store and refresh its credentials. Never commit this folder.
3. Start the API, worker, database, queue, object store, and local mail sink:

   ```sh
   docker compose up --build -d
   ```

4. Apply the initial database schema:

   ```sh
   docker compose exec api alembic upgrade head
   ```

5. Open `http://localhost:8000/docs` for the local API schema and `http://localhost:8025` to view verification/reset emails. Local uploads and generated files are persisted in the `backend-data` Docker volume.

`/health/live` checks the API process. `/health/ready` checks PostgreSQL, Redis, and object storage. The worker image installs the pipeline's Linux dependencies from Conda-forge plus the backend requirements. Set `WEBXR_PIPELINE_TRACK=mesh` or `splat` to choose output type. The default work directory and local object data live in the `backend-data` volume; completed work directories are cleaned after the configured retention period while published artifacts remain in object storage.

## API surface

All API endpoints are under `/api/v1`. Protected endpoints use `Authorization: Bearer <access_token>`; refresh tokens are sent in the JSON body and must be kept out of logs.

### Authentication

- `POST /auth/register` — create an account and email a one-time verification link.
- `POST /auth/verify-email` — body `{ "token": "..." }`, one use, expiring; verifies and signs the user in.
- `POST /auth/resend-verification` — body `{ "email": "..." }`.
- `POST /auth/login` — return short-lived access and rotating refresh tokens.
- `POST /auth/refresh` — body `{ "refresh_token": "..." }`; consumes and rotates it.
- `POST /auth/logout` — revoke the supplied refresh token.
- `GET /auth/me` — current verified account profile.
- `POST /auth/password/forgot` — body `{ "email": "..." }`; always returns a non-enumerating response.
- `POST /auth/password/reset` — body `{ "token": "...", "new_password": "..." }`; one use, expiring, invalidates refresh tokens.
- `POST /auth/password/change` — authenticated body with `current_password` and `new_password`; invalidates refresh tokens.

Passwords must be 12–256 characters. Configure SMTP before using verification or reset outside the local Mailpit setup. Verification and reset links open the frontend pages, which submit their one-time tokens to the API.

### Scans, uploads, jobs, and results

- `POST /scans`, `GET /scans`, `GET /scans/{scan_id}`, `PATCH /scans/{scan_id}`, `DELETE /scans/{scan_id}`.
- `POST /scans/{scan_id}/uploads` initializes an upload and returns a short-lived S3 URL or authenticated local `PUT` URL. After S3 upload, call `POST /scans/{scan_id}/uploads/{asset_id}/complete`.
- `GET /assets/{asset_id}/download` returns an authorized download or short-lived redirect.
- `POST /scans/{scan_id}/jobs` queues a reconstruction after all input files are complete.
- `GET /jobs/{job_id}` reports persisted job state and pipeline stage progress.
- `GET /artifacts/{artifact_id}/download` returns an authorized model download.

Photo scans accept JPEG/PNG; video scans accept one MP4, MOV, M4V, AVI, MKV, or WebM file. Photos and video cannot be mixed in one scan. Upload sessions expire and are cleaned up periodically. File size, number of files per scan, total account storage, active jobs per account, and upload session duration are configurable with `WEBXR_*` environment settings.

The worker launches the existing CLI, reads its stage manifest for progress, and stores produced GLB/GLTF/OBJ/PLY/USDZ/SPZ files as artifacts. Progress is based on completed pipeline stages, so it can remain unchanged during a long stage. Failed jobs return a safe public error; detailed worker output stays in worker logs.

## Configuration and deployment

All settings use the `WEBXR_` prefix; `.env.example` lists the development settings. Never commit `.env`, credentials, Colab auth files, or cloud keys. For production:

- Set `WEBXR_ENVIRONMENT=production`, a unique secret, exact frontend CORS origins, and SMTP with TLS.
- Use a managed PostgreSQL database with backups and TLS.
- Use Railway's managed PostgreSQL and Redis for the application data and queue, and an S3-compatible private bucket for source files and model artifacts. Keep the object bucket private, use least-privilege credentials, configure bucket CORS for the deployed frontend, and apply lifecycle policies to abandoned multipart uploads.
- Set `WEBXR_STORAGE_S3_ENDPOINT_URL` to the private endpoint used by API/workers and `WEBXR_STORAGE_S3_PUBLIC_ENDPOINT_URL` to the browser-reachable endpoint used only for signed upload/download URLs.
- Keep Redis, PostgreSQL, MinIO/S3, and worker ports private. Terminate HTTPS at a trusted reverse proxy.
- Build and deploy API and GPU-capable/Colab-authorized workers as separate services. Do not use the local Mailpit or MinIO credentials in production.
- Run `alembic upgrade head` as a release step before starting the new API version.

Production credentials, SMTP account, cloud bucket, Colab authorization, and deployment host are intentionally supplied through environment/secret management rather than stored in this repository.
