"""공공 API에서 가져온 법령·예보를 자료로 저장하고 답변 근거로 돌려준다(T52, FR-27)."""

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from agents.graphs.answer import gather_on
from app.core.db import transaction
from app.core.schedule import KST
from tools.public_apis.law import get_law_article
from tools.public_apis.weather import WeatherClient

# 저장소에서는 apps/api/app/… 다섯 단계 위, 이미지에서는 /app 아래에 data/external이 있다. 위로 올라가며 찾는다.
TOPICS_FILE = next((parent / "data" / "external" / "law_topics.json" for parent in Path(__file__).resolve().parents
                    if (parent / "data" / "external" / "law_topics.json").is_file()),
                   Path("data") / "external" / "law_topics.json")
QUOTE_LENGTH = 200
EVENT_WORDS = ("날씨", "우산", "추워", "더워", "소풍", "현장체험", "체험", "행사", "운동회", "나들이")
# '비'·'눈'은 준비물·비용처럼 다른 낱말 속 글자와 섞이지 않게, 앞에 한글이 없고 뒤가 조사·끝일 때만 센다
RAIN_SNOW = re.compile(r"(?<![가-힣])[비눈](?![가-힣])|(?<![가-힣])[비눈](?=[이가은는도와올오])")
RELATIVE_DAYS = {"오늘": 0, "내일": 1, "모레": 2}
MONTH_DAY = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일|(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)")
FORECAST_DAYS = 3
SAFETY_LAW = "child_safety"  # 아동 안전으로 분류된 민원은 AI가 안 불러도 이 조문을 붙이는 선


def law_topics():
    return json.loads(TOPICS_FILE.read_text(encoding="utf-8"))


def infection_words(when):
    """요청에 이 낱말이 있어야 감염병 조문을 붙인다. 감염병 15종 파일의 이름(등교 중지 안 하는 감기군 제외)을 재사용한다."""
    names = json.loads((TOPICS_FILE.parent / when["disease_names_file"]).read_text(encoding="utf-8"))["diseases"]
    return list(when["words"]) + [item["name"] for item in names if item["name"] != "감기군"]


def law_rule_key(topic_key, risk_category, body):
    """법령 조문을 붙일 조건에 맞는 규칙 이름. 주제가 넓어 주제만으로는 붙이지 않고, 없으면 None.
    낱말 조건(when)은 대역이에요: 고정 검색·모델 없음·실패 때만 써요. 자료 찾는 AI는 law_article 도구로 스스로 불러요."""
    for key, rule in law_topics().items():
        when = rule["when"]
        if risk_category in when.get("risk_categories", ()) or (
                topic_key in when.get("topic_keys", ()) and any(word in body for word in infection_words(when))):
            return key
    return None


def store_public(connection, org_id, doc_type, title, source_url, fetched_at, location, text_body,
                 effective_to=None):
    """공공 자료 한 건을 documents와 조각 1개로 저장하고 chunk_id를 돌려준다. 같은 내용이면 같은 조각이다."""
    digest = hashlib.sha256((title + text_body).encode("utf-8")).hexdigest()
    params = {"org": org_id, "type": doc_type, "title": title, "url": source_url, "at": fetched_at,
              "today": datetime.now(KST).date(), "to": effective_to, "sha": digest}
    connection.execute(text("""
        INSERT INTO documents (org_id,title,doc_type,visibility,source,source_url,api_called_at,effective_from,
                               effective_to,status,ingest_status,content_sha256,is_virtual)
        VALUES (:org,:title,:type,'all','public_api',:url,CAST(:at AS timestamptz),:today,:to,'active','succeeded',
                :sha,false)
        ON CONFLICT (org_id, content_sha256) DO NOTHING
    """), params)
    document = connection.scalar(text("SELECT id FROM documents WHERE org_id=:org AND content_sha256=:sha"), params)
    connection.execute(text("""
        INSERT INTO document_chunks (document_id,org_id,chunk_index,location,content)
        VALUES (:doc,:org,0,:location,:content) ON CONFLICT (document_id, chunk_index) DO NOTHING
    """), {"doc": document, "org": org_id, "location": location, "content": text_body})
    return connection.scalar(text("SELECT id FROM document_chunks WHERE document_id=:doc AND chunk_index=0"),
                             {"doc": document})


def fetch_law(topic_key, client=None):
    """법령표에 있는 규칙(topic_key)의 법령 조문을 가져온다. DB를 쓰지 않으니 트랜잭션 밖에서 불러야 한다.
    표에 없으면 None, 못 가져오면 {"unchecked": True}."""
    topic = law_topics().get(topic_key)
    if topic is None:
        return None
    result = get_law_article(topic["law_name"], topic["article"], client=client)
    if not result["ok"]:
        return {"unchecked": True}
    return {"topic": topic, "data": result["data"]}


def law_evidence(connection, org_id, topic_key, client=None, fetched=None):
    """법령 조문을 저장한다. fetched(fetch_law 결과)가 있으면 다시 부르지 않는다."""
    if fetched is None:
        fetched = fetch_law(topic_key, client)
    if fetched is None or fetched.get("unchecked"):
        return fetched
    topic, data = fetched["topic"], fetched["data"]
    chunk_id = store_public(connection, org_id, "law", f"{topic['law_name']} {topic['article']}",
                            data["source_url"], data["fetched_at"], topic["article"], data["text"])
    return {"chunk_id": chunk_id, "quote": data["text"][:QUOTE_LENGTH], "score": 1.0}


def number(value):
    return str(int(value)) if float(value) == int(value) else str(value)


def forecast_line(day, forecast):
    parts = []
    if forecast.get("temp_min") is not None and forecast.get("temp_max") is not None:
        parts.append(f"최저 {number(forecast['temp_min'])}도·최고 {number(forecast['temp_max'])}도")
    if forecast.get("pop_max") is not None:
        parts.append(f"강수확률 최대 {forecast['pop_max']}%")
    rain = [f"{item['type']} {int(item['time'][:2])}시" for item in forecast.get("precipitation") or []]
    parts.append(", ".join(rain) if rain else "비·눈 예보 없음")
    return f"{day.month}월 {day.day}일 예보: " + ", ".join(parts)


def fetch_forecast(day, client=None):
    """그날 예보를 가져온다. DB를 쓰지 않으니 트랜잭션 밖에서 불러야 한다. 못 가져오면 None."""
    try:
        return (client or WeatherClient()).get_daily_forecast(day=day)
    except Exception:  # 예보 실패가 문의 답변을 막지 않는다
        return None


def forecast_evidence(connection, org_id, day, client=None, forecast=None):
    """그날 예보를 저장한다. forecast(fetch_forecast 결과)가 있으면 다시 부르지 않는다. 못 하면 None."""
    try:
        forecast = forecast or fetch_forecast(day, client)
        if not forecast:
            return None
        line = forecast_line(day, forecast)
        title = f"기상청 단기예보 {day}"
        chunk_id = store_public(connection, org_id, "public_data", title, forecast["source_url"],
                                forecast["fetched_at"], str(day), line, effective_to=day)
    except Exception:
        return None
    return {"chunk_id": chunk_id, "quote": line[:QUOTE_LENGTH], "score": 1.0,
            "document_title": title, "location": str(day), "content": line, "effective_from": None}


def stored_forecast(org_id, day):
    """그날 예보를 가져와 공공 자료 조각으로 저장한다. 외부 API는 트랜잭션 밖에서 부르고 저장만 자기 트랜잭션에서 한다.
    못 하면 None."""
    fetched = fetch_forecast(day)
    if not fetched:
        return None
    try:
        with transaction() as connection:
            return forecast_evidence(connection, org_id, day, forecast=fetched)
    except Exception:  # 예보 저장 실패가 답변을 막지 않는다
        return None


def question_forecast(org_id, question, today):
    """고정 검색 대역: 질문 낱말·날짜(event_day)가 가리키는 날의 예보. 자료 찾는 AI는 forecast 도구로 부른다."""
    day = event_day(question, today)
    return stored_forecast(org_id, day) if day else None


def stored_law(org_id, key):
    """법령표 키의 조문을 가져와 저장하고 근거 조각으로 돌려준다(외부 API는 트랜잭션 밖). 못 가져오면 None."""
    try:
        fetched = fetch_law(key)
        if not fetched or fetched.get("unchecked"):
            return None
        with transaction() as connection:
            item = law_evidence(connection, org_id, key, fetched=fetched)
    except Exception:  # 법령 실패는 카드에 law_unchecked로만 남긴다
        return None
    topic = fetched["topic"]
    return {"chunk_id": item["chunk_id"], "document_title": f"{topic['law_name']} {topic['article']}",
            "location": topic["article"], "content": fetched["data"]["text"], "score": 1.0, "effective_from": None}


def prefetch_public(request_type, body, topic_key, today, with_forecast=True, risk_category=None):
    """공공 API 호출(법령은 검색→조문 두 번이라 최악 약 20초)을 DB 트랜잭션·연결을 잡기 전에 끝내 둔다. 결과는 처리 안에서 저장만 한다.
    예보는 고정 검색 경로(ANSWER_GATHER=fixed)에서만 미리 가져온다. 자료 찾는 AI 경로는 AI가 forecast 도구로 부르고,
    AI가 못 모아 고정 검색으로 돌아갈 때만 question_forecast로 가져온다(documents/answer.py)."""
    found = {}
    rule_key = law_rule_key(topic_key, risk_category, body) if request_type == "complaint" else None
    if rule_key:
        try:
            found["law"] = (rule_key, fetch_law(rule_key))
        except Exception:
            found["law"] = (rule_key, {"unchecked": True})
    if request_type == "inquiry" and with_forecast and not gather_on():
        day = event_day(body, today)
        if day:
            found["forecast"] = (day, fetch_forecast(day))
    return found


def event_day(question, today):
    """날씨·행사 문의가 오늘~3일 뒤 날짜를 말하면 그 날짜, 아니면 None."""
    if not (any(word in question for word in EVENT_WORDS) or RAIN_SNOW.search(question)):
        return None
    found = [today + timedelta(days=days) for word, days in RELATIVE_DAYS.items() if word in question]
    for match in MONTH_DAY.finditer(question):
        month, day = (int(value) for value in (match.group(1) or match.group(3), match.group(2) or match.group(4)))
        for year in (today.year, today.year + 1):
            try:
                found.append(date(year, month, day))
            except ValueError:
                pass
    for candidate in sorted(found):
        if 0 <= (candidate - today).days <= FORECAST_DAYS:
            return candidate
    return None


def attach_law_evidence(connection, card, req, prefetched=None, answer=None):
    """민원 답변 카드에 법령 근거를 붙인다. 실패해도 카드 처리는 계속한다.
    자료 찾는 AI가 모은 근거로 쓴 초안(answer["gathered"])이면 AI가 law_article로 받아 인용한 조문만 save_evidence로
    근거에 들어가고, 여기서는 아동 안전 선만 지킨다(AI가 안 불러도 아동복지법 조문을 붙임, 원장 보고와 같은 급).
    그 밖(모델 없음·고정 검색·실패)에는 law_rule_key 낱말 조건이 대역이다."""
    gathered = bool(answer and answer.get("gathered"))
    item = {"unchecked": True} if gathered and answer.get("law_unchecked") else None
    try:
        with connection.begin_nested():  # 저장 오류가 바깥 트랜잭션을 망치지 않게 한다
            if gathered:
                rule_key = SAFETY_LAW if req.get("risk_category") == SAFETY_LAW else None
            else:
                rule_key = law_rule_key(req.get("topic_key"), req.get("risk_category"), req["body"])
            if rule_key is not None:
                prefetched_key, fetched = (prefetched or {}).get("law", (None, None))
                found = law_evidence(connection, req["org_id"], rule_key,
                                     fetched=fetched if prefetched_key == rule_key else None)
                if found and found.get("chunk_id"):
                    # AI가 같은 조문을 이미 인용했으면 그 근거 그대로 둔다
                    rank = connection.scalar(text("SELECT coalesce(max(rank),0)+1 FROM card_evidence WHERE card_id=:id"),
                                             {"id": card["id"]})
                    connection.execute(text("""
                        INSERT INTO card_evidence(card_id, org_id, chunk_id, rank, score, quote)
                        VALUES (:card, :org, :chunk, :rank, :score, :quote) ON CONFLICT (card_id, chunk_id) DO NOTHING
                    """), {"card": card["id"], "org": card["org_id"], "chunk": found["chunk_id"], "rank": rank,
                           "score": found["score"], "quote": found["quote"]})
                elif found:
                    item = found
    except Exception:
        item = {"unchecked": True}
    if item and item.get("unchecked"):
        connection.execute(text("""
            UPDATE cards SET draft = draft || CAST(:flag AS jsonb) WHERE id=:id
        """), {"id": card["id"], "flag": json.dumps({"law_unchecked": True})})
