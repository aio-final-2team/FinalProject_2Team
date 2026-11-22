"""가상 사진을 로컬 ffmpeg로 만들고, 중복·늦은 결과는 버려요."""

from hashlib import sha256
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory
from uuid import UUID

import imageio_ffmpeg

from app import backend
from app.core import growth_video as rules, media
from app.core.auth import CurrentUser

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="growth-video")


async def run_in_api(video_id):
    await asyncio.get_running_loop().run_in_executor(_executor, run_growth_video, video_id)


def ffmpeg(args, timeout):
    wrapper = shutil.which("setpriv")
    command = [wrapper, "--pdeathsig", "KILL", "--"] if wrapper else []
    subprocess.run([*command, imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-y", "-v", "error",
                    "-xerror", "-filter_complex_threads", "1", *args], check=True, timeout=timeout,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def dimensions(data):
    """디코드 전 PNG·JPEG·WebP 머리에서 크기와 움직임을 확인해요."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if data[12:16] != b"IHDR":
            raise ValueError("invalid PNG")
        width, height = struct.unpack(">II", data[16:24])
        pos = 8
        while pos + 12 <= len(data):
            length = int.from_bytes(data[pos:pos+4], "big")
            if data[pos+4:pos+8] == b"acTL":
                raise ValueError("animated PNG")
            pos += 12 + length
        return width, height
    if data.startswith(b"\xff\xd8"):
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 0xff:
                break
            while pos < len(data) and data[pos] == 0xff:
                pos += 1
            marker = data[pos]
            pos += 1
            if marker in (0x01, *range(0xd0, 0xd9)):
                continue
            length = int.from_bytes(data[pos:pos+2], "big")
            if length < 2:
                break
            if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
                height, width = struct.unpack(">HH", data[pos+3:pos+7])
                return width, height
            pos += length
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        pos, size = 12, None
        while pos + 8 <= len(data):
            kind, length = data[pos:pos+4], int.from_bytes(data[pos+4:pos+8], "little")
            chunk = data[pos+8:pos+8+length]
            if kind in (b"ANIM", b"ANMF") or (kind == b"VP8X" and chunk[0] & 2):
                raise ValueError("animated WebP")
            if kind == b"VP8X":
                size = (1+int.from_bytes(chunk[4:7], "little"), 1+int.from_bytes(chunk[7:10], "little"))
            elif kind == b"VP8 " and chunk[3:6] == b"\x9d\x01\x2a":
                size = tuple(n & 0x3fff for n in struct.unpack("<HH", chunk[6:10]))
            elif kind == b"VP8L" and chunk[0] == 0x2f:
                bits = int.from_bytes(chunk[1:5], "little")
                size = (1+(bits & 0x3fff), 1+((bits >> 14) & 0x3fff))
            pos += 8 + length + length % 2
        if size:
            return size
    raise ValueError("unknown image dimensions")


def eligible(source):
    try:
        width, height = dimensions(source.read_bytes())
        return min(width, height) >= 1 and width * height <= 40_000_000
    except (ValueError, IndexError, struct.error, OSError):
        return False


def prepare(source, output):
    if not eligible(source):
        return False
    try:
        scale = "scale=w='max(2,trunc(iw*min(720/iw,720/ih)/2)*2)':" \
                "h='max(2,trunc(ih*min(720/iw,720/ih)/2)*2)'"
        ffmpeg(["-threads", "1", "-max_pixels", "40000000", "-i", str(source.resolve()), "-filter_complex",
                f"[0:v]{scale},format=rgba[fg];color=black:s=720x720:r=1[bg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2:format=auto,format=rgb24[out]",
                "-map", "[out]", "-frames:v", "1", "-threads", "1", str(output)], 10)
        return True
    except (ValueError, IndexError, struct.error, OSError, subprocess.SubprocessError):
        return False


class NotEnoughPhotos(ValueError):
    pass


def encode(photos, output, *, limit=20):
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_root = media.path("tmp")
    temp_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="growth-frames-", dir=temp_root) as folder:
        frames, ids = [], []
        for i, photo in enumerate(photos):
            frame = Path(folder) / f"{i}.png"
            if not prepare(media.path(photo["storage_path"]), frame):
                continue
            frames.append(frame)
            ids.append(photo["id"])
            if len(frames) == limit:
                break
        if len(frames) < 3:
            raise NotEnoughPhotos("not_enough_photos")
        return {**encode_frames(frames, output), "photo_count": len(ids), "photo_ids": ids}


def encode_frames(frames, output):
    args = []
    filters = []
    for i, frame in enumerate(frames):
        args += ["-threads", "1", "-framerate", "1/2", "-loop", "1", "-t", "2", "-i", str(frame)]
        filters.append(f"[{i}:v]setsar=1,fps=12,format=yuv420p,setpts=PTS-STARTPTS[v{i}]")
    filters.append("".join(f"[v{i}]" for i in range(len(frames))) + f"concat=n={len(frames)}:v=1:a=0[out]")
    args += ["-filter_complex", ";".join(filters), "-map", "[out]", "-an", "-c:v", "libx264", "-threads", "1",
             "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", "60", str(output)]
    ffmpeg(args, rules.ENCODE_TIMEOUT)
    return {"duration_seconds": len(frames) * rules.SECONDS_PER_PHOTO, "size_bytes": output.stat().st_size,
            "sha256": sha256(output.read_bytes()).hexdigest()}


def run_growth_video(video_id):
    video_id = UUID(str(video_id))
    row = backend.growth_videos.claim(video_id)
    if row is None:
        return
    accepted = False
    try:
        user = backend.users.get_user(row["requested_by"])
        if user is None or not user.is_active:
            raise ValueError("inactive requester")
        user = CurrentUser(id=user.id, org_id=user.org_id, role=user.role)
        backend.growth_videos.access(user, row["child_id"])
        if len(row["photo_ids"]) != row["photo_count"]:
            raise ValueError("missing source photo")
        rules.source_photos(user, row["photo_ids"])
        photos = sorted(backend.growth_videos.candidates(user, row["child_id"]),
                        key=lambda p: (p["created_at"], p["id"]))
        result = encode(photos, media.path(row["storage_path"]), limit=row["photo_count"])
        accepted = backend.growth_videos.finish(video_id, result)
    except Exception as error:
        logging.getLogger(__name__).error("성장 영상 실패 id=%s error_type=%s", video_id, type(error).__name__)
        backend.growth_videos.finish(video_id, None, failure_reason=(
            "not_enough_photos" if isinstance(error, NotEnoughPhotos) else None))
    finally:
        if not accepted:
            rules.remove(row["storage_path"])
