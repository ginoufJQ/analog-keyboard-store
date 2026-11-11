from urllib.parse import parse_qs, urlsplit

from test_store import order


def test_payment_link_is_only_returned_after_order_and_never_in_public_config(env):
    c, store, settings = env
    settings.toss_transfer_url = 'supertoss://send?bank=test-bank&accountNo=123456&amount=1900'
    settings.payment_qr_file = settings.product_file.parent / 'transfer.png'
    settings.payment_qr_file.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
    settings.payment_qr_amount = 1900
    store.set_price(1900)
    assert 'accountNo' not in c.get('/api/config').text
    mock = order(c)
    assert mock['payment_url'] is None and mock['payment_qr_url'] is None
    settings.live_sales = True  # Test payment output only, no real transaction or mail.
    o = order(c)
    assert parse_qs(urlsplit(o['payment_url']).query)['amount'] == ['1900']
    assert o['payment_qr_url'] == f"/api/orders/{o['id']}/payment-qr"
    assert c.get(o['payment_qr_url']).status_code == 401
    assert c.get(o['payment_qr_url'], headers={'Authorization':'Bearer wrong'}).status_code == 404
    assert c.get(o['payment_qr_url'], headers={'Authorization':'Bearer '+o['status_token']}).status_code == 200


def test_changed_price_updates_toss_amount_and_hides_stale_qr(env):
    c, store, settings = env
    settings.toss_transfer_url = 'supertoss://send?bank=test-bank&accountNo=123456&amount=1900'
    settings.payment_qr_file = settings.product_file
    settings.payment_qr_amount = 1900
    settings.live_sales = True
    store.set_price(2900)
    o = order(c)
    assert parse_qs(urlsplit(o['payment_url']).query)['amount'] == ['2900']
    assert o['payment_qr_url'] is None
    with store.db.connect() as db:
        db.execute('UPDATE orders SET expires_at=0 WHERE id=?',(o['id'],))
    s=c.get(f"/api/orders/{o['id']}/status",headers={'Authorization':'Bearer '+o['status_token']}).json()
    assert s['payment_url'] is None


def test_email_first_button_has_disabled_default(env):
    c, _, _ = env
    html=c.get('/').text
    assert 'id="purchase-button"' in html and 'disabled' in html.split('id="purchase-button"',1)[1].split('>',1)[0]
    assert '이메일을 먼저 입력' in html
