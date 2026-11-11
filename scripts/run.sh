#!/bin/sh
set -eu
umask 077
TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TASK_ROOT"
exec .venv/bin/python -m backend.run
