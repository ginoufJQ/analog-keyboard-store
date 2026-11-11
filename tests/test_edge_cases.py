from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import json

import httpx
import pytest
from backend.mailer import MailFailure, Mailer
from test_store import order, deposit, status
from test_delivery import paid


def test_later_duplicate_order_invalidates_earlier_unique_match(env, deposit_auth):
    c, _, _ = env
    first = order(c)
    deposit(c, deposit_auth)
    assert status(c, first).json()['status'] == 'MATCHED_UNVERIFIED'
    second = order(c)
    assert status(c, first).json()['status'] == 'REVIEW_REQUIRED'
    assert status(c, second).json()['status'] == 'REVIEW_REQUIRED'


def test_two_distinct_simultaneous_deposits_do_not_auto_approve(env, deposit_auth, admin):
    c, store, _ = env
    o = order(c)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rs = list(pool.map(lambda seconds: deposit(c, deposit_auth, when=(now-timedelta(seconds=seconds)).isoformat()), [0,1]))
    assert [r.status_code for r in rs] == [201,201]
    assert status(c, o).json()['status'] == 'REVIEW_REQUIRED'
    assert store.process_email_jobs() == 0


def test_permanent_mail_failure_revokes_token(env, admin, deposit_auth):
    c, store, _ = env
    o, _ = paid(env, admin, deposit_auth)
    def fail(payload, key):
        raise MailFailure('REJECTED', retryable=False)
    store.mailer.send = fail
    assert store.process_email_jobs() == 0
    with store.db.connect() as db:
        j = db.execute('SELECT * FROM email_jobs').fetchone()
        t = db.execute('SELECT * FROM download_tokens').fetchone()
        assert j['status'] == 'FAILED' and j['payload_ciphertext'] is None
        assert t['revoked_at'] is not None
    assert status(c, o).json()['status'] == 'EMAIL_FAILED'


def test_retry_outside_idempotency_window_does_not_send(env, admin, deposit_auth):
    c, store, _ = env
    paid(env, admin, deposit_auth)
    def fail(payload, key):
        raise MailFailure('TEMP')
    store.mailer.send = fail
    store.process_email_jobs()
    with store.db.connect() as db:
        db.execute('UPDATE email_jobs SET first_attempt_at=1,next_attempt_at=0')
    def must_not_send(payload, key):
        pytest.fail('Expired idempotency window caused another send')
    store.mailer.send = must_not_send
    assert store.process_email_jobs() == 0
    with store.db.connect() as db:
        assert db.execute('SELECT last_error FROM email_jobs').fetchone()[0] == 'IDEMPOTENCY_WINDOW_EXPIRED'


def test_resend_http_contract_has_stable_idempotency_and_bounded_timeout(env, monkeypatch):
    _, _, settings = env
    settings.mail_mode = 'resend'
    settings.resend_key = 'local-test-only'
    seen = []
    def post(url, **kwargs):
        seen.append((url,kwargs))
        return httpx.Response(200,json={'id':'provider-message-1'})
    monkeypatch.setattr('backend.mailer.httpx.post',post)
    payload={'to':['mock@example.com'],'subject':'test','text':'test'}
    assert Mailer(settings).send(payload,'job-1') == 'provider-message-1'
    assert seen[0][0] == 'https://api.resend.com/emails'
    assert seen[0][1]['headers']['Idempotency-Key'] == 'download/job-1'
    assert seen[0][1]['timeout'] == 15


@pytest.mark.parametrize('http_status,retryable',[(400,False),(401,False),(429,True),(500,True)])
def test_provider_errors_classified_without_leaking_body(env, monkeypatch, http_status, retryable):
    _, _, settings = env
    settings.mail_mode='resend'
    monkeypatch.setattr('backend.mailer.httpx.post',lambda *a,**k:httpx.Response(http_status,text='sensitive provider text'))
    with pytest.raises(MailFailure) as err:
        Mailer(settings).send({},'job-1')
    assert err.value.retryable is retryable
    assert 'sensitive' not in err.value.code


def test_malicious_strings_are_stored_as_text_not_sql(env, admin):
    c, _, _ = env
    o=order(c,"'; DROP TABLE orders; --")
    assert status(c,o).status_code==200
    assert c.get('/api/admin/orders',headers=admin).json()['total']==1


def test_xss_is_not_rendered_with_innerhtml():
    from backend.config import ROOT
    for name in ('shop.js','admin.js','demo.js'):
        folder='pages' if name=='demo.js' else 'web'
        js=(ROOT/folder/name).read_text()
        assert '.innerHTML' not in js and 'eval(' not in js


@pytest.mark.parametrize('text', ['입금: 김철수: 3,000원\n입금: 홍길동: 5,000원', '입금: 김철수: 3,,000원'])
def test_ambiguous_or_malformed_notification_is_not_guessed(env, deposit_auth, text):
    c, _, _ = env
    assert c.post('/api/deposits/parse', headers=deposit_auth, json={'text': text}).status_code == 422
