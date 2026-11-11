"""Create local secrets and an explicitly labelled mock package, never overwrite .env."""
import os
from pathlib import Path
import secrets
import zipfile
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]


def initialize():
    os.umask(0o077)
    for name in ('var', 'var/log', 'var/mock-mail', 'var/backups', 'private'):
        (ROOT / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    target = ROOT / '.env'
    if not target.exists():
        contents = (ROOT / '.env.example').read_text().replace(
            'ADMIN_API_KEY=GENERATE_WITH_SETUP', 'ADMIN_API_KEY=' + secrets.token_urlsafe(48)).replace(
            'DEPOSIT_API_KEY=GENERATE_WITH_SETUP', 'DEPOSIT_API_KEY=' + secrets.token_urlsafe(48)).replace(
            'OUTBOX_ENCRYPTION_KEY=GENERATE_WITH_SETUP', 'OUTBOX_ENCRYPTION_KEY=' + Fernet.generate_key().decode())
        with target.open('x') as f:
            f.write(contents)
        print('Created .env (0600). Keys are not printed.')
    os.chmod(target, 0o600)
    product = ROOT / 'private/AnalogKeyboardController.zip'
    if not product.exists():
        with zipfile.ZipFile(product, 'x') as z:
            z.writestr('MOCK-ONLY-실제프로그램아님.txt', '모의 다운로드 테스트 파일입니다. 실제 Windows 프로그램은 포함되어 있지 않습니다.\n')
        os.chmod(product, 0o600)
        print('Created MOCK-only ZIP. Replace with real tested product before live sales.')


if __name__ == '__main__':
    initialize()
