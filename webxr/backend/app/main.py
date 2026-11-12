from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .api.auth import router as auth_router
from .api.scans import router as scans_router
from .config import get_settings
from .db import engine
from .rate_limit import redis_client

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    engine.dispose()
    redis_client.close()


app = FastAPI(
    title="Cyclone Scan API",
    version="1.0.0",
    description="Authentication, scan storage, job management, and reconstruction artifact API.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    openapi_url="/openapi.json" if settings.environment != "production" else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["Content-Disposition", "X-Request-ID"],
    max_age=600,
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(f"{settings.api_prefix}/auth/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.environment == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(scans_router, prefix=settings.api_prefix)


@app.get("/health/live", tags=["health"])
def liveness():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def readiness():
    components = {"database": "ok", "redis": "ok", "storage": "ok"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        components["database"] = "unavailable"
    try:
        redis_client.ping()
    except RedisError:
        components["redis"] = "unavailable"
    try:
        if settings.storage_backend == "s3":
            from .services.storage import storage
            storage.s3.head_bucket(Bucket=settings.storage_s3_bucket)
    except Exception:
        components["storage"] = "unavailable"
    if any(value != "ok" for value in components.values()):
        return JSONResponse(status_code=503, content={"status": "not_ready", "components": components})
    return {"status": "ready", "components": components}


@app.exception_handler(HTTPException)
async def safe_http_error(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(_, exc: RequestValidationError):
    # Do not echo submitted values: validation failures may contain passwords or reset tokens.
    errors = [{"loc": error.get("loc", []), "msg": error.get("msg", "Invalid value"),
               "type": error.get("type", "value_error")} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})
