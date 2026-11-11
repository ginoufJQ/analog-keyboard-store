from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Settings


@pytest.fixture
def env(tmp_path):
    product = tmp_path / 'private' / 'controller.zip'
    product.parent.mkdir()
    product.write_bytes(b'private-test-product')
    settings = Settings(
        database=tmp_path / 'store.sqlite3', product_file=product,
        outbox_dir=tmp_path / 'outbox', admin_key='admin-' + 'a' * 40,
        deposit_key='deposit-' + 'b' * 40, encryption_key=Fernet.generate_key().decode(),
        public_url='http://testserver', allowed_origins=('https://store.example.com',),
        order_limit=200, worker_enabled=False, price=3000,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, app.state.store, settings


@pytest.fixture
def admin():
    return {'Authorization': 'Bearer admin-' + 'a' * 40}


@pytest.fixture
def deposit_auth():
    return {'X-API-Key': 'deposit-' + 'b' * 40}
