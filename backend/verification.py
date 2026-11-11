"""Extension boundary for a future contracted bank provider. No implementation is enabled."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VerifiedBankTransaction:
    provider: str
    transaction_id: str
    depositor_name: str
    amount: int
    received_at: datetime
    evidence_reference: str


class BankVerificationAdapter(ABC):
    @abstractmethod
    def fetch_verified_transactions(self, since: datetime) -> list[VerifiedBankTransaction]:
        """Must authenticate official bank records, not trust caller-supplied 'verified'.

        Future integration must persist UNIQUE(provider, transaction_id), compare bank
        evidence, and approve within the same transaction. No automatic approval path
        is wired until a real provider and its replay/signature tests are supplied.
        """
        raise NotImplementedError
