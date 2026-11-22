"""[TEST] 가상 사진만 써서 성장 영상의 두 모드 계약을 검사해요."""

from dataclasses import replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import subprocess
from uuid import UUID, uuid4

import imageio_ffmpeg
import pytest
from sqlalchemy import text

from app import backend, worker
from app.core import growth_video as rules, jobs, media
from app.mock import feed, growth_videos, seed, store
from app.modules.feed import growth_runner as runner
from tests.integration.api.helpers import BASE, err

ROOT = f"{BASE}/children/{seed.CHILD}/growth-videos"
ORG = f"{BASE}/organizations/{seed.ORG}/posts"
REAL_ENCODE = runner.encode


@pytest.fixture(autouse=True, params=['mock', 'db'])
def growth_backend(request, monkeypatch, tmp_path, _reset_store):
    monkeypatch.setattr(media, 'settings', replace(media.settings, media_dir=str(tmp_path)))
    settings = replace(jobs.settings, data_backend=request.param, run_in='api', feature_growth_video=True)
    monkeypatch.setattr(rules, 'settings', settings)
    monkeypatch.setattr(jobs, 'settings', settings)
    if request.param == 'db':
        request.getfixturevalue('seeded_db')
        from app.core import users
        from app.modules.feed import feed as db_feed, growth_videos as db_growth
        modules = users, db_feed, db_growth
    else:
        store.reset()
        modules = store, feed, growth_videos
    for name, module in zip(('users', 'feed', 'growth_videos'), modules, strict=True):
        monkeypatch.setattr(backend, name, module)
    if request.param == 'mock':
        store.state().feed_posts.clear()
        store.state().feed_photos.clear()
    else:
        from app.core.db import transaction
        with transaction() as c:
            c.execute(text('DELETE FROM feed_photo_children; DELETE FROM feed_photos; DELETE FROM feed_posts'))
    monkeypatch.setattr(runner, 'encode', fake_encode)
    return request.param


def fake_encode(photos, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    data = b'\x00\x00\x00\x18ftypmp42[TEST] virtual video'
    output.write_bytes(data)
    return dict(duration_seconds=len(photos)*2, size_bytes=len(data), sha256=sha256(data).hexdigest())


def photos(client, actor, tags=None):
    tags = tags or [[seed.CHILD]]*3
    result = client.post(ORG, headers=actor, data={'body': '[TEST] 가상 사진', 'child_ids': json.dumps(
        [[str(c) for c in t] for t in tags])}, files=[('files', ('virtual.png', seed.feed_png(), 'image/png')) for _ in tags])
    assert result.status_code == 201, result.text
    return result.json()['post']


def create(client, parent, **body):
    response = client.post(ROOT, headers=parent, json=body)
    assert response.status_code == 202, response.text
    row = response.json()
    assert row['status'] == 'queued' and row['file_url'] is None
    return row


def listed(client, parent):
    response = client.get(ROOT, headers=parent)
    assert response.status_code == 200, response.text
    return response.json()['items']


def events(mode):
    if mode == 'mock':
        return [e.__dict__ for e in store.state().events]
    from app.core.db import transaction
    with transaction() as c:
        return [dict(e) for e in c.execute(text('SELECT * FROM events ORDER BY id')).mappings()]


def test_real_mp4_and_private_file(client, parent, monkeypatch):
    photos(client, parent)
    monkeypatch.setattr(runner, 'encode', REAL_ENCODE)
    create(client, parent, photo_limit=3)
    row = listed(client, parent)[0]
    assert row['status'] == 'succeeded' and row['duration_seconds'] == 6
    response = client.get(row['file_url'], headers=parent)
    assert response.status_code == 200 and response.content[4:8] == b'ftyp'
    assert response.headers['content-type'] == 'video/mp4'
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert len(response.content) == row['size_bytes'] and sha256(response.content).hexdigest() == row['sha256']
    assert 'storage_path' not in json.dumps(row) and 'requested_by' not in row
    user = backend.users.get_user(seed.PARENT)
    internal = backend.growth_videos.file(user, UUID(row['id']))
    reader = imageio_ffmpeg.read_frames(str(media.path(internal['storage_path'])))
    try:
        info = next(reader)
        assert info['size'] == (720, 720) and info['codec'] == 'h264'
        assert info['duration'] == pytest.approx(6, abs=0.2)
    finally:
        reader.close()


@pytest.mark.parametrize('count', [0, 2])
def test_too_few_current_photos(client, parent, count):
    if count:
        photos(client, parent, [[seed.CHILD]]*count)
    err(client.post(ROOT, headers=parent, json={}), 422, 'VALIDATION_FAILED')
    assert listed(client, parent) == []


@pytest.mark.parametrize('limit', [2, 21])
def test_photo_limit_bounds(client, parent, limit):
    err(client.post(ROOT, headers=parent, json={'photo_limit': limit}), 422, 'VALIDATION_FAILED')


def test_selects_oldest_visible_tagged_photos_up_to_limit(client, parent, teacher, monkeypatch):
    first = photos(client, teacher, [[seed.CHILD]]*3)
    photos(client, teacher, [[seed.CHILD, seed.demo_id('503')]]*3)  # 다른 아이의 family 범위라 빠져요.
    photos(client, parent, [[]]*3)  # 표시 없는 사진도 빠져요.
    photos(client, parent)
    captured = []
    def encode(rows, output):
        captured.extend(str(p['id']) for p in rows)
        return fake_encode(rows, output)
    monkeypatch.setattr(runner, 'encode', encode)
    create(client, parent, photo_limit=3)
    assert captured == [p['id'] for p in first['photos']]


@pytest.mark.parametrize('actor', ['teacher', 'director', 'parent_other'])
def test_only_guardians_all_surfaces_and_audit(client, parent, actor, request, growth_backend):
    photos(client, parent)
    row = create(client, parent)
    headers = request.getfixturevalue(actor)
    before = len(events(growth_backend))
    for response in (client.post(ROOT, headers=headers, json={}), client.get(ROOT, headers=headers),
                     client.get(f"{BASE}/growth-videos/{row['id']}/file", headers=headers),
                     client.delete(f"{BASE}/growth-videos/{row['id']}", headers=headers)):
        err(response, 403, 'FORBIDDEN')
    assert sum(e['action'] == 'permission_denied' for e in events(growth_backend)[before:]) == 4


def test_foreign_org_all_surfaces_404(client, parent, growth_backend):
    from app.core.auth import issue_token
    from app.core.db import transaction
    photos(client, parent)
    row = create(client, parent)
    uid, oid = uuid4(), uuid4()
    if growth_backend == 'mock':
        store.state().users[uid] = store.User(uid, oid, 'parent', str(uid), 'unused', '[TEST] 다른 원')
    else:
        with transaction() as c:
            c.execute(text("INSERT INTO organizations(id,name) VALUES (:id,'[TEST] 다른 원')"), {'id': oid})
            c.execute(text("INSERT INTO users(id,org_id,role,login_id,display_name,password_hash) "
                           "VALUES (:id,:org,'parent',:login,'[TEST] 다른 원','unused')"),
                      dict(id=uid, org=oid, login=str(uid)))
    actor = {'Authorization': 'Bearer '+issue_token(backend.users.get_user(uid))}
    for response in (client.post(ROOT, headers=actor, json={}), client.get(ROOT, headers=actor),
                     client.get(f"{BASE}/growth-videos/{row['id']}/file", headers=actor),
                     client.delete(f"{BASE}/growth-videos/{row['id']}", headers=actor)):
        err(response, 404, 'NOT_FOUND')


@pytest.mark.parametrize('revoke', ['delete', 'scope', 'hide', 'disk'])
def test_source_revocation_blocks_even_range(client, parent, parent_other, teacher, director, revoke):
    client.patch(f'{BASE}/children/{seed.demo_id("503")}/photo-scope', headers=parent_other, json={'photo_scope': 'org'})
    post = photos(client, teacher, [[seed.CHILD, seed.demo_id('503')]]*3)
    create(client, parent)
    row = listed(client, parent)[0]
    if revoke == 'scope':
        client.patch(f'{BASE}/children/{seed.demo_id("503")}/photo-scope', headers=parent_other, json={'photo_scope': 'family'})
    elif revoke == 'delete':
        client.delete(f"{BASE}/posts/{post['id']}", headers=teacher)
    elif revoke == 'hide':
        client.patch(f"{BASE}/posts/{post['id']}", headers=director, json={'status': 'hidden'})
    else:
        internal = backend.feed.file(backend.users.get_user(seed.PARENT), UUID(post['photos'][0]['id']))
        media.remove(internal['storage_path'])
    for extra in ({}, {'Range': 'bytes=0-7'}):
        err(client.get(row['file_url'], headers={**parent, **extra}), 404, 'NOT_FOUND')


@pytest.mark.parametrize('value,expected', [('bytes=0-7', (0, 7)), ('bytes=8-', (8, None)), ('bytes=-4', (-4, None))])
def test_range_bytes(client, parent, value, expected):
    photos(client, parent)
    create(client, parent)
    row = listed(client, parent)[0]
    whole = client.get(row['file_url'], headers=parent).content
    response = client.get(row['file_url'], headers={**parent, 'Range': value})
    start, end = expected
    assert response.status_code == 206 and response.content == whole[start:end+1 if end is not None else None]
    assert int(response.headers['content-length']) == len(response.content)
    assert response.headers['content-range'].endswith('/'+str(len(whole)))


@pytest.mark.parametrize('value', ['bytes=999999-', 'bytes=8-2', 'bytes=-0', 'bytes=0-1,3-4', 'bad'])
def test_unsatisfiable_or_multiple_range(client, parent, value):
    photos(client, parent)
    create(client, parent)
    err(client.get(listed(client, parent)[0]['file_url'], headers={**parent, 'Range': value}), 416, 'VALIDATION_FAILED')


def test_delete_removes_file_and_listing(client, parent):
    photos(client, parent)
    row = create(client, parent)
    data = backend.growth_videos.file(backend.users.get_user(seed.PARENT), UUID(row['id']))
    path = media.path(data['storage_path'])
    assert path.is_file()
    assert client.delete(f"{BASE}/growth-videos/{row['id']}", headers=parent).status_code == 204
    assert not path.exists() and listed(client, parent) == []
    err(client.get(f"{BASE}/growth-videos/{row['id']}/file", headers=parent), 404, 'NOT_FOUND')


def test_failed_encoder_cleans_partial_file(client, parent, monkeypatch, tmp_path):
    photos(client, parent)
    def fail(rows, output):
        fake_encode(rows, output)
        raise subprocess.TimeoutExpired('[TEST] ffmpeg', 120)
    monkeypatch.setattr(runner, 'encode', fail)
    create(client, parent)
    assert listed(client, parent)[0]['status'] == 'failed'
    assert not list(tmp_path.rglob('*.mp4'))


def test_single_claim_and_late_finish_cannot_revive_deleted_job(client, parent, monkeypatch, tmp_path):
    photos(client, parent)
    monkeypatch.setattr(jobs, 'dispatch', lambda *args: None)
    row = create(client, parent)
    vid = UUID(row['id'])
    assert backend.growth_videos.claim(vid)['status'] == 'running'
    assert backend.growth_videos.claim(vid) is None
    client.delete(f'{BASE}/growth-videos/{vid}', headers=parent)
    assert backend.growth_videos.finish(vid, dict(duration_seconds=6, size_bytes=10, sha256='a'*64)) is False
    runner.run_growth_video(vid)
    assert not list(tmp_path.rglob('*.mp4'))


def test_worker_default_queue_and_broker_failure_sweep(client, parent, monkeypatch, growth_backend, tmp_path):
    from app.core.db import transaction
    photos(client, parent)
    monkeypatch.setattr(jobs, 'settings', replace(jobs.settings, run_in='worker'))
    def fail(**kwargs):
        raise ConnectionError('[TEST] broker')
    monkeypatch.setattr(worker.growth_video, 'apply_async', fail)
    row = create(client, parent)
    assert worker.celery_app.amqp.router.route({}, 'yuchion.growth_video')['queue'].name == 'default'
    if growth_backend == 'db':
        assert listed(client, parent)[0]['status'] == 'queued'
        with transaction() as c:
            c.execute(text("UPDATE growth_videos SET created_at=now()-interval '6 minutes'"))
        assert backend.growth_videos.sweep() == 1
        assert listed(client, parent)[0]['status'] == 'failed'
    else:
        assert listed(client, parent)[0]['status'] == 'succeeded'
    assert backend.growth_videos.claim(UUID(row['id'])) is None


def test_worker_task_executes_once(client, parent, monkeypatch, growth_backend):
    photos(client, parent)
    monkeypatch.setattr(jobs, 'dispatch', lambda *args: None)
    row = create(client, parent)
    monkeypatch.setattr(worker, 'settings', replace(jobs.settings, run_in='worker'))
    execute = worker.growth_video.run if growth_backend == 'db' else runner.run_growth_video
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(execute, [row['id']]*4))
    assert listed(client, parent)[0]['status'] == 'succeeded'
    assert sum(e['action'] == 'growth_video_completed' for e in events(growth_backend)) == 1


def test_sweep_running_and_startup_cleanup(client, parent, monkeypatch, tmp_path):
    from app import main
    from fastapi.testclient import TestClient
    photos(client, parent)
    monkeypatch.setattr(jobs, 'dispatch', lambda *args: None)
    for _ in range(2):
        create(client, parent)
    row = listed(client, parent)[0]
    claimed = backend.growth_videos.claim(UUID(row['id']))
    fake_encode([1, 2, 3], media.path(claimed['storage_path']))
    monkeypatch.setattr(main, 'settings', replace(jobs.settings, feature_growth_video=False, data_backend='mock'))
    with TestClient(main.app):
        pass
    assert all(r['status'] == 'failed' for r in listed(client, parent))
    assert backend.growth_videos.finish(UUID(row['id']), dict(duration_seconds=6, size_bytes=10, sha256='a'*64)) is False
    assert not list(tmp_path.rglob('*.mp4'))


def test_stale_running_sweep_discards_late_output(client, parent, monkeypatch, growth_backend, tmp_path):
    from app.core.db import transaction
    photos(client, parent)
    monkeypatch.setattr(jobs, 'dispatch', lambda *args: None)
    row = create(client, parent)
    vid = UUID(row['id'])
    claimed = backend.growth_videos.claim(vid)
    fake_encode([1, 2, 3], media.path(claimed['storage_path']))
    if growth_backend == 'mock':
        store.state().growth_videos[vid]['started_at'] = store.now()-timedelta(minutes=6)
    else:
        with transaction() as c:
            c.execute(text("UPDATE growth_videos SET started_at=now()-interval '6 minutes'"))
    assert backend.growth_videos.sweep() == 1 and backend.growth_videos.sweep() == 0
    assert not list(tmp_path.rglob('*.mp4')) and listed(client, parent)[0]['status'] == 'failed'
    assert backend.growth_videos.finish(vid, dict(duration_seconds=6, size_bytes=10, sha256='a'*64)) is False


def test_disabled_every_route_before_auth_and_unchanged_existing_contract(client, parent, monkeypatch):
    monkeypatch.setattr(rules, 'settings', replace(rules.settings, feature_growth_video=False))
    for actor in (None, parent):
        for method, path in [('post', ROOT), ('get', ROOT), ('get', f'{BASE}/growth-videos/{uuid4()}/file'),
                             ('delete', f'{BASE}/growth-videos/{uuid4()}')]:
            err(getattr(client, method)(path, headers=actor), 404, 'NOT_FOUND')
    assert client.get(ORG.replace('/posts', '/albums'), headers=parent).status_code == 200
