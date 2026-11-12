import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class EmailRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class MessageResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    email_verified: bool
    created_at: datetime


class ScanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subject_type: str = Field(default="Object", pattern="^(Object|Room|Building|Environment)$")
    subject: str | None = Field(default=None, max_length=240)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Scan name is required")
        return value


class ScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    subject_type: str
    subject: str | None
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class UploadInitRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=120)
    size_bytes: int = Field(gt=0)


class UploadInitResponse(BaseModel):
    asset_id: uuid.UUID
    method: str
    upload_url: str
    headers: dict[str, str] = Field(default_factory=dict)
    expires_in: int | None = None


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    created_at: datetime


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    scan_id: uuid.UUID
    status: str
    progress: int
    current_stage: str | None
    error_code: str | None
    error_message: str | None
    metrics: dict
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    download_url: str | None = None


class ScanDetailResponse(ScanResponse):
    assets: list[AssetResponse] = Field(default_factory=list)
    jobs: list[JobResponse] = Field(default_factory=list)
    artifacts: list[ArtifactResponse] = Field(default_factory=list)
