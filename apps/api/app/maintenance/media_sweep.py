"""MEDIA_DIR에서 살아 있는 사진 행이 없는 파일(고아)을 찾는다. --apply일 때만 지운다."""

import argparse
import os
import time
from pathlib import Path

from sqlalchemy import text

from app.core import media
from app.core.db import transaction


def root():
    return Path(media.settings.media_dir).resolve()


def safe_path(name):
    """DB나 목록에서 온 이름이 MEDIA_DIR 밖을 가리키면 거부한다."""
    base = root()
    target = (base / name).resolve()
    if target == base or not target.is_relative_to(base):
        raise ValueError(f"MEDIA_DIR 밖 경로예요: {name}")
    return target


def live_paths(connection):
    return set(connection.scalars(text("""
        SELECT p.storage_path FROM feed_photos p JOIN feed_posts f ON (f.id,f.org_id)=(p.post_id,p.org_id)
        WHERE f.deleted_at IS NULL
    """)))


def orphans(connection, min_age=600):
    """모의 모드의 mock/ 폴더와 링크는 건너뛴다. 막 올라오는 사진을 피하려고 min_age초 안의 파일도 뺀다."""
    base, live, found = root(), live_paths(connection), []
    newest = time.time() - min_age
    for folder, dirs, files in os.walk(base):
        if Path(folder) == base:
            dirs[:] = [d for d in dirs if d != "mock"]
        for name in files:
            path = Path(folder, name)
            relative = path.relative_to(base).as_posix()
            if path.is_symlink() or relative in live or path.stat().st_mtime > newest:
                continue
            found.append(relative)
    return sorted(found)


def sweep(apply=False, min_age=600):
    with transaction() as connection:
        found = orphans(connection, min_age)
    if apply:
        for name in found:
            safe_path(name).unlink(missing_ok=True)
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description="고아 사진 파일 점검. 기본은 목록만 출력해요.")
    parser.add_argument("--apply", action="store_true", help="찾은 고아 파일을 실제로 지워요")
    parser.add_argument("--min-age", type=int, default=600, help="이 초보다 최근에 생긴 파일은 건너뛰어요")
    args = parser.parse_args(argv)
    found = sweep(args.apply, args.min_age)
    for name in found:
        print(name)
    print(f"고아 파일 {len(found)}개" + (" 지움" if args.apply else " (지우려면 --apply)"))


if __name__ == "__main__":
    main()
