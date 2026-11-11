from datetime import datetime, timezone, timedelta
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def normalize_name(value: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', value).split()).casefold()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class OrderInput(StrictModel):
    email: EmailStr = Field(max_length=254)
    depositor_name: str = Field(min_length=1, max_length=50)
    privacy_consent: Literal[True]

    @field_validator('depositor_name')
    @classmethod
    def valid_name(cls, value):
        if not normalize_name(value) or any(unicodedata.category(c).startswith('C') for c in value):
            raise ValueError('입금자명을 확인하세요')
        return value.strip()


class DepositInput(StrictModel):
    depositor_name: str = Field(min_length=1, max_length=50)
    amount: int = Field(gt=0, le=100_000_000, strict=True)
    received_at: datetime
    source: Literal['manual', 'shortcut_manual', 'toss_notification', 'sms', 'email', 'mock'] = 'manual'
    raw_notification: str = Field(default='', max_length=2000)
    valid_name = field_validator('depositor_name')(OrderInput.valid_name.__func__)

    @field_validator('received_at')
    @classmethod
    def valid_time(cls, value):
        if value.tzinfo is None or value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('시간대가 있는 실제 입금 시각을 입력하세요')
        return value.astimezone(timezone.utc).replace(microsecond=0)


class ApprovalInput(StrictModel):
    deposit_id: str = Field(min_length=1, max_length=64)
    bank_checked: Literal[True]
    note: str = Field(min_length=3, max_length=500)


class NoteInput(StrictModel):
    note: str = Field(min_length=3, max_length=500)


class PriceInput(StrictModel):
    price: int = Field(gt=0, le=100_000_000, strict=True)


class ParseInput(StrictModel):
    text: str = Field(min_length=1, max_length=2000)


def parse_notification(text: str) -> dict:
    """Accept an explicit, documented format; never guess unknown Toss formats."""
    match = re.search(r'입금\s*[:：]\s*(?P<name>[^\n:：]+?)\s*[:：]\s*(?P<amount>[\d,]+)\s*원', text)
    if not match:
        raise ValueError('지원 형식: 입금: 김철수: 3,000원. 실제 알림 형식은 직접 확인 후 입력하세요.')
    return {'depositor_name': match['name'].strip(), 'amount': int(match['amount'].replace(',', '')), 'requires_confirmation': True}
