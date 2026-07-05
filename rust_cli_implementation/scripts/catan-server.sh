#!/usr/bin/env bash
# Bring up the catanatron bridge that the Catan lens talks to.
#
# First run creates a virtualenv and installs catanatron (core only: networkx,
# click, rich). Subsequent runs just start the server. Ctrl-C to stop.
#
#   ./scripts/catan-server.sh            # 127.0.0.1:8000
#   ./scripts/catan-server.sh 0.0.0.0 9000
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
srv="$here/catan-server"
venv="$srv/.venv"
host="${1:-127.0.0.1}"
port="${2:-8000}"

if [ ! -x "$venv/bin/python" ]; then
  echo "Creating virtualenv at $venv ..."
  python3 -m venv "$venv"
fi

if ! "$venv/bin/python" -c "import catanatron" >/dev/null 2>&1; then
  echo "Installing catanatron (this happens once) ..."
  "$venv/bin/pip" install -q --upgrade pip
  "$venv/bin/pip" install -q -e "$here/catanatron"
fi

echo "Starting catanatron bridge on http://$host:$port"
echo "Leave this running, then in another terminal:  cargo run"
exec "$venv/bin/python" "$srv/app.py" "$host" "$port"
