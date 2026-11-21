"""가상 사진 파일. 공개 정적 경로 없이 UUID 이름으로만 저장해요."""

from hashlib import sha256
from pathlib import Path
import shutil
from uuid import uuid4

from app.core.config import settings
from app.core.constants import MAX_PHOTO_BYTES
from app.core.errors import ApiError


def inspect(data):
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise ApiError(422, "VALIDATION_FAILED", field="files", problem="사진은 5MB 이하여야 해요.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        kind, extension = "image/png", "png"
    elif data.startswith(b"\xff\xd8\xff"):
        kind, extension = "image/jpeg", "jpg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        kind, extension = "image/webp", "webp"
    else:
        raise ApiError(422, "VALIDATION_FAILED", field="files", problem="jpeg·png·webp만 올려 주세요.")
    return {"media_type": kind, "extension": extension, "size_bytes": len(data), "sha256": sha256(data).hexdigest()}


def save(data, metadata, *, file_id=None, mock=False):
    name = ("mock/" if mock else "") + f"{file_id or uuid4()}.{metadata['extension']}"
    path(name).parent.mkdir(parents=True, exist_ok=True)
    try:
        path(name).write_bytes(data)
    except OSError:
        path(name).unlink(missing_ok=True)
        raise
    return name


def path(name):
    return Path(settings.media_dir) / name


def remove(name):
    path(name).unlink(missing_ok=True)


def reset_mock():
    """메모리를 초기화할 때 mock 파일만 지워요. DB 파일은 건드리지 않아요."""
    root = path("mock")
    if root.exists():
        shutil.rmtree(root)
