#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

printf '%s\n' '🚀 AvalAI → OpenCode helper'

if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' '❌ Python 3 was not found in PATH.' >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
exec python3 "$PROJECT_DIR/configure.py" "$@"
