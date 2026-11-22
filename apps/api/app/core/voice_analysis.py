"""두 모드가 공유하는 음성 권한·첫 바이트 검사·결과 정리예요."""

from hashlib import sha256
from io import BytesIO
import logging
import wave

from app.api.schemas.voice_analysis import VoiceAnalysis
from app.core import media
from app.core.config import settings
from app.core.errors import ApiError

MAX_VOICE_BYTES = 10 * 1024 * 1024
VOICE_TIMEOUT = 300


def enabled():
    if not settings.feature_voice_analysis:
        raise ApiError(404, "NOT_FOUND")


def authorize(user, booking, deny, *, write=False):
    if booking is None or booking["org_id"] != user.org_id:
        raise ApiError(404, "NOT_FOUND")
    if not ((user.role == "teacher" and booking["teacher_id"] == user.id)
            or (not write and user.role == "director")):
        deny()
        raise ApiError(403, "FORBIDDEN")
    return booking


def inspect(data):
    if len(data) > MAX_VOICE_BYTES:
        raise ApiError(413, "VALIDATION_FAILED", field="file")
    duration = None
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        try:
            with wave.open(BytesIO(data)) as audio:
                duration = audio.getnframes() / audio.getframerate()
        except (wave.Error, EOFError, ZeroDivisionError):
            raise ApiError(422, "VALIDATION_FAILED", field="file") from None
        kind, extension = "audio/wav", "wav"
    elif data.startswith(b"ID3") or (len(data) > 2 and data[0] == 255 and data[1] & 0xE0 == 0xE0):
        kind, extension = "audio/mpeg", "mp3"
    elif data.startswith(b"\x1aE\xdf\xa3"):
        kind, extension = "audio/webm", "webm"
    elif len(data) >= 12 and data[4:8] == b"ftyp":
        kind, extension = "audio/mp4", "mp4"
    else:
        raise ApiError(422, "VALIDATION_FAILED", field="file", problem="wav·mpeg·webm·mp4만 올려 주세요.")
    return {"media_type": kind, "extension": extension, "size_bytes": len(data),
            "sha256": sha256(data).hexdigest(), "duration_seconds": duration}


def view(row):
    return VoiceAnalysis.model_validate(row).model_dump()


def remove(name):
    if name:
        try:
            media.remove(name)
        except OSError as error:
            logging.getLogger(__name__).warning("가상 음성 파일 삭제 실패 error_type=%s", type(error).__name__)
