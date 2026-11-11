from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone


def order(c, name='김철수', email='buyer@example.com'):
    r = c.post('/api/orders', json={'email': email, 'depositor_name': name, 'privacy_consent': True})
    assert r.status_code == 201, r.text
    return r.json()


def deposit(c, auth, name='김철수', amount=3000, when=None, source='manual'):
    return c.post('/api/deposits', headers=auth, json={
        'depositor_name': name, 'amount': amount,
        'received_at': when or datetime.now(timezone.utc).isoformat(), 'source': source,
        'raw_notification': '모의 입금 테스트',
    })


def status(c, o):
    return c.get(f"/api/orders/{o['id']}/status", headers={'Authorization': 'Bearer ' + o['status_token']})


def test_order_create_status_privacy_and_price(env, admin):
    c, store, _ = env
    o = order(c)
    assert o['amount'] == 3000
    assert status(c, o).json()['status'] == 'PENDING'
    assert c.get(f"/api/orders/{o['id']}/status").status_code == 401
    assert c.get(f"/api/orders/{o['id']}/status", headers={'Authorization': 'Bearer bad'}).status_code == 404
    assert c.patch('/api/admin/settings', headers=admin, json={'price': 5000}).status_code == 200
    assert order(c, '다른사람')['amount'] == 5000
    assert status(c, o).json()['amount'] == 3000


def test_unverified_normalized_match_never_sends(env, deposit_auth):
    c, store, _ = env
    o = order(c, ' 김 철수 ')
    r = deposit(c, deposit_auth)
    assert r.status_code == 201
    assert status(c, o).json()['status'] == 'MATCHED_UNVERIFIED'
    assert store.process_email_jobs() == 0


def test_name_and_amount_mismatches(env, deposit_auth):
    c, _, _ = env
    o = order(c)
    assert deposit(c, deposit_auth, name='홍길동').status_code == 201
    assert deposit(c, deposit_auth, amount=3001).status_code == 201
    assert status(c, o).json()['status'] == 'PENDING'


def test_ambiguous_orders_and_deposits_require_review(env, deposit_auth, admin):
    c, _, _ = env
    a, b = order(c), order(c)
    deposit(c, deposit_auth)
    assert status(c, a).json()['status'] == 'REVIEW_REQUIRED'
    assert status(c, b).json()['status'] == 'REVIEW_REQUIRED'
    ds = c.get('/api/admin/deposits', headers=admin).json()['items']
    assert ds[0]['verification_status'] == 'REVIEW_REQUIRED'


def test_duplicate_event_idempotent_and_concurrent(env, deposit_auth, admin):
    c, _, _ = env
    o = order(c)
    when = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: deposit(c, deposit_auth, when=when), range(4)))
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201]
    assert len(c.get('/api/admin/deposits', headers=admin).json()['items']) == 1
    assert status(c, o).json()['status'] == 'MATCHED_UNVERIFIED'


def test_reverse_arrival_and_expiration(env, deposit_auth):
    c, store, _ = env
    deposit(c, deposit_auth)
    o = order(c)
    assert status(c, o).json()['status'] == 'MATCHED_UNVERIFIED'
    other = order(c, '만료')
    with store.db.connect() as db:
        db.execute('UPDATE orders SET expires_at=? WHERE id=?', (0, other['id']))
    assert status(c, other).json()['status'] == 'EXPIRED'
    deposit(c, deposit_auth, name='만료')
    assert status(c, other).json()['status'] == 'EXPIRED'


def test_old_and_future_events_cannot_match(env, deposit_auth):
    c, _, _ = env
    o = order(c)
    deposit(c, deposit_auth, when=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat())
    assert status(c, o).json()['status'] == 'PENDING'
    assert deposit(c, deposit_auth, when=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat()).status_code == 422


def test_auth_validation_and_untrusted_verification_flag(env, deposit_auth):
    c, _, _ = env
    assert deposit(c, {}).status_code == 401
    assert deposit(c, {'X-API-Key': 'bad'}).status_code == 401
    assert c.get('/api/admin/orders').status_code == 401
    assert c.get('/api/admin/orders', headers=deposit_auth).status_code == 401
    for body in [
        {'email': 'bad', 'depositor_name': '김철수', 'privacy_consent': True},
        {'email': 'x@example.com', 'depositor_name': ' ', 'privacy_consent': True},
        {'email': 'x@example.com', 'depositor_name': '김철수', 'privacy_consent': False},
        {'email': 'x@example.com', 'depositor_name': '김철수', 'privacy_consent': True, 'amount': 1},
    ]:
        assert c.post('/api/orders', json=body).status_code == 422
    assert c.post('/api/deposits', headers=deposit_auth, json={
        'depositor_name': '김철수', 'amount': 3000,
        'received_at': datetime.now(timezone.utc).isoformat(), 'source': 'official_bank', 'verified': True,
    }).status_code == 422


def test_cors_body_limit_rate_limit(env):
    c, _, settings = env
    good = c.options('/api/orders', headers={'Origin': 'https://store.example.com', 'Access-Control-Request-Method': 'POST'})
    assert good.headers['access-control-allow-origin'] == 'https://store.example.com'
    bad = c.options('/api/orders', headers={'Origin': 'https://evil.example', 'Access-Control-Request-Method': 'POST'})
    assert 'access-control-allow-origin' not in bad.headers
    assert c.post('/api/orders', content='x' * 20000).status_code == 413
    settings.order_limit = 2
    order(c)
    order(c)
    assert c.post('/api/orders', json={'email': 'a@example.com', 'depositor_name': '김', 'privacy_consent': True}).status_code == 429
