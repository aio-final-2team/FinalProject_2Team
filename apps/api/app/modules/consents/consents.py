"""[제안] 동의와 이력을 같은 트랜잭션에서 저장해요."""

from sqlalchemy import text

from app.core import consents as rules
from app.core.constants import CONSENT_VERSION
from app.core.db import transaction
from app.modules.feed.feed import record


def _get(connection, user):
    agreed = dict(connection.execute(text("""
        SELECT item, agreed_at FROM user_consents
        WHERE org_id=:org AND user_id=:user AND terms_version=:version
    """), {"org": user.org_id, "user": user.id, "version": CONSENT_VERSION}).all())
    return rules.view(user.role, agreed)


def get(user):
    with transaction() as connection:
        return _get(connection, user)


def agree(user, items, terms_version):
    required = rules.validate(user, items, terms_version)
    with transaction() as connection:
        changed = False
        for item in required:
            inserted = connection.scalar(text("""
                INSERT INTO user_consents(org_id,user_id,item,terms_version)
                VALUES (:org,:user,:item,:version) ON CONFLICT DO NOTHING RETURNING id
            """), {"org": user.org_id, "user": user.id, "item": item, "version": terms_version})
            changed = changed or inserted is not None
        if changed:
            record(connection, user, "consent_agreed", items=required, terms_version=terms_version)
        return _get(connection, user)


def classroom(user, classroom_id):
    with transaction() as connection:
        org = connection.scalar(text("SELECT org_id FROM classrooms WHERE id=:id AND org_id=:org"),
                                {"id": classroom_id, "org": user.org_id})
        rules.check_classroom(user, classroom_id, org)
        completed = set(connection.scalars(text("""
            SELECT u.id FROM users u JOIN user_consents s ON (s.user_id,s.org_id)=(u.id,u.org_id)
            WHERE u.org_id=:org AND u.role='parent' AND s.terms_version=:version AND s.item=ANY(:items)
            GROUP BY u.id HAVING count(*)=:total
        """), {"org": user.org_id, "version": CONSENT_VERSION,
               "items": rules.required_items("parent"), "total": len(rules.required_items("parent"))}))
        children = connection.execute(text("""
            SELECT c.id,c.display_name,
              coalesce(array_agg(g.user_id) FILTER (WHERE g.user_id IS NOT NULL),'{}') AS guardians
            FROM children c LEFT JOIN child_guardians g ON (g.child_id,g.org_id)=(c.id,c.org_id)
            WHERE c.org_id=:org AND c.classroom_id=:class
            GROUP BY c.id ORDER BY c.display_name,c.id
        """), {"org": user.org_id, "class": classroom_id}).mappings()
        return {"items": [rules.child_view(c["id"], c["display_name"], c["guardians"], completed) for c in children]}
