"""[TEST] 보호자 기억의 확인 전 차단과 가정·반 경계를 확인해요."""
from uuid import uuid4
import pytest
from app import backend
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api.test_memories import memory_backend


def save(mode, candidates, body=None, **changes):
    req = dict(id=uuid4(), org_id=seed.ORG, requester_id=seed.PARENT, child_id=seed.CHILDREN[0]['id'],
               body=body or '견과류 알레르기가 있어요. 평소 상담은 오후 4시 이후를 선호해요.', **changes)
    # 알림의 요청 FK를 위해 실제 접수 대신 기본 시드 요청을 출처로 써요.
    req['id'] = seed.DEMO_NOTE_REQUESTS[0]['id']
    if mode == 'db':
        with transaction() as c:
            backend.memories.save_parent_candidates(c, req, candidates, [x['display_name'] for x in seed.CHILDREN])
    else:
        backend.memories.save_parent_candidates(req, candidates, [x['display_name'] for x in seed.CHILDREN])
    return req


def load(mode, child_id, reader_id):
    if mode == 'db':
        with transaction() as c:
            return backend.memories.load_child_notes(c, seed.ORG, child_id, reader_id)
    return backend.memories.load_child_notes(seed.ORG, child_id, reader_id)


CARE = dict(kind='care_note', content='견과류 알레르기가 있어요.')
PREF = dict(kind='preference', content='평소 상담은 오후 4시 이후를 선호해요.', structured={'after': '16:00'})


def test_memory_parent_pending_dedupe_and_preference(memory_backend):
    req = save(memory_backend, [CARE, PREF])
    save(memory_backend, [CARE, PREF])
    assert load(memory_backend, req['child_id'], seed.PARENT) == []
    if memory_backend == 'db':
        from sqlalchemy import text
        with transaction() as c:
            rows = c.execute(text("SELECT kind,confirm_status FROM memories")).all()
            assert sorted(rows) == [('care_note','pending'), ('preference','confirmed')]
            assert c.scalar(text("SELECT count(*) FROM notifications WHERE kind='memory_candidate'")) == 1
            assert backend.memories.load_preferences(c, seed.ORG, seed.PARENT)[0]['structured']['after'] == '16:00'
    else:
        assert len(store.state().memories) == 2
        assert len([n for n in store.state().notifications.values() if n.kind == 'memory_candidate']) == 1
        assert backend.memories.load_preferences(seed.ORG, seed.PARENT)[0]['structured']['after'] == '16:00'


def test_memory_parent_rejects_temporary_diagnosis_other_child_and_sensitive(memory_backend):
    from sqlalchemy import text
    for body, content in [('오늘만 낮잠 전에 책을 읽어 주세요.','낮잠 전에 책을 읽어 주세요.'),
                          ('ADHD 진단으로 낮잠이 어려워요.','낮잠이 어려워요.'),
                          ('친구는 견과류 알레르기가 있어요.',CARE['content']),
                          ('낮잠 연락은 010-1234-5678로 해요.','낮잠 연락은 010-1234-5678로 해요.'),
                          ('견과류 알레르기는 없어요.',CARE['content'])]:
        save(memory_backend, [dict(kind='care_note',content=content)],body)
    save(memory_backend, [dict(kind='preference',content='평소 견과류 알레르기가 있어요.')],
         '평소 견과류 알레르기가 있어요.')
    if memory_backend == 'db':
        with transaction() as c:
            assert c.scalar(text('SELECT count(*) FROM memories')) == 0
    else:
        assert not store.state().memories


def test_memory_child_reader_scope_and_deleted(memory_backend):
    from sqlalchemy import text
    req = save(memory_backend, [CARE])
    if memory_backend == 'db':
        with transaction() as c:
            c.execute(text("UPDATE memories SET confirm_status='confirmed',confirmed_at=now()"))
    else:
        for m in store.state().memories.values():
            m.confirm_status = 'confirmed'
    assert load(memory_backend, req['child_id'], seed.PARENT)
    assert load(memory_backend, req['child_id'], seed.TEACHER)
    assert not load(memory_backend, req['child_id'], seed.TEACHER_OTHER)
    assert not load(memory_backend, req['child_id'], seed.DIRECTOR)
    assert not load(memory_backend, seed.CHILDREN[1]['id'], seed.PARENT)
    assert not load(memory_backend, req['child_id'], seed.PARENT_OTHER)
    if memory_backend == 'db':
        with transaction() as c:
            c.execute(text('UPDATE memories SET deleted_at=now()'))
    else:
        for m in store.state().memories.values():
            m.deleted_at=store.now()
    assert not load(memory_backend, req['child_id'], seed.TEACHER)
