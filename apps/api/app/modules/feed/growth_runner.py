"""가상 사진을 로컬 ffmpeg로 만들고, 중복·늦은 결과는 버려요."""

from hashlib import sha256
import logging
import subprocess
from uuid import UUID

import imageio_ffmpeg

from app import backend
from app.core import growth_video as rules, media
from app.core.auth import CurrentUser


def encode(photos, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    args = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-y", "-loglevel", "error", "-filter_complex_threads", "1"]
    filters = []
    for i, photo in enumerate(photos):
        args += ["-threads", "1", "-loop", "1", "-t", str(rules.SECONDS_PER_PHOTO), "-i",
                 str(media.path(photo["storage_path"]).resolve())]
        filters.append(f"[{i}:v]scale=720:720:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                       "pad=720:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=12,format=yuv420p,setpts=PTS-STARTPTS"
                       f"[v{i}]")
    filters.append("".join(f"[v{i}]" for i in range(len(photos))) + f"concat=n={len(photos)}:v=1:a=0[out]")
    args += ["-filter_complex", ";".join(filters), "-map", "[out]", "-an", "-c:v", "libx264", "-threads", "1",
             "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", "60", str(output)]
    subprocess.run(args, check=True, timeout=rules.ENCODE_TIMEOUT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"duration_seconds": len(photos) * rules.SECONDS_PER_PHOTO, "size_bytes": output.stat().st_size,
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
        photos = rules.source_photos(user, row["photo_ids"])
        result = encode(photos, media.path(row["storage_path"]))
        accepted = backend.growth_videos.finish(video_id, result)
    except Exception as error:
        logging.getLogger(__name__).error("성장 영상 실패 id=%s error_type=%s", video_id, type(error).__name__)
        backend.growth_videos.finish(video_id, None)
    finally:
        if not accepted:
            rules.remove(row["storage_path"])
