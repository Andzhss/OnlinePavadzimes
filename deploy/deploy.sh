#!/usr/bin/env bash
# Izvieto pavadzīmju app + MCP serveri uz Thinkpad. Dati (/opt/pavadzimes/data) netiek aiztikti.
# Pirmajā reizē:      ./deploy.sh --setup     (lietotājs, venv, systemd, tailscale serve, datu pārnese)
# Pārcelt datus vēlreiz no GitHub (pārraksta servera CSV!):  ./deploy.sh --import-data
set -euo pipefail
HOST=root@100.74.220.29
ROOT=/opt/pavadzimes
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../OnlinePavadzimes"

import_data() {
  echo "→ Jaunākie dati no GitHub"
  git -C "$HERE/.." pull --ff-only -q
  ssh "$HOST" "mkdir -p $ROOT/data/docs && stamp=\$(date +%Y%m%d-%H%M%S) && mkdir -p $ROOT/data/backup/\$stamp && cp -a $ROOT/data/*.csv $ROOT/data/backup/\$stamp/ 2>/dev/null || true"
  rsync -a "$SRC"/{invoice_history.csv,test_invoice_history.csv,clients.csv,presets.csv,credentials.json} "$HOST:$ROOT/data/"
  ssh "$HOST" "chown -R pavadzimes:pavadzimes $ROOT/data && wc -l $ROOT/data/invoice_history.csv"
}

if [[ "${1:-}" == "--setup" ]]; then
  ssh "$HOST" "id pavadzimes >/dev/null 2>&1 || useradd --system --home $ROOT --shell /sbin/nologin pavadzimes; mkdir -p $ROOT/app $ROOT/data/docs"
fi

echo "→ Kods"
rsync -a --delete --exclude __pycache__ --exclude '*.csv' --exclude credentials.json --exclude token.json \
  "$SRC/" "$HOST:$ROOT/app/"
rsync -a "$HERE"/pavadzimes.service "$HERE"/pavadzimes-mcp.service "$HERE"/pavadzimes-mcp-public.service "$HOST:/etc/systemd/system/"

if [[ "${1:-}" == "--setup" ]]; then
  ssh "$HOST" "test -d $ROOT/.venv || python3 -m venv $ROOT/.venv; $ROOT/.venv/bin/pip install -q -r $ROOT/app/requirements.txt 'mcp>=2.3,<3'"
  import_data
  ssh "$HOST" "tailscale serve --bg --https=8786 http://127.0.0.1:8786 && tailscale serve --bg --https=8787 http://127.0.0.1:8787"
elif [[ "${1:-}" == "--import-data" ]]; then
  import_data
fi

ssh "$HOST" "chown -R pavadzimes:pavadzimes $ROOT && systemctl daemon-reload && systemctl enable -q pavadzimes pavadzimes-mcp pavadzimes-mcp-public && systemctl restart pavadzimes pavadzimes-mcp pavadzimes-mcp-public && sleep 4 && curl -sf http://127.0.0.1:8787/health && echo && curl -sf -o /dev/null -w 'forma %{http_code}\n' http://127.0.0.1:8786/"
