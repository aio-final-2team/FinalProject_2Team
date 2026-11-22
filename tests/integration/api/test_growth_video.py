"""[TEST] 가상 사진만 써서 성장 영상의 두 모드 계약을 검사해요."""

from dataclasses import replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import subprocess
import time
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


def fake_encode(photos, output, *, limit=20):
    photos = photos[:limit]
    output.parent.mkdir(parents=True, exist_ok=True)
    data = b'\x00\x00\x00\x18ftypmp42[TEST] virtual video'
    output.write_bytes(data)
    result = dict(duration_seconds=len(photos)*2, size_bytes=len(data), sha256=sha256(data).hexdigest())
    if photos and isinstance(photos[0], dict):
        result.update(photo_count=len(photos), photo_ids=[p['id'] for p in photos])
    return result


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
    def encode(rows, output, *, limit=20):
        rows = rows[:limit]
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


@pytest.mark.parametrize('value', ['bytes=999999-'])
def test_unsatisfiable_or_multiple_range(client, parent, value):
    photos(client, parent)
    create(client, parent)
    response = client.get(listed(client, parent)[0]['file_url'], headers={**parent, 'Range': value})
    err(response, 416, 'VALIDATION_FAILED')
    assert response.headers['content-range'].startswith('bytes */')


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
    def fail(rows, output, **kwargs):
        fake_encode(rows, output)
        raise subprocess.TimeoutExpired('[TEST] ffmpeg', 120)
    monkeypatch.setattr(runner, 'encode', fail)
    create(client, parent)
    row = listed(client, parent)[0]
    assert row['status'] == 'failed' and row['failure_reason'] == 'processing_failed'
    assert not list(tmp_path.rglob('*.mp4'))


def test_single_claim_and_late_finish_cannot_revive_deleted_job(client, parent, monkeypatch, tmp_path):
    photos(client, parent)
    monkeypatch.setattr(jobs, 'dispatch', lambda *args: None)
    row = create(client, parent)
    vid = UUID(row['id'])
    assert backend.growth_videos.claim(vid)['status'] == 'running'
    assert backend.growth_videos.claim(vid) is None
    client.delete(f'{BASE}/growth-videos/{vid}', headers=parent)
    if backend.growth_videos is growth_videos:
        deleted = store.state().growth_videos[vid]
    else:
        from app.core.db import transaction
        with transaction() as c:
            deleted = c.execute(text('SELECT * FROM growth_videos WHERE id=:id'), {'id': vid}).mappings().one()
    assert deleted['status'] == 'failed' and deleted['failure_reason'] == 'deleted'
    assert backend.growth_videos.finish(vid, dict(duration_seconds=6, size_bytes=10, sha256='a'*64)) is False
    runner.run_growth_video(vid)
    assert not list(tmp_path.rglob('*.mp4'))


def test_worker_media_queue_and_broker_failure_sweep(client, parent, monkeypatch, growth_backend, tmp_path):
    from app.core.db import transaction
    photos(client, parent)
    monkeypatch.setattr(jobs, 'settings', replace(jobs.settings, run_in='worker'))
    def fail(**kwargs):
        raise ConnectionError('[TEST] broker')
    monkeypatch.setattr(worker.growth_video, 'apply_async', fail)
    row = create(client, parent)
    assert worker.celery_app.amqp.router.route({}, 'yuchion.growth_video')['queue'].name == 'media'
    if growth_backend == 'db':
        assert listed(client, parent)[0]['status'] == 'queued'
        with transaction() as c:
            c.execute(text("UPDATE growth_videos SET created_at=now()-interval '31 minutes'"))
        assert backend.growth_videos.sweep() == 1
        assert listed(client, parent)[0]['failure_reason'] == 'stale'
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
    create(client, parent)
    row = listed(client, parent)[0]
    claimed = backend.growth_videos.claim(UUID(row['id']))
    fake_encode([1, 2, 3], media.path(claimed['storage_path']))
    monkeypatch.setattr(main, 'settings', replace(jobs.settings, feature_growth_video=False, data_backend='mock'))
    with TestClient(main.app):
        pass
    assert all(r['status'] == 'failed' and r['failure_reason'] == 'interrupted' for r in listed(client, parent))
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
        store.state().growth_videos[vid]['started_at'] = store.now()-timedelta(minutes=7)
    else:
        with transaction() as c:
            c.execute(text("UPDATE growth_videos SET started_at=now()-interval '7 minutes'"))
    assert backend.growth_videos.sweep() == 1 and backend.growth_videos.sweep() == 0
    assert not list(tmp_path.rglob('*.mp4')) and listed(client, parent)[0]['status'] == 'failed'
    assert listed(client, parent)[0]['failure_reason'] == 'stale'
    assert backend.growth_videos.finish(vid, dict(duration_seconds=6, size_bytes=10, sha256='a'*64)) is False


def test_disabled_every_route_before_auth_and_unchanged_existing_contract(client, parent, monkeypatch):
    monkeypatch.setattr(rules, 'settings', replace(rules.settings, feature_growth_video=False))
    for actor in (None, parent):
        for method, path in [('post', ROOT), ('get', ROOT), ('get', f'{BASE}/growth-videos/{uuid4()}/file'),
                             ('delete', f'{BASE}/growth-videos/{uuid4()}')]:
            err(getattr(client, method)(path, headers=actor), 404, 'NOT_FOUND')
    assert client.get(ORG.replace('/posts', '/albums'), headers=parent).status_code == 200


@pytest.mark.parametrize('value,status', [('Bytes=0-1', 206), ('bytes= 0-1', 200),
    ('bytes=0-1,3-4', 200), ('items=0-1', 200), ('bytes=5-3', 200), ('bytes=-0', 200)])
def test_range_ignores_unreadable_values(client, parent, value, status):
    photos(client, parent)
    create(client, parent)
    url = listed(client, parent)[0]['file_url']
    whole = client.get(url, headers=parent).content
    response = client.get(url, headers={**parent, 'Range': value})
    assert response.status_code == status
    assert response.content == (whole[:2] if status == 206 else whole)


def test_body_can_be_omitted(client, parent):
    photos(client, parent)
    assert client.post(ROOT, headers=parent).status_code == 202


def test_twenty_simultaneous_requests_have_one_pending_job(client, parent, monkeypatch):
    photos(client, parent)
    monkeypatch.setattr(jobs, 'dispatch', lambda *args: None)
    # 연결·잠금 경합을 보며 인코더 부하는 별도 실제 시험에서 확인해요.
    from unittest.mock import Mock
    prepare = Mock(side_effect=AssertionError('[TEST] 요청 안에서 디코딩하면 안 돼요.'))
    monkeypatch.setattr(runner, 'prepare', prepare)
    from threading import Barrier
    barrier = Barrier(20)
    def post(_):
        barrier.wait(timeout=10)
        return client.post(ROOT, headers=parent, json={}).status_code
    with ThreadPoolExecutor(max_workers=20) as pool:
        codes = list(pool.map(post, range(20)))
    assert codes.count(202) == 1 and codes.count(409) == 19
    prepare.assert_not_called()
    assert len(listed(client, parent)) == 1


def test_thirty_requests_stop_at_five_retained_videos(client, parent, monkeypatch):
    photos(client, parent)
    monkeypatch.setattr(runner, 'prepare', lambda *args: True)
    codes = [client.post(ROOT, headers=parent, json={}).status_code for _ in range(30)]
    assert codes == [202]*5 + [409]*25
    assert len(listed(client, parent)) == 5
    assert client.delete(f"{BASE}/growth-videos/{listed(client, parent)[0]['id']}", headers=parent).status_code == 204
    assert client.post(ROOT, headers=parent, json={}).status_code == 202


def test_photo_rechecks_do_not_create_permission_audits(client, parent, growth_backend):
    from app.core.db import transaction
    post = client.post(f'{BASE}/classrooms/{seed.CLASS_STAR}/posts', headers=parent,
                      data={'body': '[TEST] 옛 반 사진', 'child_ids': json.dumps([[str(seed.CHILD)]]*5)},
                      files=[('files', ('virtual.png', seed.feed_png(), 'image/png'))]*5)
    assert post.status_code == 201
    create(client, parent)
    url = listed(client, parent)[0]['file_url']
    if growth_backend == 'mock':
        store.state().children[seed.CHILD].classroom_id = seed.CLASS_SUN
    else:
        with transaction() as c:
            c.execute(text('UPDATE children SET classroom_id=:room WHERE id=:id'),
                      {'room': seed.CLASS_SUN, 'id': seed.CHILD})
    before = sum(e['action'] == 'permission_denied' for e in events(growth_backend))
    err(client.post(ROOT, headers=parent, json={}), 422, 'VALIDATION_FAILED')
    err(client.get(url, headers=parent), 404, 'NOT_FOUND')
    assert sum(e['action'] == 'permission_denied' for e in events(growth_backend)) == before


@pytest.mark.parametrize('shape', ['4000x3000', '3000x1', '1x3000', 'transparent'])
def test_real_preprocessing_large_extreme_and_transparent(client, parent, monkeypatch, tmp_path, shape):
    source = tmp_path / 'synthetic.png'
    runner.ffmpeg(['-f', 'lavfi', '-i', 'testsrc=size='+('32x32' if shape == 'transparent' else shape),
                   '-frames:v', '1', '-threads', '1', str(source)], 10)
    if shape == 'transparent':
        # 코드로 만든 RGBA PNG: 투명 빨강이 검은 배경 위에 합성돼야 해요.
        import struct
        import zlib
        def chunk(kind, data):
            return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
        source.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 0))
                           +chunk(b'IDAT', zlib.compress((b'\0'+b'\xff\0\0\0'*2)*2))+chunk(b'IEND', b''))
    monkeypatch.setattr(runner, 'encode', REAL_ENCODE)
    response = client.post(ORG, headers=parent,
        data={'body': '[TEST] 합성 사진', 'child_ids': json.dumps([[str(seed.CHILD)]]*3)},
        files=[('files', ('synthetic.png', source.read_bytes(), 'image/png'))]*3)
    assert response.status_code == 201
    started = time.monotonic()
    create(client, parent)
    assert time.monotonic()-started < 30
    row = listed(client, parent)[0]
    assert row['status'] == 'succeeded' and row['duration_seconds'] == 6
    internal = backend.growth_videos.file(backend.users.get_user(seed.PARENT), UUID(row['id']))
    reader = imageio_ffmpeg.read_frames(str(media.path(internal['storage_path'])))
    try:
        next(reader)
        frame = next(reader)
        if shape == 'transparent':
            assert max(frame) < 8
        else:
            assert max(frame) > 100  # 극단 비율도 전부 검은 화면이 아니에요.
    finally:
        reader.close()
    assert not list(tmp_path.rglob('growth-frames-*'))


def test_bad_and_animated_photos_from_other_parent_are_skipped(client, parent, parent_other, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "encode", REAL_ENCODE)
    animated_path = tmp_path/'moving.webp'
    runner.ffmpeg(['-f', 'lavfi', '-i', 'testsrc=size=16x16:rate=2', '-frames:v', '2',
                   '-c:v', 'libwebp_anim', '-loop', '0', str(animated_path)], 10)
    animated = animated_path.read_bytes()
    assert b'ANIM' in animated
    response = client.post(f'{BASE}/classrooms/{seed.CLASS_STAR}/posts', headers=parent_other,
        data={'body': '[TEST] 깨진 사진', 'child_ids': json.dumps([[str(seed.CHILD)]]*2)},
        files=[('files', ('bad.png', seed.feed_png()[:33], 'image/png')),
               ('files', ('animated.webp', animated, 'image/webp'))])
    assert response.status_code == 201
    photos(client, parent)
    for _ in range(2):
        create(client, parent, photo_limit=3)
        row = listed(client, parent)[0]
        assert row["status"] == "succeeded" and row["photo_count"] == 3
        assert client.get(row["file_url"], headers=parent).status_code == 200


def test_invalid_sources_leave_less_than_three(client, parent, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "encode", REAL_ENCODE)
    photos(client, parent, [[seed.CHILD]]*2)
    client.post(ORG, headers=parent, data={'body': '[TEST] 깨진 사진', 'child_ids': json.dumps([[str(seed.CHILD)]])},
                files=[('files', ('bad.png', seed.feed_png()[:33], 'image/png'))])
    create(client, parent)
    row = listed(client, parent)[0]
    assert row['status'] == 'failed' and row['failure_reason'] == 'not_enough_photos'
    assert row['file_url'] is None and not list(tmp_path.rglob('*.mp4'))
    assert not list(tmp_path.rglob('growth-frames-*'))


@pytest.mark.parametrize('status,age,expected', [('queued', 1799, 0), ('queued', 1801, 1),
                                              ('running', 359, 0), ('running', 361, 1)])
def test_sweep_uses_distinct_queue_and_running_limits(client, parent, monkeypatch, growth_backend, status, age, expected):
    from app.core.db import transaction
    photos(client, parent)
    monkeypatch.setattr(jobs, 'dispatch', lambda *args: None)
    row = create(client, parent)
    vid = UUID(row['id'])
    if status == 'running':
        backend.growth_videos.claim(vid)
    field = 'created_at' if status == 'queued' else 'started_at'
    if growth_backend == 'mock':
        store.state().growth_videos[vid][field] = store.now()-timedelta(seconds=age)
    else:
        with transaction() as c:
            c.execute(text(f'UPDATE growth_videos SET {field}=now()-make_interval(secs=>:age)'), {'age': age})
    assert backend.growth_videos.sweep() == expected


def test_api_executor_is_serial_and_does_not_use_starlette_pool(monkeypatch):
    import asyncio
    import threading
    started, release = threading.Event(), threading.Event()
    threads = []
    def work(_):
        threads.append(threading.current_thread().name)
        started.set()
        assert release.wait(5)
    monkeypatch.setattr(runner, 'run_growth_video', work)
    async def run():
        tasks = [asyncio.create_task(runner.run_in_api(i)) for i in range(3)]
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert len(threads) == 1
            import anyio
            assert await anyio.to_thread.run_sync(lambda: '[TEST] free shared pool') == '[TEST] free shared pool'
        finally:
            release.set()
            await asyncio.gather(*tasks)
    asyncio.run(run())
    assert len(threads) == 3 and len(set(threads)) == 1 and threads[0].startswith('growth-video')


def test_dimension_headers_and_preflight_rejections(monkeypatch, tmp_path):
    import struct
    png = b'\x89PNG\r\n\x1a\n'+struct.pack('>I', 13)+b'IHDR'+struct.pack('>II', 800, 600)+b'\0'*9
    jpeg = b'\xff\xd8\xff\xc2'+struct.pack('>HBHH', 8, 8, 600, 800)+b'\0'
    def webp(kind, body):
        return b'RIFF'+(len(body)+12).to_bytes(4, 'little')+b'WEBP'+kind+len(body).to_bytes(4, 'little')+body
    vp8 = webp(b'VP8 ', b'\0'*3+b'\x9d\x01\x2a'+struct.pack('<HH', 800, 600))
    vp8l = webp(b'VP8L', b'\x2f'+(799+(599 << 14)).to_bytes(4, 'little'))
    vp8x = webp(b'VP8X', b'\0'*4+(799).to_bytes(3, 'little')+(599).to_bytes(3, 'little'))
    assert all(runner.dimensions(data) == (800, 600) for data in (png, jpeg, vp8, vp8l, vp8x))
    def unexpected(*args):
        pytest.fail('거절한 머리는 ffmpeg를 실행하지 않아야 해요.')
    monkeypatch.setattr(runner, 'ffmpeg', unexpected)
    huge = png[:16]+struct.pack('>II', 10000, 10000)+png[24:]
    animated = png+struct.pack('>I', 8)+b'acTL'+b'\0'*12
    for data in (huge, animated, webp(b'VP8X', b'\x02'+b'\0'*9)):
        source = tmp_path/'rejected.png'
        source.write_bytes(data)
        assert runner.prepare(source, tmp_path/'frame.png') is False


def test_preprocessing_timeout_and_encoding_failure_clean_temp(monkeypatch, tmp_path):
    source = tmp_path/'valid.png'
    source.write_bytes(seed.feed_png())
    def timeout(*args):
        raise subprocess.TimeoutExpired('[TEST] preflight', 10)
    monkeypatch.setattr(runner, 'ffmpeg', timeout)
    assert runner.prepare(source, tmp_path/'frame.png') is False
    monkeypatch.setattr(runner, 'prepare', lambda source, out: (out.write_bytes(seed.feed_png()) or True))
    with pytest.raises(subprocess.TimeoutExpired):
        REAL_ENCODE([dict(id=uuid4(), storage_path='valid.png')]*3, tmp_path/'failed.mp4')
    assert not list(tmp_path.rglob('growth-frames-*'))


def test_ffmpeg_is_killed_when_parent_dies():
    # Linux 감독 프로세스가 고아 자식까지 회수해요. Python preexec_fn은 쓰지 않아요.
    import os
    import shutil
    import sys
    if not sys.platform.startswith('linux') or not shutil.which('setpriv'):
        pytest.skip('[TEST] setpriv 부모 사망 검사는 Linux에서만 실행해요.')
    script = """
import ctypes, os, signal, time
from pathlib import Path
from app.modules.feed.growth_runner import ffmpeg
assert ctypes.CDLL(None).prctl(36, 1, 0, 0, 0) == 0
parent = os.fork()
if parent == 0:
    ffmpeg(['-re', '-f', 'lavfi', '-i', 'testsrc=size=16x16', '-f', 'null', '-'], 8)
    os._exit(0)
child = None
try:
    for _ in range(300):
        ids = Path(f'/proc/{parent}/task/{parent}/children').read_text().split()
        if ids:
            child = int(ids[0])
            # setpriv가 ffmpeg로 exec될 때까지 기다려요.
            if 'ffmpeg' in Path(f'/proc/{child}/comm').read_text():
                break
        time.sleep(0.01)
    else:
        raise AssertionError('[TEST] ffmpeg not started')
    os.kill(parent, signal.SIGKILL)
    os.waitpid(parent, 0)
    parent = None
    pid, status = os.waitpid(child, 0)
    child = None
    assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
    print('[TEST] ffmpeg child killed and reaped')
finally:
    for pid in (parent, child):
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except ProcessLookupError:
                pass
"""
    result = subprocess.run([sys.executable, '-c', script], env={**os.environ, 'PYTHONPATH': 'apps/api'},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert '[TEST] ffmpeg child killed and reaped' in result.stdout


@pytest.mark.parametrize('operation', ['file', 'delete'])
def test_twenty_file_or_delete_requests_do_not_nest_connections(client, parent, monkeypatch, growth_backend,
                                                               operation, request):
    from threading import Barrier
    from app.core import db
    from app.core.errors import ApiError
    from sqlalchemy import create_engine
    photos(client, parent)
    vid = UUID(create(client, parent)['id'])
    user = backend.users.get_user(seed.PARENT)
    engine = None
    if growth_backend == 'db':
        engine = create_engine(request.getfixturevalue('seeded_db').url,
                               pool_size=3, max_overflow=0, pool_timeout=2)
        monkeypatch.setattr(db, 'get_engine', lambda: engine)
    barrier = Barrier(20)
    def run(_):
        barrier.wait(timeout=10)
        try:
            getattr(backend.growth_videos, operation)(user, vid)
            return 200
        except ApiError as error:
            return error.status
    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            codes = list(pool.map(run, range(20)))
        assert codes == [200]*20 if operation == 'file' else codes.count(200) == 1 and codes.count(404) == 19
    finally:
        if engine:
            engine.dispose()


def test_failed_videos_do_not_consume_success_capacity(client, parent, monkeypatch):
    photos(client, parent)
    def fail(*args, **kwargs):
        raise ValueError('[TEST] analyzer failed')
    monkeypatch.setattr(runner, 'encode', fail)
    for _ in range(6):
        create(client, parent)
    assert all(row['status'] == 'failed' and row['failure_reason'] == 'processing_failed'
               for row in listed(client, parent))
    monkeypatch.setattr(runner, 'encode', fake_encode)
    codes = [client.post(ROOT, headers=parent, json={}).status_code for _ in range(6)]
    assert codes == [202]*5 + [409]
    assert sum(row['status'] == 'succeeded' for row in listed(client, parent)) == 5


@pytest.mark.parametrize('trigger', ['sweep', 'startup', 'worker_startup'])
def test_stale_frame_folders_are_cleaned_without_touching_recent_or_unrelated(tmp_path, monkeypatch, trigger):
    import os
    from app import main
    from fastapi.testclient import TestClient
    temp = tmp_path/'tmp'
    folders = [temp/'growth-frames-stale', temp/'growth-frames-recent', temp/'other-stale',
               tmp_path/'videos'/'growth-frames-stale']
    for folder in folders:
        folder.mkdir(parents=True)
        (folder/'frame.png').write_bytes(seed.feed_png())
    old = time.time()-3601
    for folder in (folders[0], *folders[2:]):
        os.utime(folder, (old, old))
    if trigger == 'sweep':
        assert backend.growth_videos.sweep() == 0
    else:
        from app.modules.daily_notes import runner as note_runner
        monkeypatch.setattr(note_runner, 'requeue_daily_note_drafts', lambda **kwargs: [])
        monkeypatch.setattr(jobs, 'check_broker', lambda: None)
        monkeypatch.setattr(main, 'settings', replace(jobs.settings, feature_growth_video=False,
                            data_backend='db', run_in='worker') if trigger == 'worker_startup'
                            else replace(jobs.settings, feature_growth_video=False))
        with TestClient(main.app):
            pass
    assert not folders[0].exists()
    assert all(folder.is_dir() for folder in folders[1:])


def test_real_video_succeeds_without_setpriv(client, parent, monkeypatch):
    monkeypatch.setattr(runner.shutil, 'which', lambda name: None)
    monkeypatch.setattr(runner, 'encode', REAL_ENCODE)
    photos(client, parent)
    create(client, parent)
    assert listed(client, parent)[0]['status'] == 'succeeded'


def test_forged_small_sof_cannot_bypass_decoder_pixel_limit(tmp_path, monkeypatch):
    # 가상 단색 JPEG 240MP: 작은 가짜 SOF 뒤의 진짜 SOF도 디코더에서 막아요.
    import struct
    source = tmp_path/'large.jpg'
    runner.ffmpeg(['-f', 'lavfi', '-i', 'color=c=blue:s=16000x15000', '-frames:v', '1',
                   '-threads', '1', str(source)], 20)
    data = source.read_bytes()
    pos = 2
    while pos+4 < len(data):
        length = int.from_bytes(data[pos+2:pos+4], 'big')
        if data[pos+1] == 0xc0:
            sof = bytearray(data[pos:pos+2+length])
            break
        pos += 2+length
    else:
        pytest.fail('[TEST] SOF not found')
    sof[5:9] = struct.pack('>HH', 100, 100)
    source.write_bytes(data[:2]+sof+data[2:])
    assert runner.dimensions(source.read_bytes()) == (100, 100) and runner.eligible(source)
    real_ffmpeg = runner.ffmpeg
    calls = []
    def checked(args, timeout):
        calls.append(args)
        return real_ffmpeg(args, timeout)
    monkeypatch.setattr(runner, 'ffmpeg', checked)
    assert runner.prepare(source, tmp_path/'frame.png') is False
    assert calls[0].index('-max_pixels') < calls[0].index('-i')
    assert not (tmp_path/'frame.png').exists()


@pytest.mark.parametrize('invalid', ['missing', 'too_large', 'invalid_header', 'animated'])
def test_request_metadata_rejection_releases_reserved_job(client, parent, monkeypatch, invalid):
    import struct
    photos(client, parent)
    user = backend.users.get_user(seed.PARENT)
    source = backend.growth_videos.candidates(user, seed.CHILD)[0]
    path = media.path(source['storage_path'])
    if invalid == 'missing':
        path.unlink()
    elif invalid == 'too_large':
        data = path.read_bytes()
        path.write_bytes(data[:16]+struct.pack('>II', 10000, 10000)+data[24:])
    elif invalid == 'animated':
        path.write_bytes(path.read_bytes()+struct.pack('>I', 8)+b'acTL'+b'\0'*12)
    else:
        path.write_bytes(b'\x89PNG\r\n\x1a\ninvalid')
    err(client.post(ROOT, headers=parent, json={}), 422, 'VALIDATION_FAILED')
    assert listed(client, parent) == []
    # 422 뒤 진행 중 자리가 남아 있지 않아야 해요.
    photos(client, parent)
    create(client, parent)


@pytest.mark.parametrize('status,age,expired', [('queued', 599, False), ('queued', 601, True),
                                             ('running', 359, False), ('running', 361, True)])
def test_new_request_releases_only_stale_pending_slot(client, parent, monkeypatch, growth_backend,
                                                     status, age, expired):
    from app.core.db import transaction
    photos(client, parent)
    monkeypatch.setattr(jobs, 'dispatch', lambda *args: None)
    old = UUID(create(client, parent)['id'])
    if status == 'running':
        claimed = backend.growth_videos.claim(old)
        fake_encode([1, 2, 3], media.path(claimed['storage_path']))
    else:
        # claim 이전의 일시 오류는 queued를 남겨도 다음 요청으로 회복해요.
        with monkeypatch.context() as patch:
            def failed_claim(_):
                raise ConnectionError('[TEST] claim unavailable')
            patch.setattr(backend.growth_videos, 'claim', failed_claim)
            with pytest.raises(ConnectionError):
                runner.run_growth_video(old)
    field = 'created_at' if status == 'queued' else 'started_at'
    if growth_backend == 'mock':
        store.state().growth_videos[old][field] = store.now()-timedelta(seconds=age)
    else:
        with transaction() as c:
            c.execute(text(f'UPDATE growth_videos SET {field}=now()-make_interval(secs=>:age) WHERE id=:id'),
                      {'age': age, 'id': old})
    if status == 'queued':
        assert backend.growth_videos.sweep() == 0  # 주기 점검 30분과 새 요청 10분은 달라요.
    response = client.post(ROOT, headers=parent, json={})
    rows = {r['id']: r for r in listed(client, parent)}
    if expired:
        assert response.status_code == 202, response.text
        assert response.json()['id'] != str(old) and len(rows) == 2
        assert rows[str(old)]['status'] == 'failed' and rows[str(old)]['failure_reason'] == 'stale'
        assert rows[str(old)]['completed_at'] is not None
        assert backend.growth_videos.claim(old) is None
        assert not backend.growth_videos.finish(old, {'duration_seconds': 6, 'size_bytes': 10, 'sha256': 'a'*64})
        assert sum(e['action'] == 'growth_video_completed' for e in events(growth_backend)) == 1
        if status == 'running':
            assert not media.path(claimed['storage_path']).exists()
    else:
        err(response, 409, 'CONFLICT')
        assert response.json()['error']['message'] == '만드는 중인 영상이 있어요. 끝나거나 지우면 다시 만들 수 있어요.'
        assert len(rows) == 1 and rows[str(old)]['status'] == status


@pytest.mark.parametrize('change', ['post_deleted', 'file_deleted', 'scope_revoked', 'insufficient'])
def test_job_reselects_current_photos_instead_of_request_snapshot(client, parent, parent_other, teacher,
                                                               monkeypatch, change):
    monkeypatch.setattr(jobs, 'dispatch', lambda *args: None)
    client.patch(f'{BASE}/children/{seed.demo_id("503")}/photo-scope', headers=parent_other,
                 json={'photo_scope': 'org'})
    first = photos(client, teacher, [[seed.CHILD, seed.demo_id('503')]]*3)
    remaining = photos(client, parent, [[seed.CHILD]]*(2 if change == 'insufficient' else 3))
    vid = UUID(create(client, parent, photo_limit=3)['id'])
    if change == 'scope_revoked':
        client.patch(f'{BASE}/children/{seed.demo_id("503")}/photo-scope', headers=parent_other,
                     json={'photo_scope': 'family'})
    elif change == 'file_deleted':
        source = backend.feed.file(backend.users.get_user(seed.TEACHER), UUID(first['photos'][0]['id']))
        media.remove(source['storage_path'])
    else:
        assert client.delete(f"{BASE}/posts/{first['id']}", headers=teacher).status_code == 204
    monkeypatch.setattr(runner, 'encode', REAL_ENCODE)
    runner.run_growth_video(vid)
    row = listed(client, parent)[0]
    if change == 'insufficient':
        assert row['status'] == 'failed' and row['failure_reason'] == 'not_enough_photos'
    else:
        assert row['status'] == 'succeeded' and row['failure_reason'] is None and row['photo_count'] == 3
        assert client.get(row['file_url'], headers=parent).content[4:8] == b'ftyp'
        user = backend.users.get_user(seed.PARENT)
        current = backend.growth_videos.file(user, vid)
        if 'photo_ids' in current:
            used = current['photo_ids']
        else:
            from app.core.db import transaction
            with transaction() as c:
                used = backend.growth_videos.photo_ids(c, vid)
        assert set(used) <= {UUID(p['id']) for p in first['photos']+remaining['photos']}
        assert UUID(first['photos'][0]['id']) not in used
        assert set(used) & {UUID(p['id']) for p in remaining['photos']}


def test_eligible_reads_only_first_64_kib(tmp_path, monkeypatch):
    from unittest.mock import mock_open
    source = tmp_path/'large.png'
    opened = mock_open(read_data=seed.feed_png()+b'\0'*(5*1024*1024))
    monkeypatch.setattr(type(source), 'open', opened)
    assert runner.eligible(source)
    opened.assert_called_once_with('rb')
    opened().read.assert_called_once_with(64*1024)


def test_eligible_reads_more_when_jpeg_size_header_is_after_64_kib(tmp_path):
    import struct
    app1 = b'\xff\xe1'+struct.pack('>H', 40000)+b'\0'*39998
    sof = b'\xff\xc0'+struct.pack('>HBHH', 8, 8, 600, 800)+b'\0'
    source = tmp_path/'phone.jpg'
    source.write_bytes(b'\xff\xd8'+app1+app1+sof+b'\0'*100)
    assert source.read_bytes().index(sof) > 64*1024
    assert runner.eligible(source)
    source.write_bytes(b'\xff\xd8'+app1+app1+b'\0'*100)
    assert not runner.eligible(source)


def test_listing_and_file_do_not_wait_for_child_row_lock(client, parent, growth_backend):
    if growth_backend != 'db':
        pytest.skip('[TEST] PG 행 잠금은 DB 모드에서만 검사해요.')
    from app.core.db import transaction
    photos(client, parent)
    create(client, parent)
    url = listed(client, parent)[0]['file_url']
    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction() as c:
            c.execute(text('SELECT id FROM children WHERE id=:id FOR UPDATE'), {'id': seed.CHILD})
            calls = [pool.submit(client.get, path, headers=parent) for path in (ROOT, url)]
            assert all(call.result(timeout=2).status_code == 200 for call in calls)
