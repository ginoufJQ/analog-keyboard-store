"""Transactional matching. Incoming notifications never become verified payments."""
from hashlib import sha256
import json
import secrets
import sqlite3
import time
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi import HTTPException

from .db import Database
from .models import normalize_name


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def uid() -> str:
    return uuid4().hex


class Store:
    def __init__(self, settings, mailer):
        self.settings = settings
        self.db = Database(settings.database)
        self.mailer = mailer
        self.cipher = Fernet(settings.encryption_key.encode())
        with self.db.transaction() as db:
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('price', str(settings.price)))

    def config(self):
        with self.db.connect() as db:
            price = int(db.execute("SELECT value FROM settings WHERE key='price'").fetchone()[0])
        return {'price': price, 'mode': 'live' if self.settings.live_sales else 'mock',
                'version': self.settings.product_version, 'supported_keyboards': self.settings.supported_keyboards,
                'support_email': self.settings.support_email, 'order_hours': self.settings.order_hours,
                'download_hours': self.settings.download_hours}

    def rate_limit(self, bucket, maximum, window=3600):
        now = time.time()
        with self.db.transaction() as db:
            db.execute('DELETE FROM rate_limits WHERE window_start<?', (now - 86400,))
            row = db.execute('SELECT * FROM rate_limits WHERE bucket=?', (bucket,)).fetchone()
            if not row or now - row['window_start'] >= window:
                db.execute('INSERT OR REPLACE INTO rate_limits VALUES (?,?,1)', (bucket, now))
            elif row['count'] >= maximum:
                raise HTTPException(429, '요청이 많습니다. 잠시 후 다시 시도하세요.', headers={'Retry-After': str(window)})
            else:
                db.execute('UPDATE rate_limits SET count=count+1 WHERE bucket=?', (bucket,))

    def _expire(self, db):
        db.execute("UPDATE orders SET status='EXPIRED' WHERE expires_at<? AND status IN ('PENDING','MATCHED_UNVERIFIED','REVIEW_REQUIRED')", (time.time(),))

    def _match(self, db):
        self._expire(db)
        orders = db.execute("SELECT * FROM orders WHERE status IN ('PENDING','MATCHED_UNVERIFIED','REVIEW_REQUIRED')").fetchall()
        deposits = db.execute("SELECT * FROM deposits WHERE verification_status!='VERIFIED'").fetchall()
        edges = {o['id']: [d for d in deposits if o['name_key'] == d['name_key'] and o['amount'] == d['amount']
                           and o['created_at'] - 900 <= d['received_at'] <= o['expires_at']] for o in orders}
        counts = {d['id']: sum(any(x['id'] == d['id'] for x in ds) for ds in edges.values()) for d in deposits}
        # Re-evaluate every unverified edge: later duplicate orders/events invalidate a formerly unique match.
        for d in deposits:
            db.execute("UPDATE deposits SET matched_order_id=NULL, verification_status='UNVERIFIED' WHERE id=?", (d['id'],))
        for o in orders:
            candidates = edges[o['id']]
            if not candidates:
                state = 'PENDING'
            elif len(candidates) == 1 and counts[candidates[0]['id']] == 1:
                state = 'MATCHED_UNVERIFIED'
                db.execute("UPDATE deposits SET matched_order_id=?, verification_status='MATCHED_UNVERIFIED' WHERE id=?", (o['id'], candidates[0]['id']))
            else:
                state = 'REVIEW_REQUIRED'
                for d in candidates:
                    db.execute("UPDATE deposits SET matched_order_id=NULL, verification_status='REVIEW_REQUIRED' WHERE id=?", (d['id'],))
            db.execute('UPDATE orders SET status=? WHERE id=?', (state, o['id']))

    def create_order(self, data):
        now, token, order_id = time.time(), secrets.token_urlsafe(32), uid()
        with self.db.transaction() as db:
            price = int(db.execute("SELECT value FROM settings WHERE key='price'").fetchone()[0])
            db.execute('INSERT INTO orders (id,email,depositor_name,name_key,amount,created_at,expires_at,status,status_token_hash,privacy_consent_at) VALUES (?,?,?,?,?,?,?,\'PENDING\',?,?)',
                       (order_id, str(data.email), data.depositor_name, normalize_name(data.depositor_name), price,
                        now, now + self.settings.order_hours * 3600, digest(token), now))
            self._match(db)
        return {'id': order_id, 'status_token': token, 'amount': price, 'expires_at': now + self.settings.order_hours * 3600,
                'bank_account': self.settings.bank_account if self.settings.live_sales else '모의 운영 — 실제 송금하지 마세요',
                'bank_holder': self.settings.bank_holder if self.settings.live_sales else '모의 예금주'}

    def order_status(self, order_id, token):
        with self.db.transaction() as db:
            self._expire(db)
            row = db.execute('SELECT id,status,amount,created_at,expires_at,paid_at,sent_at FROM orders WHERE id=? AND status_token_hash=?', (order_id, digest(token))).fetchone()
            if not row:
                raise HTTPException(404, '주문을 확인할 수 없습니다')
            return dict(row)

    def receive_deposit(self, data):
        payload = [normalize_name(data.depositor_name), data.amount, data.received_at.timestamp(), data.source]
        fingerprint = digest(json.dumps(payload, ensure_ascii=False))
        with self.db.transaction() as db:
            existing = db.execute('SELECT * FROM deposits WHERE event_fingerprint=?', (fingerprint,)).fetchone()
            if existing:
                return dict(existing), False
            deposit_id = uid()
            db.execute('INSERT INTO deposits VALUES (?,?,?,?,?,?,?,?,NULL,?,?)',
                       (deposit_id, data.depositor_name, normalize_name(data.depositor_name), data.amount,
                        data.received_at.timestamp(), time.time(), data.source, data.raw_notification, 'UNVERIFIED', fingerprint))
            self._match(db)
            return dict(db.execute('SELECT * FROM deposits WHERE id=?', (deposit_id,)).fetchone()), True

    def list_rows(self, table, limit=100, offset=0, status=None):
        assert table in ('orders', 'deposits', 'email_jobs', 'audit_log')
        with self.db.transaction() as db:
            self._expire(db)
            where, params = '', []
            if status and table == 'orders':
                where, params = ' WHERE status=?', [status]
            total = db.execute(f'SELECT count(*) FROM {table}{where}', params).fetchone()[0]
            sort = 'received_at' if table == 'deposits' else 'created_at'
            columns = '*' if table != 'orders' else 'id,email,depositor_name,amount,created_at,expires_at,status,paid_at,sent_at'
            if table == 'email_jobs':
                columns = 'id,order_id,status,attempts,last_error,sent_at,created_at,next_attempt_at'
            rows = db.execute(f'SELECT {columns} FROM {table}{where} ORDER BY {sort} DESC LIMIT ? OFFSET ?', [*params, limit, offset]).fetchall()
            return {'items': [dict(r) for r in rows], 'total': total, 'offset': offset, 'limit': limit}

    def _audit(self, db, action, order_id=None, deposit_id=None, note=''):
        db.execute('INSERT INTO audit_log(created_at,action,order_id,deposit_id,note) VALUES (?,?,?,?,?)', (time.time(), action, order_id, deposit_id, note))

    def approve(self, order_id, data):
        with self.db.transaction() as db:
            self._expire(db)
            o = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            d = db.execute('SELECT * FROM deposits WHERE id=?', (data.deposit_id,)).fetchone()
            if not o or not d:
                raise HTTPException(404, '주문 또는 입금이 없습니다')
            if o['paid_at']:
                if d['matched_order_id'] == order_id and d['verification_status'] == 'VERIFIED' and o['status'] not in ('REFUNDED', 'CANCELLED'):
                    return {'status': o['status'], 'already_approved': True}
                raise HTTPException(409, '이미 처리된 주문입니다')
            if o['status'] in ('EXPIRED', 'CANCELLED', 'REFUNDED') or d['verification_status'] == 'VERIFIED':
                raise HTTPException(409, '만료·취소·사용된 주문/입금입니다')
            if d['amount'] != o['amount']:
                raise HTTPException(409, '입금액이 주문액과 다릅니다')
            db.execute("UPDATE deposits SET matched_order_id=?, verification_status='VERIFIED' WHERE id=?", (order_id, d['id']))
            db.execute("UPDATE orders SET status='PAID_VERIFIED', paid_at=? WHERE id=?", (time.time(), order_id))
            self._queue(db, order_id)
            self._audit(db, 'MANUAL_BANK_APPROVAL', order_id, d['id'], data.note)
            self._match(db)
            return {'status': 'PAID_VERIFIED'}

    def _queue(self, db, order_id):
        now = time.time()
        db.execute('INSERT INTO email_jobs(id,order_id,status,created_at,next_attempt_at) VALUES (?, ?,\'PENDING\',?,?)', (uid(), order_id, now, now))

    def resend(self, order_id, note):
        with self.db.transaction() as db:
            o = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            if not o:
                raise HTTPException(404, '주문이 없습니다')
            if not o['paid_at'] or o['status'] in ('CANCELLED', 'REFUNDED'):
                raise HTTPException(409, '승인된 주문만 재발급할 수 있습니다')
            if db.execute("SELECT 1 FROM email_jobs WHERE order_id=? AND status IN ('PENDING','RETRY','SENDING')", (order_id,)).fetchone():
                raise HTTPException(409, '메일 작업이 진행 중입니다. 자동 재시도를 기다리세요')
            db.execute('UPDATE download_tokens SET revoked_at=? WHERE order_id=? AND revoked_at IS NULL', (time.time(), order_id))
            self._queue(db, order_id)
            db.execute("UPDATE orders SET status='PAID_VERIFIED' WHERE id=?", (order_id,))
            self._audit(db, 'REISSUE_EMAIL', order_id, note=note)
        return {'status': 'QUEUED'}

    def close_order(self, order_id, action, note):
        with self.db.transaction() as db:
            o = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            if not o:
                raise HTTPException(404, '주문이 없습니다')
            if action == 'CANCELLED' and o['paid_at']:
                raise HTTPException(409, '승인 후에는 실제 환불 확인 후 환불 처리하세요')
            if action == 'REFUNDED' and not o['paid_at']:
                raise HTTPException(409, '승인되지 않은 주문입니다')
            db.execute('UPDATE orders SET status=? WHERE id=?', (action, order_id))
            db.execute('UPDATE download_tokens SET revoked_at=? WHERE order_id=?', (time.time(), order_id))
            db.execute("UPDATE email_jobs SET status='CANCELLED', payload_ciphertext=NULL WHERE order_id=? AND status IN ('PENDING','RETRY','SENDING')", (order_id,))
            self._audit(db, action, order_id, note=note)
            self._match(db)
        return {'status': action}

    def set_price(self, price):
        with self.db.transaction() as db:
            db.execute("UPDATE settings SET value=? WHERE key='price'", (str(price),))
            self._audit(db, 'SET_PRICE', note=str(price))
        return self.config()

    def process_email_jobs(self, limit=5):
        from .mailer import make_payload, MailFailure
        completed = 0
        for _ in range(limit):
            # Persist the encrypted immutable payload BEFORE the network side effect.
            # If the process dies after Resend accepts it, a restart sends the same
            # body and idempotency key; the original token still exists in SQLite.
            with self.db.transaction() as db:
                now = time.time()
                job = db.execute("SELECT * FROM email_jobs WHERE status IN ('PENDING','RETRY') AND next_attempt_at<=? ORDER BY created_at LIMIT 1", (now,)).fetchone()
                if not job:
                    break
                o = db.execute('SELECT * FROM orders WHERE id=?', (job['order_id'],)).fetchone()
                if not o['paid_at'] or o['status'] in ('CANCELLED', 'REFUNDED'):
                    db.execute("UPDATE email_jobs SET status='CANCELLED', payload_ciphertext=NULL WHERE id=?", (job['id'],))
                    continue
                if job['first_attempt_at'] and now - job['first_attempt_at'] >= 23 * 3600:
                    db.execute("UPDATE email_jobs SET status='FAILED',last_error='IDEMPOTENCY_WINDOW_EXPIRED',payload_ciphertext=NULL WHERE id=?", (job['id'],))
                    db.execute("UPDATE orders SET status='EMAIL_FAILED' WHERE id=?", (o['id'],))
                    if job['token_id']:
                        db.execute('UPDATE download_tokens SET revoked_at=? WHERE id=?', (now, job['token_id']))
                    continue
                if job['payload_ciphertext']:
                    payload = json.loads(self.cipher.decrypt(job['payload_ciphertext'].encode()))
                    token_id = job['token_id']
                else:
                    token, token_id = secrets.token_urlsafe(32), uid()
                    db.execute('INSERT INTO download_tokens(id,order_id,token_hash,expires_at) VALUES (?,?,?,?)', (token_id, o['id'], digest(token), now + self.settings.download_hours * 3600))
                    payload = make_payload(self.settings, o['email'], token)
                    encrypted = self.cipher.encrypt(json.dumps(payload, ensure_ascii=False).encode()).decode()
                    db.execute('UPDATE email_jobs SET payload_ciphertext=?,token_id=?,first_attempt_at=? WHERE id=?', (encrypted, token_id, now, job['id']))
                job_id = job['id']
            # Serialize workers and cancellation across the bounded (15s) send.
            # A second worker may have selected this same prepared job: recheck it.
            with self.db.transaction() as db:
                job = db.execute('SELECT * FROM email_jobs WHERE id=?', (job_id,)).fetchone()
                if job['status'] not in ('PENDING', 'RETRY') or job['next_attempt_at'] > time.time():
                    continue
                o = db.execute('SELECT * FROM orders WHERE id=?', (job['order_id'],)).fetchone()
                if not o['paid_at'] or o['status'] in ('CANCELLED', 'REFUNDED'):
                    continue
                now = time.time()
                payload = json.loads(self.cipher.decrypt(job['payload_ciphertext'].encode()))
                token_id = job['token_id']
                attempts = job['attempts'] + 1
                db.execute("UPDATE email_jobs SET status='SENDING',attempts=? WHERE id=?", (attempts, job['id']))
                try:
                    provider_id = self.mailer.send(payload, job['id'])
                except MailFailure as exc:
                    failed = attempts >= self.settings.max_attempts or not exc.retryable
                    db.execute('UPDATE email_jobs SET status=?,last_error=?,next_attempt_at=? WHERE id=?',
                               ('FAILED' if failed else 'RETRY', exc.code, now + min(60 * 2 ** (attempts - 1), 3600), job['id']))
                    db.execute("UPDATE orders SET status='EMAIL_FAILED' WHERE id=?", (o['id'],))
                    if failed:
                        db.execute('UPDATE download_tokens SET revoked_at=? WHERE id=?', (now, token_id))
                        db.execute('UPDATE email_jobs SET payload_ciphertext=NULL WHERE id=?', (job['id'],))
                else:
                    db.execute("UPDATE email_jobs SET status='SENT',sent_at=?,last_error=NULL,payload_ciphertext=NULL,provider_id=? WHERE id=?", (time.time(), provider_id, job['id']))
                    db.execute("UPDATE orders SET status='SENT',sent_at=? WHERE id=?", (time.time(), o['id']))
                    self._audit(db, 'EMAIL_ACCEPTED', o['id'], note=self.settings.mail_mode)
                    completed += 1
        return completed

    def download(self, token):
        if not self.settings.product_file.is_file():
            raise HTTPException(503, '배포 파일 준비 중입니다. 관리자에게 문의하세요')
        with self.db.transaction() as db:
            row = db.execute('SELECT t.*,o.status FROM download_tokens t JOIN orders o ON o.id=t.order_id WHERE token_hash=?', (digest(token),)).fetchone()
            if not row or row['revoked_at'] or row['expires_at'] <= time.time() or row['status'] not in ('PAID_VERIFIED', 'SENT', 'EMAIL_FAILED'):
                raise HTTPException(404, '만료되었거나 유효하지 않은 링크입니다')
            db.execute('UPDATE download_tokens SET download_count=download_count+1 WHERE id=?', (row['id'],))
        return self.settings.product_file
