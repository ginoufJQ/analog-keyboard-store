"""SQLite online backup, no raw copy of a live WAL database."""
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT, Settings


def backup(settings=None):
    os.umask(0o077)
    settings = settings or Settings.from_env()
    if not settings.database.is_file():
        raise SystemExit('Database not created yet; start the server first.')
    folder = ROOT / 'var/backups'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = folder / ('store-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
    with sqlite3.connect(f'file:{settings.database}?mode=ro', uri=True) as source:
        with sqlite3.connect(target) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed')
    os.chmod(target, 0o600)
    print(f'Backup verified: {target}')
    return target


if __name__ == '__main__':
    backup()
