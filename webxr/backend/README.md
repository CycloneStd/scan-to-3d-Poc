# WebXR backend

This backend provides account authentication, verification and password reset, scan metadata, private uploads, processing jobs, and model artifact storage. The Vite/React frontend is connected to the auth endpoints; scan and library data remain on their existing frontend implementation.

## Stack

- FastAPI and Pydantic for the JSON API.
- PostgreSQL for users, sessions/tokens, scans, jobs, and artifact metadata.
- Redis and Celery for request throttling and durable long-running jobs.
- Private local filesystem storage for development; S3-compatible storage can be configured for production.
- The existing `scan3d` Python CLI runs in a separate Linux worker. Its current dense reconstruction stage uses the configured Colab adapter.

Passwords use Argon2id. Access tokens are short lived; refresh tokens are random, one-time-rotated values stored only as SHA-256 hashes. Email verification, password reset, refresh, logout, and password change are supported. Authentication and upload routes are rate limited. Each scan and object is checked against the authenticated owner. Uploads are size, type, and file-signature checked; file bytes are never stored in PostgreSQL.

## Local development

Choose one local runtime; both run the same application source and use the same Resend integration.

### Railway-backed frontend (lightweight)

1. Set `VITE_API_BASE_URL` in `webxr/.env.local` to `https://<api-domain>/api/v1`.
2. Ensure the Railway API's `WEBXR_CORS_ORIGINS` includes `http://localhost:5173` and its deployed web origin.
3. From `webxr/`, run `npm ci` once and `npm run dev`.

This uses the selected Railway environment and its data. Use a separate Railway environment if you need isolated development data.

### Optional local Docker stack

1. Copy `webxr/backend/.env.example` to `webxr/backend/.env` and provide a Resend API key and verified sender if you want local signup/reset email delivery.
2. From the repository root, start the frontend, API, PostgreSQL, and Redis:

   ```powershell
   docker compose --env-file webxr/backend/.env -f webxr/backend/docker-compose.yml up --build
   ```

3. Open `http://localhost:5173`. The API uses local PostgreSQL, Redis, and filesystem storage. Migrations run automatically when the API starts.

The optional `processing` profile also builds the large reconstruction worker image. Enable it only when you need local job processing and have configured `COLAB_CONFIG_DIR`:

```powershell
docker compose --env-file webxr/backend/.env -f webxr/backend/docker-compose.yml --profile processing up --build
```

The Docker stack uses the same Dockerfiles, API, frontend, and configuration code as Railway. Only service URLs, storage backend, and secrets differ by environment. Never commit `.env` files.

### Why the earlier worker build failed

The captured build log ends with `Download error (18) Transferred a partial file`. The custom OCI mirror made Micromamba fetch large full repository indexes (about 34 MB and 72 MB in this attempt); the TLS connection closed before the files completed, and Micromamba exhausted its retries. The worker config now uses Conda-forge directly with Zstandard-compressed indexes, and BuildKit caches successfully downloaded packages for retries. The attempted build was interrupted before this corrected dependency-install step completed, so the worker image still needs to be built by Railway or in a later local run.

## Railway deployment

Deploy three services from the repository root, all connected to the same repository and branch:

1. **API:** set the service config file path to `/webxr/backend/railway.api.toml`.
2. **Worker:** set the service config file path to `/webxr/backend/railway.worker.toml`.
3. **Web:** set the service config file path to `/railway.web.toml`.

Add Railway-managed PostgreSQL and Redis. Set shared API/worker variables using Railway's service references (update service names if yours differ):

```text
WEBXR_ENVIRONMENT=production
WEBXR_DATABASE_URL=${{Postgres.DATABASE_URL}}
WEBXR_REDIS_URL=${{Redis.REDIS_URL}}
WEBXR_JWT_SECRET=<unique random secret, at least 32 characters>
WEBXR_FRONTEND_BASE_URL=https://<web-domain>
WEBXR_CORS_ORIGINS=https://<web-domain>,http://localhost:5173
# Railway Free, Trial, and Hobby: use the HTTPS API provider below.
WEBXR_EMAIL_FROM_EMAIL=<verified sender>
WEBXR_EMAIL_FROM_NAME=Cyclone Scan
WEBXR_RESEND_API_KEY=<Resend API key>
WEBXR_STORAGE_BACKEND=s3
WEBXR_STORAGE_S3_BUCKET=<private bucket>
WEBXR_STORAGE_S3_REGION=<region>
WEBXR_STORAGE_S3_ENDPOINT_URL=<private endpoint>
WEBXR_STORAGE_S3_PUBLIC_ENDPOINT_URL=<browser reachable endpoint>
WEBXR_STORAGE_S3_ACCESS_KEY=<least privilege key>
WEBXR_STORAGE_S3_SECRET_KEY=<secret>
WEBXR_PIPELINE_CONFIG_TEMPLATE=/repo/configs/house.yaml
WEBXR_PIPELINE_WORK_ROOT=/tmp/scan3d-pipeline
WEBXR_PIPELINE_TRACK=mesh
```

Create a Resend API key and verify a sending domain in Resend, then use an address on that domain for `WEBXR_EMAIL_FROM_EMAIL`.

Use Railway's actual Postgres/Redis variable references. For S3, provide the same bucket credentials to the API and worker and configure bucket CORS for the web domain so browsers can use signed uploads/downloads. The CORS example includes the local Vite origin so you can develop the frontend locally against Railway. Use a separate Railway environment and data services for development if you want to keep test data separate from production. Set the web service's build variable `VITE_API_BASE_URL=https://<api-domain>/api/v1`. Generate domains for the API and web services; keep the worker private.

The API service runs `alembic upgrade head` as a pre-deploy step and reports readiness at `/health/ready`. The worker executes the existing `scan3d` CLI and uses the Colab GPU adapter. Provide the worker with valid Colab CLI credentials and persistent configuration at `/home/mambauser/.config/colab` (a Railway volume); otherwise the API can accept a job, but dense reconstruction cannot start. The worker's Linux image build is resource intensive. Railway does not share a service's local filesystem with other services, which is why Railway must use S3-compatible storage; local development continues to use private local storage. Review Railway's [Dockerfile setup](https://docs.railway.com/builds/dockerfiles) and [pre-deploy migrations](https://docs.railway.com/deployments/pre-deploy-command) when wiring services.

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

Passwords must be 12–256 characters. Configure the production email provider before using verification or reset. Verification and reset links open the frontend pages, which submit their one-time tokens to the API. Successful provider acceptance and provider message IDs are logged by the API; delivery outcomes are available in the provider dashboard.

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

- Set `WEBXR_ENVIRONMENT=production`, a unique secret, exact frontend CORS origins, and Resend credentials/sender.
- Use a managed PostgreSQL database with backups and TLS.
- Use Railway's managed PostgreSQL and Redis for the application data and queue, and an S3-compatible private bucket for source files and model artifacts. Keep the object bucket private, use least-privilege credentials, configure bucket CORS for the deployed frontend, and apply lifecycle policies to abandoned multipart uploads.
- Set `WEBXR_STORAGE_S3_ENDPOINT_URL` to the private endpoint used by API/workers and `WEBXR_STORAGE_S3_PUBLIC_ENDPOINT_URL` to the browser-reachable endpoint used only for signed upload/download URLs.
- Keep Redis, PostgreSQL, MinIO/S3, and worker ports private. Terminate HTTPS at a trusted reverse proxy.
- Build and deploy API and GPU-capable/Colab-authorized workers as separate services. Do not use development credentials in production.
- Run `alembic upgrade head` as a release step before starting the new API version.

Production credentials, Resend API key, cloud bucket, Colab authorization, and deployment host are supplied through environment/secret management rather than stored in this repository.
