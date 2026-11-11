def test_frontend_and_demo_have_no_sensitive_content(env):
    c, _, _ = env
    assert c.get('/').status_code == 200
    assert c.get('/admin').status_code == 200
    assert c.get('/assets/style.css').status_code == 200
    assert c.get('/assets/shop.js').status_code == 200
    assert '실제 송금하지' in c.get('/').text


def test_mock_mail_requires_admin_auth(env, admin):
    c, _, _ = env
    assert c.get('/api/admin/mock-mail').status_code == 401
    assert c.get('/api/admin/mock-mail', headers=admin).json() == {'items': []}
