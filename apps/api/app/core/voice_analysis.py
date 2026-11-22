"""두 모드가 공유하는 음성 권한·첫 바이트 검사·결과 정리예요."""

from hashlib import sha256
from io import BytesIO
import logging
import re
import struct
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
    if write and booking["status"] not in {"confirmed", "done"}:
        raise ApiError(409, "CONFLICT")
    return booking


def _mpeg(data):
    if not data.startswith(b"ID3"):
        return len(data) >= 4 and data[0] == 255 and data[1] & 0xE0 == 0xE0
    if (len(data) < 10 or data[3] not in (2, 3, 4) or data[4] == 255
            or data[5] & {2: 0x3F, 3: 0x1F, 4: 0x0F}[data[3]] or any(v & 128 for v in data[6:10])):
        return False
    size = 0
    for value in data[6:10]:
        size = (size << 7) | value
    start = 10 + size + (10 if data[3] == 4 and data[5] & 0x10 else 0)
    return re.search(b"\xff[\xe0-\xff]", data[start:]) is not None


def _ebml_integer(data, offset, *, identifier=False):
    if offset >= len(data) or data[offset] == 0:
        raise ValueError("EBML integer")
    width = 9 - data[offset].bit_length()
    if width > (4 if identifier else 8) or offset + width > len(data):
        raise ValueError("EBML integer")
    value = int.from_bytes(data[offset:offset + width], "big")
    if not identifier:
        value &= (1 << (7 * width)) - 1
        if value == (1 << (7 * width)) - 1:
            raise ValueError("EBML unknown header size")
    return value, offset + width


def _webm(data):
    try:
        size, offset = _ebml_integer(data, 4)
        end, doctypes = offset + size, []
        if end > len(data):
            return False
        while offset < end:
            element, offset = _ebml_integer(data, offset, identifier=True)
            size, offset = _ebml_integer(data, offset)
            if offset + size > end:
                return False
            if element == 0x4282:
                doctypes.append(data[offset:offset + size])
            offset += size
        return doctypes == [b"webm"]
    except ValueError:
        return False


def _mp4(data):
    if len(data) < 16:
        return False
    size = int.from_bytes(data[:4], "big")
    allowed = {b"M4A ", b"M4B ", b"mp42", b"mp41", b"isom", b"iso2", b"dash"}
    return (16 <= size <= len(data) and size % 4 == 0 and data[8:12] in allowed
            and all(data[i:i + 4] in allowed for i in range(16, size, 4)))


def inspect(data):
    if len(data) > MAX_VOICE_BYTES:
        raise ApiError(413, "VALIDATION_FAILED", field="file")
    duration = None
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        try:
            with wave.open(BytesIO(data)) as audio:
                declared = audio.getnframes()
                actual = len(audio.readframes(declared)) // (audio.getnchannels() * audio.getsampwidth())
                duration = min(declared, actual) / audio.getframerate()
        except (wave.Error, EOFError, RuntimeError, struct.error, ValueError, OverflowError, ZeroDivisionError):
            raise ApiError(422, "VALIDATION_FAILED", field="file") from None
        kind, extension = "audio/wav", "wav"
    elif _mpeg(data):
        kind, extension = "audio/mpeg", "mp3"
    elif data.startswith(b"\x1aE\xdf\xa3") and _webm(data):
        kind, extension = "audio/webm", "webm"
    elif data[4:8] == b"ftyp" and _mp4(data):
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
