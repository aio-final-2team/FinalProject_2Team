"""자료 찾는 AI(`agents/graphs/gather.py`)가 부르는 범위 지키는 도구예요.

도구 인자는 문서 종류·검색어·날짜뿐이에요. 기관·반·아이·보호자는 요청 행(학부모 문의)이나 교직원 검색 함수에서만 와서,
AI가 인자를 어떻게 적어도 다른 집 자료를 부를 수 없어요. 인자가 틀리면 ValueError를 올리고 gather는 그 호출만 건너뛰어요.
교직원 'AI에게 묻기'(mock 포함)도 이 파일을 쓰므로 DB 모듈은 학부모 도구 안에서만 불러와요.
"""

from datetime import date, datetime, timedelta

from app.core.schedule import KST

DOC_TYPES = ("notice", "schedule", "menu", "policy")
DOC_CONTENTS = {
    "notice": "가정통신문·행사 안내(행사 날짜·시간·준비물·원 소식)",
    "schedule": "월간·학사 일정표와 반 주간 활동 계획(준비물 포함)",
    "menu": "주간 점심 식단표·간식표·알레르기 대체식 안내",
    "policy": "운영 규정과 안내(원비·납부, 등·하원과 귀가 변경, 투약 의뢰, 감염병 등원 기준, 안전사고, 준비물·원복 등)",
}
MAX_QUERY = 100
DAYS_BEFORE, DAYS_AFTER = 14, 1
CHILD_TOOLS = {
    "child_records": "담임이 이 아이에 대해 그날 남긴 관찰 기록(놀이·친구 관계·식사·낮잠·몸 상태 메모). 날마다 최근 3개",
    "daily_notes": "그날 이 아이 보호자에게 실제로 보낸 알림장(오늘 하루·식사·준비물·아이 메모 줄)",
    "care": "그날 이 아이 보호자가 낸 투약·귀가 요청 글과 처리 상태(선생님 확인 대기·확인 완료·투약 완료·인계 완료·반려·취소)",
}


def documents_spec(doc_types, forecast=False):
    kinds = "; ".join(f"{kind}={DOC_CONTENTS[kind]}" for kind in doc_types)
    note = " schedule을 찾으면 질문에 나온 날의 기상청 예보가 맨 앞에 붙어요." if forecast else ""
    return {"name": "documents",
            "description": "원이 올린 자료에서 낱말로 근거 조각(문서 제목·위치·본문)을 찾아요. 질문 문장 그대로보다 "
                           "핵심 낱말(행사 이름·준비물·음식·날짜 같은)을 넣어야 잘 찾고, 한 번에 8개까지 나와요." + note,
            "args": {"doc_type": f"자료 종류 하나. {kinds}", "query": f"검색 낱말({MAX_QUERY}자 이내)"}}


def _check_keys(args, keys):
    if not isinstance(args, dict) or set(args) != set(keys):
        raise ValueError(f"인자는 {', '.join(keys)}만 받아요")


def _doc_args(args, doc_types):
    _check_keys(args, ("doc_type", "query"))
    doc_type, query = args["doc_type"], args["query"]
    if doc_type not in doc_types:
        raise ValueError(f"doc_type은 {'|'.join(doc_types)} 중 하나예요")
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY:
        raise ValueError(f"query는 1~{MAX_QUERY}자 글이에요")
    return doc_type, query.strip()


class StaffToolbox:
    """선생님 'AI에게 묻기'. search는 staff_ask가 담당 범위로 묶고 민감정보를 가린 검색 함수예요."""

    def __init__(self, search):
        self.search = search

    def specs(self):
        return [documents_spec(DOC_TYPES)]

    def call(self, name, args):
        if name != "documents":
            raise ValueError("없는 도구예요")
        return self.search(*_doc_args(args, DOC_TYPES))


class RequestToolbox:
    """학부모 요청 하나의 범위(기관·반·아이·요청한 보호자·질문 받은 날)에 묶인 도구예요.
    민원 답변은 지금처럼 가정통신문·운영 규정만 찾고, 아이 도구는 아이를 정한 문의에만 열어요."""

    def __init__(self, req, forecast=None):
        from app.modules.documents.answer import asked_on
        self.req = req
        self.forecast = forecast
        self.today = asked_on(req) or datetime.now(KST).date()
        self.doc_types = ("notice", "policy") if req["type"] == "complaint" else DOC_TYPES
        self.child = req["type"] == "inquiry" and bool(req.get("child_id"))

    def specs(self):
        specs = [documents_spec(self.doc_types, forecast=bool(self.forecast) and "schedule" in self.doc_types)]
        if self.child:
            since, until = self.today - timedelta(days=DAYS_BEFORE), self.today + timedelta(days=DAYS_AFTER)
            specs += [{"name": name, "description": description, "args": {"date": f"YYYY-MM-DD, {since}~{until} 사이 하루"}}
                      for name, description in CHILD_TOOLS.items()]
        return specs

    def _day(self, args):
        _check_keys(args, ("date",))
        try:
            day = date.fromisoformat(args["date"]) if isinstance(args["date"], str) else None
        except ValueError:
            day = None
        if day is None or not -DAYS_BEFORE <= (day - self.today).days <= DAYS_AFTER:
            raise ValueError(f"date는 {self.today - timedelta(days=DAYS_BEFORE)}~{self.today + timedelta(days=DAYS_AFTER)} "
                             "사이 YYYY-MM-DD예요")
        return day

    def call(self, name, args):
        from types import SimpleNamespace

        from app.modules.documents import answer as source
        if name == "documents":
            doc_type, query = _doc_args(args, self.doc_types)
            user = SimpleNamespace(id=self.req["requester_id"], org_id=self.req["org_id"], role="parent")
            chunks = source.search_documents(user, str(self.req["org_id"]), doc_type, query,
                                             classroom_id=self.req["classroom_id"], top_k=8)["chunks"]
            if self.forecast and doc_type == "schedule":
                chunks = [{k: v for k, v in self.forecast.items() if k != "quote"}, *chunks]
            return chunks
        if not self.child or name not in CHILD_TOOLS:
            raise ValueError("없는 도구예요")
        day = self._day(args)
        if name == "child_records":
            return source.record_chunks(self.req, [day])
        if name == "daily_notes":
            return source.sent_note_chunks(self.req, day, day)
        return source.care_request_chunks(self.req, day)
