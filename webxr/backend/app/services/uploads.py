from pathlib import PurePosixPath

from fastapi import HTTPException

from ..config import get_settings

IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
VIDEO_TYPES = {
    ".mp4": {"video/mp4", "application/mp4"},
    ".mov": {"video/quicktime", "video/mp4"},
    ".m4v": {"video/x-m4v", "video/mp4"},
    ".avi": {"video/x-msvideo", "video/avi"},
    ".mkv": {"video/x-matroska"},
    ".webm": {"video/webm"},
}


def clean_filename(value: str) -> str:
    name = PurePosixPath(value.replace("\\", "/")).name.strip()
    if not name or name in {".", ".."} or len(name) > 255 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise HTTPException(status_code=422, detail="Invalid filename")
    return name


def validate_upload(filename: str, content_type: str, size_bytes: int) -> tuple[str, str]:
    settings = get_settings()
    name = clean_filename(filename)
    extension = PurePosixPath(name.lower()).suffix
    mime = content_type.split(";", 1)[0].strip().lower()
    if size_bytes <= 0 or size_bytes > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds configured {settings.upload_max_bytes}-byte upload limit")
    if extension in IMAGE_TYPES and mime == IMAGE_TYPES[extension]:
        return name, "photos"
    if extension in VIDEO_TYPES and mime in VIDEO_TYPES[extension]:
        return name, "video"
    raise HTTPException(status_code=415, detail="Supported sources are JPEG/PNG photos or supported video files")


def validate_magic(content_type: str, prefix: bytes) -> bool:
    mime = content_type.split(";", 1)[0].lower()
    if mime == "image/jpeg":
        return prefix.startswith(b"\xff\xd8\xff")
    if mime == "image/png":
        return prefix.startswith(b"\x89PNG\r\n\x1a\n")
    if mime in {"video/mp4", "application/mp4", "video/quicktime", "video/x-m4v"}:
        return len(prefix) >= 8 and prefix[4:8] == b"ftyp"
    if mime in {"video/x-matroska", "video/webm"}:
        return prefix.startswith(b"\x1a\x45\xdf\xa3")
    if mime in {"video/x-msvideo", "video/avi"}:
        return prefix.startswith(b"RIFF") and prefix[8:12] == b"AVI "
    return False
