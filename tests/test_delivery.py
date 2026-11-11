from concurrent.futures import ThreadPoolExecutor
import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.mailer import MailFailure
from test_store import deposit, order, status


def approve(c, admin, o, d):
    return c.post(f"/api/admin/orders/{o['id']}/approve", headers=admin,
                  json={'deposit_id': d['id'], 'bank_checked': True, 'note': '은행 거래내역 대조 완료 (모의 테스트)'})


def paid(env, admin, deposit_auth):
    c, store, settings = env
    o = order(c)
    d = deposit(c, deposit_auth).json()
    assert approve(c, admin, o, d).status_code == 200
    return o, d


def link(settings):
    payload = json.loads(next(settings.outbox_dir.glob('*.json')).read_text())
    return re.search(r'http://testserver(/api/download/\S+)', payload['text'])[1]


def test_approved_mail_and_protected_download(env, admin, deposit_auth):
    c, store, settings = env
    o, _ = paid(env, admin, deposit_auth)
    assert status(c, o).json()['status'] == 'PAID_VERIFIED'
    assert store.process_email_jobs() == 1
    assert status(c, o).json()['status'] == 'SENT'
    url = link(settings)
    r = c.get(url)
    assert r.status_code == 200 and r.content == b'private-test-product'
    assert r.headers['cache-control'] == 'no-store'
    assert c.get('/api/download/wrong').status_code == 404
    assert c.get('/private/controller.zip').status_code == 404
    with store.db.connect() as db:
        row = db.execute('SELECT * FROM download_tokens').fetchone()
        assert row['download_count'] == 1
        assert url.split('/')[-1] != row['token_hash']
        assert url.split('/')[-1].encode() not in settings.database.read_bytes()
        assert db.execute('SELECT payload_ciphertext FROM email_jobs').fetchone()[0] is None


def test_concurrent_approval_and_worker_only_one_email(env, admin, deposit_auth):
    c, store, settings = env
    o = order(c)
    d = deposit(c, deposit_auth).json()
    with ThreadPoolExecutor(max_workers=4) as pool:
        rs = list(pool.map(lambda _: approve(c, admin, o, d), range(4)))
    assert all(r.status_code == 200 for r in rs)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _: store.process_email_jobs(), range(4))) == 1
    assert len(list(settings.outbox_dir.glob('*.json'))) == 1


def test_approval_requires_bank_confirmation_and_cannot_reuse_deposit(env, admin, deposit_auth):
    c, _, _ = env
    o, d = paid(env, admin, deposit_auth)
    other = order(c)
    assert approve(c, admin, other, d).status_code == 409
    assert c.post(f"/api/admin/orders/{o['id']}/approve", headers=admin,
                  json={'deposit_id': d['id'], 'bank_checked': False, 'note': '미확인'}).status_code == 422


def test_failed_email_retry_same_link_and_idempotency_key(env, admin, deposit_auth):
    c, store, settings = env
    o, _ = paid(env, admin, deposit_auth)
    original = store.mailer.send
    attempted = []

    def fail_once(payload, key):
        attempted.append((payload, key))
        if len(attempted) == 1:
            raise MailFailure('TEST_TEMPORARY')
        return original(payload, key)

    store.mailer.send = fail_once
    assert store.process_email_jobs() == 0
    assert status(c, o).json()['status'] == 'EMAIL_FAILED'
    with store.db.connect() as db:
        row = db.execute('SELECT * FROM email_jobs').fetchone()
        assert row['status'] == 'RETRY' and row['attempts'] == 1
        assert 'api/download' not in row['payload_ciphertext']
        db.execute('UPDATE email_jobs SET next_attempt_at=0')
    assert store.process_email_jobs() == 1
    assert attempted[0] == attempted[1]
    assert c.get(link(settings)).status_code == 200


def test_process_crash_preserves_mail_payload_before_send(env, admin, deposit_auth):
    c, store, _ = env
    paid(env, admin, deposit_auth)
    attempted = []
    class SimulatedCrash(BaseException):
        pass
    original = store.mailer.send

    def crash(payload, key):
        attempted.append((payload, key))
        raise SimulatedCrash()

    store.mailer.send = crash
    with pytest.raises(SimulatedCrash):
        store.process_email_jobs()
    with store.db.connect() as db:
        row = db.execute('SELECT * FROM email_jobs').fetchone()
        assert row['payload_ciphertext'] is not None
        assert row['first_attempt_at'] is not None
    def resume(payload, key):
        attempted.append((payload, key))
        return original(payload, key)
    store.mailer.send = resume
    assert store.process_email_jobs() == 1
    assert attempted[0] == attempted[1]


def test_retry_cutoff_and_expired_link(env, admin, deposit_auth):
    c, store, settings = env
    paid(env, admin, deposit_auth)
    store.process_email_jobs()
    url = link(settings)
    with store.db.connect() as db:
        db.execute('UPDATE download_tokens SET expires_at=0')
    assert c.get(url).status_code == 404


def test_resend_revokes_previous_link_and_refund_revokes_all(env, admin, deposit_auth):
    c, store, settings = env
    o, _ = paid(env, admin, deposit_auth)
    store.process_email_jobs()
    old = link(settings)
    assert c.post(f"/api/admin/orders/{o['id']}/resend", headers=admin, json={'note': '구매자 요청 링크 재발급'}).status_code == 200
    assert c.get(old).status_code == 404
    assert store.process_email_jobs() == 1
    assert len(list(settings.outbox_dir.glob('*.json'))) == 2
    assert c.post(f"/api/admin/orders/{o['id']}/refund", headers=admin, json={'note': '실제 환불 송금 확인 기록 (모의)'}).status_code == 200
    assert status(c, o).json()['status'] == 'REFUNDED'
    assert c.post(f"/api/admin/orders/{o['id']}/resend", headers=admin, json={'note': '재발송'}).status_code == 409


def test_cancel_and_csv_formula_protection(env, admin):
    c, store, _ = env
    o = order(c, '=HYPERLINK("evil")')
    r = c.get('/api/admin/export.csv', headers=admin)
    assert r.status_code == 200 and "'=HYPERLINK" in r.text
    assert c.post(f"/api/admin/orders/{o['id']}/cancel", headers=admin, json={'note': '구매자 취소 요청'}).status_code == 200
    assert status(c, o).json()['status'] == 'CANCELLED'


def test_database_persists_across_app_restart(env, deposit_auth):
    c, _, settings = env
    o = order(c)
    with TestClient(create_app(settings)) as new:
        assert status(new, o).json()['status'] == 'PENDING'
        deposit(new, deposit_auth)
        assert status(new, o).json()['status'] == 'MATCHED_UNVERIFIED'


def test_notify_parser_is_explicit_and_never_verifies(env, deposit_auth):
    c, _, _ = env
    parsed = c.post('/api/deposits/parse', headers=deposit_auth, json={'text': '입금: 김철수: 3,000원'})
    assert parsed.json() == {'depositor_name': '김철수', 'amount': 3000, 'requires_confirmation': True}
    assert c.post('/api/deposits/parse', headers=deposit_auth, json={'text': '잔액 100,000원'}).status_code == 422
