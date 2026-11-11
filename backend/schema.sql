PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, email TEXT NOT NULL, depositor_name TEXT NOT NULL,
    name_key TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
    created_at REAL NOT NULL, expires_at REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','MATCHED_UNVERIFIED','PAID_VERIFIED','SENT','EXPIRED','REVIEW_REQUIRED','REFUNDED','CANCELLED','EMAIL_FAILED')),
    paid_at REAL, sent_at REAL, status_token_hash TEXT NOT NULL,
    privacy_consent_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deposits (
    id TEXT PRIMARY KEY, depositor_name TEXT NOT NULL, name_key TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount>0), received_at REAL NOT NULL,
    ingested_at REAL NOT NULL, source TEXT NOT NULL, raw_notification TEXT NOT NULL,
    matched_order_id TEXT REFERENCES orders(id), verification_status TEXT NOT NULL,
    event_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS download_tokens (
    id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
    token_hash TEXT NOT NULL UNIQUE, expires_at REAL NOT NULL,
    download_count INTEGER NOT NULL DEFAULT 0, revoked_at REAL
);
CREATE TABLE IF NOT EXISTS email_jobs (
    id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT, sent_at REAL, created_at REAL NOT NULL,
    next_attempt_at REAL NOT NULL, first_attempt_at REAL, payload_ciphertext TEXT,
    token_id TEXT REFERENCES download_tokens(id), provider_id TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON email_jobs(order_id)
    WHERE status IN ('PENDING','RETRY','SENDING');
CREATE INDEX IF NOT EXISTS order_match ON orders(name_key, amount, status);
CREATE INDEX IF NOT EXISTS deposit_match ON deposits(name_key, amount, verification_status);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY, created_at REAL NOT NULL, action TEXT NOT NULL,
    order_id TEXT, deposit_id TEXT, note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (
    bucket TEXT PRIMARY KEY, window_start REAL NOT NULL, count INTEGER NOT NULL
);
