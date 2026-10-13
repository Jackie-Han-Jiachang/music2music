#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to this script, even when launched from another folder.
project_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

if ! command -v uv >/dev/null 2>&1; then
    printf '%s\n' 'uv is required. Install it using https://docs.astral.sh/uv/getting-started/installation/' >&2
    exit 1
fi

if [[ ! -f uv.lock || ! -f 'flask+ninja2/n2s.py' ]]; then
    printf '%s\n' 'The project archive is incomplete. Extract a newly built source archive and try again.' >&2
    exit 1
fi

uv sync --locked
printf '\nOpen http://localhost:%s in your browser. Press Ctrl+C to stop.\n\n' "${PORT:-8888}"
exec uv run --locked --no-sync python 'flask+ninja2/n2s.py'
