#!/bin/sh
set -eu
umask 077
TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TASK_ROOT"
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --no-cache-dir -r requirements.lock
.venv/bin/python scripts/init_local.py
.venv/bin/python scripts/build_pages.py
printf '%s\n' '설치 완료. 실행: sh scripts/run.sh / 테스트: .venv/bin/python -m pytest -q'
