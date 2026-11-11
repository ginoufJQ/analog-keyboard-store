from logging.handlers import RotatingFileHandler
import logging
import os
import uvicorn
from .app import create_app
from .config import ROOT


def main():
    os.umask(0o077)
    log_dir = ROOT / 'var/log'
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    handler = RotatingFileHandler(log_dir / 'server.log', maxBytes=2_000_000, backupCount=5)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # No access logs: download URL tokens must not enter local request logs.
    uvicorn.run(create_app(), host='127.0.0.1', port=8000, workers=1,
                access_log=False, proxy_headers=False, log_config=None)


if __name__ == '__main__':
    main()
