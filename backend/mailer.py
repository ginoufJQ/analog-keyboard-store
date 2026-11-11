import json
import os
import tempfile
from pathlib import Path
import httpx


class MailFailure(Exception):
    def __init__(self, code, retryable=True):
        self.code, self.retryable = code, retryable
        super().__init__(code)


def make_payload(settings, email, token):
    template = (Path(__file__).parent / 'templates/download.txt').read_text()
    return {'from': settings.mail_from or 'mock@example.com', 'to': [email],
            'subject': ('[모의 발송] ' if settings.mail_mode == 'mock' else '') + 'Analog Keyboard Controller 다운로드 안내',
            'text': template.format(link=f'{settings.public_url}/api/download/{token}', support=settings.support_email)}


class Mailer:
    def __init__(self, settings):
        self.settings = settings

    def send(self, payload, key):
        if self.settings.mail_mode == 'mock':
            folder = self.settings.outbox_dir
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            target = folder / f'{key}.json'
            # Local mock mailbox is the mail delivery sink, outside SQLite and Git.
            if target.exists():
                try:
                    existing = json.loads(target.read_text())
                except (ValueError, UnicodeError):
                    existing = None  # Repair an incomplete pre-atomic mock mailbox file.
                if existing == payload:
                    return 'mock-' + key
                if existing is not None:
                    raise MailFailure('MOCK_PAYLOAD_MISMATCH', retryable=False)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', dir=folder, suffix='.tmp', delete=False) as f:
                    temporary = f.name
                    os.chmod(temporary, 0o600)
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary, target)
            except OSError as exc:
                raise MailFailure('MOCK_LOCAL_IO_ERROR') from exc
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
            return 'mock-' + key
        try:
            response = httpx.post('https://api.resend.com/emails', json=payload, timeout=15,
                                  headers={'Authorization': 'Bearer ' + self.settings.resend_key,
                                           'Idempotency-Key': 'download/' + key})
            if response.status_code >= 400:
                raise MailFailure(f'RESEND_HTTP_{response.status_code}', response.status_code in (408, 425, 429) or response.status_code >= 500)
            return str(response.json()['id'])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise MailFailure('RESEND_NETWORK_OR_RESPONSE_ERROR') from exc
