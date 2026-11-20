"""국가법령정보 공동활용 Open API로 법령 조문 원문을 가져온다(get_law_article).

흐름: lawSearch.do로 법령 이름 → 법령일련번호(MST), lawService.do(JO)로 그 조문.
계약(API 설계 문서 5.4): 인자 law_name·article, 성공 data {text, source_url, fetched_at},
실패 UPSTREAM_UNAVAILABLE(참)·NOT_FOUND(거짓).
"""

import os
import re
import urllib.parse

from tools.public_apis.common import fetch_json, not_found, now_kst, tool_result, upstream

SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
PUBLIC_URL = "https://www.law.go.kr/법령/{name}/{article}"
NAME = "국가법령정보 API"
ARTICLE_RE = re.compile(r"^\s*제?\s*(\d{1,4})\s*조?\s*(?:의\s*(\d{1,2}))?\s*$")


def article_code(article):
    """'제33조'·'33'·'제31조의2' → JO 값 '003300'·'003300'·'003102'과 표시 이름."""
    match = ARTICLE_RE.match(str(article))
    if not match:
        raise not_found(f"조문 번호를 읽지 못했어요: {article}")
    number, branch = int(match.group(1)), int(match.group(2) or 0)
    label = f"제{number}조" + (f"의{branch}" if branch else "")
    return f"{number:04d}{branch:02d}", label


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def article_text(unit):
    """조문내용 + 항 + 호를 줄바꿈으로 잇는다."""
    lines = [unit.get("조문내용", "").strip()]
    for paragraph in _as_list(unit.get("항")):
        lines.append(paragraph.get("항내용", "").strip())
        lines.extend(item.get("호내용", "").strip() for item in _as_list(paragraph.get("호")))
    return "\n".join(line for line in lines if line)


class LawClient:
    def __init__(self, oc=None, opener=None):
        self.oc = oc if oc is not None else os.getenv("LAW_GO_KR_OC", "")
        self.opener = opener

    def _get(self, base, **params):
        if not self.oc:
            raise upstream("LAW_GO_KR_OC가 없어 법령 API를 부를 수 없어요", False)
        query = urllib.parse.urlencode({"OC": self.oc, "type": "JSON", "target": "law", **params})
        return fetch_json(f"{base}?{query}", NAME, self.opener)

    def find_law(self, law_name):
        """이름이 정확히 같은 현행 법령의 법령일련번호. 시행령·시행규칙과 섞지 않는다."""
        wanted = law_name.replace(" ", "")
        result = self._get(SEARCH_URL, query=law_name).get("LawSearch") or {}
        for law in _as_list(result.get("law")):
            if law.get("법령명한글", "").replace(" ", "") == wanted and law.get("현행연혁코드", "현행") == "현행":
                return law["법령일련번호"], law["법령명한글"]
        raise not_found(f"'{law_name}' 이름의 현행 법령이 없어요")

    def get_article(self, law_name, article):
        jo, label = article_code(article)
        mst, name = self.find_law(law_name)
        body = self._get(SERVICE_URL, MST=mst, JO=jo).get("법령") or {}
        unit = (body.get("조문") or {}).get("조문단위")
        unit = next((u for u in _as_list(unit) if u.get("조문여부", "조문") == "조문"), None)
        if not unit:
            raise not_found(f"{name}에 {label}이 없어요")
        return {"text": article_text(unit),
                "source_url": PUBLIC_URL.format(name=urllib.parse.quote(name), article=urllib.parse.quote(label)),
                "fetched_at": now_kst().isoformat(timespec="seconds")}


def get_law_article(law_name, article, *, client=None, trace_id=None):
    """에이전트 도구 get_law_article. 공통 출력 형식으로 돌려준다."""
    client = client or LawClient()
    return tool_result(lambda: client.get_article(law_name, article), trace_id)
