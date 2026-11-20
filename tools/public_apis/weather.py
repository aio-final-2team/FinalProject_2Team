"""기상청 단기예보 조회서비스(data.go.kr)로 한 격자의 하루 기온·강수를 가져온다.

쓰임: 기획서 FR-27 '기상청 단기예보(행사 문의)', WBS T52. 도구 계약은 아직 없어서
최소 모양만 둔다: 그날 최저·최고 기온, 가장 높은 강수확률, 비·눈이 오는 시각.
"""

import os
import urllib.parse
from datetime import date as date_type, datetime, timedelta

from tools.public_apis.common import fetch_json, not_found, now_kst, upstream

FORECAST_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
NAME = "기상청 단기예보 API"
BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)  # 하루 8번 발표, 발표 10분 뒤부터 조회됨
PTY_NAMES = {"1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}
SEOUL_GRID = (60, 127)  # 서울 중구 격자. 원의 주소가 정해지면 원마다 바꾼다


def base_time_for(target, now):
    """오늘 예보는 05시 발표(하루 전체 최저·최고 포함), 그 밖에는 가장 최근 발표를 쓴다."""
    ready = now - timedelta(minutes=10)
    if target == now.date() and ready.hour >= 5:
        return ready.strftime("%Y%m%d"), "0500"
    hours = [h for h in BASE_HOURS if h <= ready.hour]
    if not hours:
        return (ready - timedelta(days=1)).strftime("%Y%m%d"), "2300"
    return ready.strftime("%Y%m%d"), f"{hours[-1]:02d}00"


def summarize(items, day):
    """같은 날짜 예보 항목을 기온·강수 요약으로 줄인다."""
    rows = [i for i in items if i.get("fcstDate") == day]
    if not rows:
        raise not_found(f"{day} 예보가 없어요")
    by = {}
    for row in rows:
        by.setdefault(row["category"], []).append(row)
    temps = [float(r["fcstValue"]) for r in by.get("TMP", [])]
    pick = lambda cat, fn: float(by[cat][0]["fcstValue"]) if by.get(cat) else (fn(temps) if temps else None)
    pops = [int(r["fcstValue"]) for r in by.get("POP", [])]
    rain = [{"time": r["fcstTime"], "type": PTY_NAMES.get(r["fcstValue"], r["fcstValue"])}
            for r in by.get("PTY", []) if r["fcstValue"] != "0"]
    return {"temp_min": pick("TMN", min), "temp_max": pick("TMX", max),
            "pop_max": max(pops) if pops else None, "precipitation": rain}


class WeatherClient:
    def __init__(self, service_key=None, opener=None):
        self.key = service_key if service_key is not None else os.getenv("DATA_GO_KR_API_KEY", "")
        self.opener = opener

    def get_daily_forecast(self, nx=SEOUL_GRID[0], ny=SEOUL_GRID[1], day=None, now=None):
        now = now or now_kst()
        target = day or now.date()
        if isinstance(target, str):
            target = datetime.strptime(target, "%Y-%m-%d").date()
        if not isinstance(target, date_type):
            raise not_found(f"날짜를 읽지 못했어요: {day}")
        if not self.key:
            raise upstream("DATA_GO_KR_API_KEY가 없어 기상청 API를 부를 수 없어요", False)
        base_date, base_time = base_time_for(target, now)
        params = {"pageNo": "1", "numOfRows": "1000", "dataType": "JSON", "base_date": base_date,
                  "base_time": base_time, "nx": str(nx), "ny": str(ny)}
        key = self.key if "%" in self.key else urllib.parse.quote(self.key, safe="")
        data = fetch_json(f"{FORECAST_URL}?serviceKey={key}&{urllib.parse.urlencode(params)}", NAME, self.opener)
        header = (data.get("response") or {}).get("header") or {}
        code = header.get("resultCode")
        if code == "03":
            raise not_found(f"{NAME}에 이 조건의 자료가 없어요")
        if code != "00":
            raise upstream(f"{NAME} 결과 코드 {code}: {header.get('resultMsg', '')}", code in ("01", "02", "04", "05", "22"))
        items = ((data["response"].get("body") or {}).get("items") or {}).get("item") or []
        return {"date": target.isoformat(), "nx": nx, "ny": ny, "base": f"{base_date} {base_time}",
                **summarize(items, target.strftime("%Y%m%d")),
                "source_url": f"{FORECAST_URL}?{urllib.parse.urlencode(params)}",
                "fetched_at": now_kst().isoformat(timespec="seconds")}
