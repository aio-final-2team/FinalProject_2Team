"""실제 호출 확인: python -m tools.public_apis.check

키는 환경 변수 LAW_GO_KR_OC·DATA_GO_KR_API_KEY에서만 읽고, 화면에는 키를 지운 주소만 찍는다.
결과는 README '실제 호출 기록'에 옮겨 적는다(T15 완료 기준: 요청 조건·응답 시각·결과 건수·상태).
"""

import argparse
import json
import re
import sys

from tools.public_apis.common import PublicApiError, now_kst, urlopen_bytes
from tools.public_apis.law import LawClient
from tools.public_apis.weather import SEOUL_GRID, WeatherClient

SECRET_RE = re.compile(r"(OC|serviceKey)=[^&]*")


class RecordingOpener:
    """실제 호출을 그대로 하고 상태 코드·결과 건수만 적어 둔다."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, timeout):
        status, body = urlopen_bytes(url, timeout)
        count = None
        try:
            data = json.loads(body)
            count = (data.get("LawSearch") or {}).get("totalCnt") or \
                ((data.get("response") or {}).get("body") or {}).get("totalCount")
        except (ValueError, AttributeError):
            pass
        self.calls.append((SECRET_RE.sub(r"\1=***", url), status, count))
        return status, body


def run(name, call, opener):
    print(f"[{now_kst():%Y-%m-%d %H:%M} KST] {name}")
    try:
        data = call()
        state = "받아서 씀"
    except PublicApiError as error:
        data, state = {"error": error.code, "message": error.message}, "안 됨"
    for url, status, count in opener.calls:
        print(f"  GET {url}\n      → HTTP {status}" + (f", 결과 {count}건" if count is not None else ""))
    for key, value in data.items():
        print(f"  {key}: {str(value)[:120]}")
    print(f"  상태: {state}\n")
    return state == "받아서 씀"


def main(argv=None):
    parser = argparse.ArgumentParser(description="공공 API 2개 실제 호출 확인")
    parser.add_argument("--law", default="영유아보육법")
    parser.add_argument("--article", default="제33조")
    parser.add_argument("--nx", type=int, default=SEOUL_GRID[0])
    parser.add_argument("--ny", type=int, default=SEOUL_GRID[1])
    args = parser.parse_args(argv)
    law_opener, weather_opener = RecordingOpener(), RecordingOpener()
    ok = run(f"국가법령정보 {args.law} {args.article}",
             lambda: LawClient(opener=law_opener).get_article(args.law, args.article), law_opener)
    ok &= run(f"기상청 단기예보 nx={args.nx} ny={args.ny}",
              lambda: WeatherClient(opener=weather_opener).get_daily_forecast(args.nx, args.ny), weather_opener)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
