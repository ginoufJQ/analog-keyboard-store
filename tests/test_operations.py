from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import plistlib
import sqlite3
import zipfile

import pytest
from backend.mailer import Mailer
from backend.config import ROOT


def test_live_refuses_mock_account_product_and_unreviewed_policies(env, tmp_path):
    _, _, settings = env
    mockzip = tmp_path / 'mock.zip'
    with zipfile.ZipFile(mockzip, 'w') as z:
        z.writestr('MOCK-ONLY-not-a-product.txt', 'test')
    live = replace(settings, live_sales=True, public_url='https://store.example.com',
                   support_email='support@developer.test', mail_mode='resend', resend_key='test-key',
                   mail_from='support@developer.test', bank_holder='판매자', product_file=mockzip)
    with pytest.raises(ValueError):
        live.validate()
    # Even if all ordinary live settings are supplied, the mock artifact is blocked.
    live = replace(live, bank_account='토스뱅크 1000-1234-5678', product_version='1.0.0',
                   supported_keyboards='실제 확인한 모델', operations_reviewed=True,
                   product_sha256=sha256(mockzip.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match='MOCK'):
        live.validate()


def test_live_requires_matching_explicit_product_hash(env, tmp_path):
    _, _, settings = env
    product = tmp_path / 'example.exe'
    product.write_bytes(b'MZ-fixture-only-not-real-product')
    live = replace(settings, live_sales=True, public_url='https://store.example.com',
                   support_email='support@developer.test', mail_mode='resend', resend_key='test-key',
                   mail_from='support@developer.test', bank_holder='판매자', product_file=product,
                   bank_account='토스뱅크 1000-1234-5678', product_version='1.0.0',
                   supported_keyboards='확인한 모델', operations_reviewed=True, product_sha256='0'*64)
    with pytest.raises(ValueError):
        live.validate()
    replace(live, product_sha256=sha256(product.read_bytes()).hexdigest()).validate()


def test_mock_mail_repairs_partial_file_atomically(env):
    _, _, settings = env
    settings.outbox_dir.mkdir()
    path = settings.outbox_dir / 'test-key.json'
    path.write_text('{')
    mailer = Mailer(settings)
    payload = {'to':['mock@example.com'],'subject':'test','text':'body'}
    assert mailer.send(payload, 'test-key') == 'mock-test-key'
    assert json.loads(path.read_text()) == payload
    assert len(list(settings.outbox_dir.iterdir())) == 1


def test_backup_restores_consistent_database(env):
    from scripts.backup import backup
    _, store, settings = env
    target = backup(settings)
    try:
        with sqlite3.connect(target) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert db.execute("SELECT value FROM settings WHERE key='price'").fetchone()[0] == '3000'
    finally:
        target.unlink()


def test_launchd_generated_files_have_loopback_runner_and_restart():
    from scripts.generate_launchd import generate
    generate()
    obj = plistlib.loads((ROOT / 'deploy/generated/com.analog.store.plist').read_bytes())
    assert obj['KeepAlive'] is True and obj['RunAtLoad'] is True
    assert obj['ProgramArguments'][-2:] == ['-m','backend.run']
    backup = plistlib.loads((ROOT / 'deploy/generated/com.analog.store.backup.plist').read_bytes())
    assert backup['StartCalendarInterval'] == {'Hour':4,'Minute':15}


def test_pages_artifact_isolated_from_real_storefront():
    from scripts.build_pages import build
    build()
    assert {p.name for p in (ROOT/'dist').iterdir()} == {'index.html','demo.js','style.css','.nojekyll'}
    html=(ROOT/'dist/index.html').read_text()
    js=(ROOT/'dist/demo.js').read_text()
    assert '<input' not in html and '<form' not in html
    assert 'fetch(' not in js and '/api/' not in js and 'localStorage' not in js
    assert '실제 주문·입금·메일 발송 없음' in html
