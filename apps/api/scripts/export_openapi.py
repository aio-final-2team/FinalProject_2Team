"""API가 쓰는 스키마를 계약 파일로 저장한다."""

from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app


def export():
    target = Path(__file__).resolve().parents[3] / "contracts/openapi.yaml"
    target.write_text(yaml.safe_dump(app.openapi(), allow_unicode=True, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    export()
