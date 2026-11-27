"""QA 원 목록과 데모 ID의 결정적 변환. 기본 시드에는 관여하지 않아요."""

from uuid import UUID, uuid5

from app.mock.seed import ORG

QA_ORGS = tuple({"tag": tag, "name": f"QA {name} 원", "login_prefix": f"{tag}."}
                for tag, name in (("sj", "성주"), ("ym", "영민"), ("jh", "지혜"), ("ih", "인혜"), ("tw", "태웅")))


def qa_id(tag, source):
    return uuid5(uuid5(ORG, f"qa:{tag}"), str(source))


def find_org(org_id: UUID):
    return next((org for org in QA_ORGS if qa_id(org["tag"], ORG) == org_id), None)
