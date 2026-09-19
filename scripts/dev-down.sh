#!/usr/bin/env bash
# 關掉 dev-up.sh 起的所有服務。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/.dev"

shopt -s nullglob
for pidfile in "$RUN_DIR"/*.pid; do
  name="$(basename "$pidfile" .pid)"
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    # uvicorn / npm 會開子行程，整個 process group 一起收掉才不會留孤兒。
    kill -TERM -- "-$(ps -o pgid= "$pid" | tr -d ' ')" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    echo "  停掉 ${name}（pid ${pid}）"
  fi
  rm -f "$pidfile"
done
echo "關完了。"
