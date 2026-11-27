"""T11 가상 원 자료: 커밋된 파일이 생성기 결과와 같아야 한다.

README·문서를 손으로 고치면 다음에 생성기를 돌릴 때 지워진다(#369 리뷰).
고칠 땐 `data/fixtures/make_fixtures.py`를 고치고 `python3 data/fixtures/make_fixtures.py`로 다시 만든다.
"""

from pathlib import Path
import runpy

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "kg-demo-01"
GENERATOR = runpy.run_path(str(FIXTURES.parent / "make_fixtures.py"))


def generated_files() -> dict[str, str]:
    files = {
        "README.md": GENERATOR["index_text"](),
        "consult_timetable/staff_busy_blocks.json": GENERATOR["busy_blocks_text"](),
    }
    files.update({GENERATOR["filename"](d): GENERATOR["render"](d) for d in GENERATOR["DOCS"]})
    return files


@pytest.mark.parametrize("rel, text", sorted(generated_files().items()))
def test_committed_fixture_matches_generator(rel: str, text: str) -> None:
    committed = (FIXTURES / rel).read_text(encoding="utf-8")
    assert committed == text, f"{rel} 파일이 생성기 결과와 달라요. make_fixtures.py를 고친 뒤 다시 만들어 주세요."
