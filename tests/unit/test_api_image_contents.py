"""API 이미지가 실행 때 쓰는 저장소 폴더를 빠뜨리지 않는지 본다(11/23 배포 실패: tools·data/external 누락)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_api_dockerfile_copies_every_repo_folder_the_app_imports_or_reads():
    copied = re.findall(r"^COPY (\S+) ", (ROOT / "apps/api/Dockerfile").read_text(), re.M)
    code = "\n".join(p.read_text(encoding="utf-8") for base in ("apps/api/app", "agents")
                     for p in (ROOT / base).rglob("*.py"))
    imported = set(re.findall(r"^\s*(?:from|import) (tools\.[a-z_]+)", code, re.M))
    needed = {name.replace(".", "/") for name in imported}
    if '"data" / "external"' in code:
        needed.add("data/external")
    missing = sorted(path for path in needed if not any(path == c or path.startswith(c + "/") for c in copied))
    assert not missing, f"apps/api/Dockerfile에 COPY가 없어요: {missing}"
