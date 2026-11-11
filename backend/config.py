from dataclasses import dataclass, field
from pathlib import Path
import os
from urllib.parse import urlsplit
from hashlib import sha256
import zipfile

from cryptography.fernet import Fernet
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    database: Path = ROOT / 'var/store.sqlite3'
    product_file: Path = ROOT / 'private/AnalogKeyboardController.zip'
    outbox_dir: Path = ROOT / 'var/mock-mail'
    admin_key: str = ''
    deposit_key: str = ''
    encryption_key: str = ''
    public_url: str = 'http://127.0.0.1:8000'
    allowed_origins: tuple[str, ...] = ('http://127.0.0.1:8000',)
    mail_mode: str = 'mock'
    resend_key: str = ''
    mail_from: str = ''
    support_email: str = 'support@example.com'
    bank_account: str = '모의 운영 — 실제 송금하지 마세요'
    bank_holder: str = '미설정'
    live_sales: bool = False
    worker_enabled: bool = True
    price: int = 3000
    order_hours: int = 24
    download_hours: int = 24
    order_limit: int = 10
    max_attempts: int = 5
    product_version: str = '출시 준비 중'
    supported_keyboards: str = '실제 지원 목록 확인 필요'
    operations_reviewed: bool = False
    product_sha256: str = ''

    def validate(self):
        if min(len(self.admin_key), len(self.deposit_key)) < 32 or self.admin_key == self.deposit_key:
            raise ValueError('서로 다른 32자 이상 ADMIN_API_KEY / DEPOSIT_API_KEY가 필요합니다. scripts/setup.sh 실행')
        Fernet(self.encryption_key.encode())
        if self.mail_mode not in ('mock', 'resend'):
            raise ValueError('MAIL_MODE must be mock or resend')
        parsed = urlsplit(self.public_url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError('PUBLIC_BASE_URL must be an absolute origin')
        if '*' in self.allowed_origins:
            raise ValueError('CORS wildcard is forbidden')
        if self.live_sales:
            if parsed.scheme != 'https' or not self.bank_account or any(x in self.bank_account for x in ('모의', '미설정')) or self.bank_holder == '미설정':
                raise ValueError('실판매에는 HTTPS 및 실제 계좌/예금주 설정이 필요합니다')
            if self.support_email.endswith('@example.com') or not self.product_file.is_file():
                raise ValueError('실판매에는 실제 문의 이메일과 비공개 배포 파일이 필요합니다')
            if self.mail_mode != 'resend' or not self.resend_key or not self.mail_from:
                raise ValueError('실판매에는 Resend 발신자와 키 설정이 필요합니다')
            if not self.operations_reviewed or self.product_version == '출시 준비 중' or self.supported_keyboards == '실제 지원 목록 확인 필요':
                raise ValueError('운영 정책 검토와 실제 버전/호환 키보드 설정이 필요합니다')
            if self.product_file.suffix.lower() == '.zip':
                if not zipfile.is_zipfile(self.product_file):
                    raise ValueError('유효한 ZIP 파일이 필요합니다')
                with zipfile.ZipFile(self.product_file) as package:
                    if any('MOCK-ONLY' in n for n in package.namelist()):
                        raise ValueError('MOCK 배포 파일은 실판매에 사용할 수 없습니다')
            elif self.product_file.suffix.lower() == '.exe':
                with self.product_file.open('rb') as product:
                    if product.read(2) != b'MZ':
                        raise ValueError('유효한 Windows EXE 형식이 필요합니다')
            else:
                raise ValueError('PRODUCT_FILE은 ZIP 또는 EXE여야 합니다')
            with self.product_file.open('rb') as product:
                file_digest = sha256()
                for chunk in iter(lambda: product.read(1024 * 1024), b''):
                    file_digest.update(chunk)
            if file_digest.hexdigest() != self.product_sha256:
                raise ValueError('실제 배포 파일의 PRODUCT_SHA256 확인값이 필요합니다')

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / '.env')
        return cls(
            database=Path(os.getenv('DATABASE_PATH', str(ROOT / 'var/store.sqlite3'))),
            product_file=Path(os.getenv('PRODUCT_FILE', str(ROOT / 'private/AnalogKeyboardController.zip'))),
            outbox_dir=Path(os.getenv('MOCK_MAIL_DIR', str(ROOT / 'var/mock-mail'))),
            admin_key=os.getenv('ADMIN_API_KEY', ''), deposit_key=os.getenv('DEPOSIT_API_KEY', ''),
            encryption_key=os.getenv('OUTBOX_ENCRYPTION_KEY', ''),
            public_url=os.getenv('PUBLIC_BASE_URL', 'http://127.0.0.1:8000').rstrip('/'),
            allowed_origins=tuple(x.strip() for x in os.getenv('ALLOWED_ORIGINS', 'http://127.0.0.1:8000').split(',') if x.strip()),
            mail_mode=os.getenv('MAIL_MODE', 'mock'), resend_key=os.getenv('RESEND_API_KEY', ''),
            mail_from=os.getenv('MAIL_FROM', ''), support_email=os.getenv('SUPPORT_EMAIL', 'support@example.com'),
            bank_account=os.getenv('BANK_ACCOUNT', '모의 운영 — 실제 송금하지 마세요'),
            bank_holder=os.getenv('BANK_HOLDER', '미설정'), live_sales=os.getenv('LIVE_SALES', 'false').lower() == 'true',
            worker_enabled=os.getenv('WORKER_ENABLED', 'true').lower() == 'true',
            price=int(os.getenv('PRICE_KRW', '3000')), product_version=os.getenv('PRODUCT_VERSION', '출시 준비 중'),
            supported_keyboards=os.getenv('SUPPORTED_KEYBOARDS', '실제 지원 목록 확인 필요'),
            operations_reviewed=os.getenv('OPERATIONS_REVIEWED', 'false').lower() == 'true',
            product_sha256=os.getenv('PRODUCT_SHA256', ''),
        )
