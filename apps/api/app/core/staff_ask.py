"""[제안] 기존 문의 답변의 인용 검증·가리기를 교직원 질문에도 적용해요."""

from agents.graphs import answer as graph
from agents.guardrails.sensitive import mask_sensitive
from agents.llm import ModelError
from app.core.errors import ApiError
from app.modules.documents.tools import StaffToolbox


class MaskedModel:
    def __init__(self, model):
        self.model = model
        self.failed = False

    def json(self, system, user):
        try:
            return self.model.json(system, mask_sensitive(user))
        except ModelError:
            self.failed = True
            raise
        except Exception as error:
            # 답변 그래프의 근거 없음 대체 경로와 모델 장애를 구분해요.
            raise ApiError(503, "UPSTREAM_UNAVAILABLE") from error


def respond(question, search, sources, writer=None, checker=None):
    def safe_search(kind, query):
        return [{k: mask_sensitive(v) if isinstance(v, str) else v for k, v in chunk.items()}
                for chunk in search(kind, query)]

    try:
        writer = MaskedModel(writer if writer is not None else graph.OpenAIModel("DOCUMENT"))
        checker = MaskedModel(checker if checker is not None else graph.OpenAIModel("CHECKER"))
        draft = graph.draft_answer(mask_sensitive(question), safe_search,
                                  writer=writer, checker=checker, gather_tools=StaffToolbox(safe_search))
    except ApiError:
        raise
    except Exception as error:
        raise ApiError(503, "UPSTREAM_UNAVAILABLE") from error
    evidence = [sources[e["chunk_id"]] for e in draft["evidence"] if e["chunk_id"] in sources]
    if draft["conflict"]:
        return {"answer": "자료마다 내용이 달라요. 아래 두 자료를 확인해 주세요.",
                "evidence": evidence, "conflict": True}
    if draft["no_evidence"] or not draft["check_result"]["passed"]:
        if writer.failed or checker.failed:
            raise ApiError(503, "UPSTREAM_UNAVAILABLE")
        evidence = []
    return {"answer": draft["text"] if evidence else "자료에서 못 찾았어요",
            "evidence": evidence, "conflict": False}
