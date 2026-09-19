#!/usr/bin/env bash
# 一次把本機 demo 需要的四個後端服務叫起來，並等到每一個都健康才返回。
#
# 為什麼需要這支：這四個服務全都要帶環境變數才會正確互指，靠手打的話
# 每次重開機都得重新考古一次（2026-09-19 就因為 ENGINE02_BASE_URL 指錯
# port，整條推薦鏈默默回空陣列，前端顯示成「連不到後端」查了很久）。
#
#   ./scripts/dev-up.sh          # 起四個後端
#   ./scripts/dev-up.sh --web    # 連前端 dev server 一起起
#   ./scripts/dev-down.sh        # 全部關掉
#
# 設定放在 .env（複製 .env.example 改），這支只負責把它讀進來。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/.dev"
LOG_DIR="$RUN_DIR/logs"
mkdir -p "$LOG_DIR"

if [[ -f .env ]]; then
  set -a; . ./.env; set +a
else
  echo "！找不到 .env —— 先 cp .env.example .env 再填值" >&2
  exit 1
fi

# --- python：優先用 repo 自己的 .venv，其次 .env 裡指定的 PYTHON ---------
PY="${PYTHON:-}"
if [[ -z "$PY" && -x "$ROOT/.venv/bin/python" ]]; then PY="$ROOT/.venv/bin/python"; fi
if [[ -z "$PY" ]]; then
  echo "！沒有 .venv，也沒在 .env 設 PYTHON=。" >&2
  echo "  建一個：python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi
if [[ ! -x "$PY" ]]; then echo "！PYTHON=$PY 不可執行" >&2; exit 1; fi

# --- ENGINE02 的 catalog 是本機產出的（gitignore），不在 repo 裡 ---------
: "${ENGINE02_CATALOG:?請在 .env 設 ENGINE02_CATALOG，指到含 items.parquet 的目錄}"
if [[ ! -f "$ENGINE02_CATALOG/items.parquet" ]]; then
  echo "！$ENGINE02_CATALOG 裡沒有 items.parquet" >&2
  echo "  先產生：$PY scripts/prepare_catalog.py --source Marqo/KAGL --limit 5000 --out data/catalog/kagl" >&2
  exit 1
fi

ENGINE01_PORT="${ENGINE01_PORT:-8000}"
ENGINE02_PORT="${ENGINE02_PORT:-8002}"
ENGINE03_PORT="${ENGINE03_PORT:-8003}"
BFF_PORT="${BFF_PORT:-8100}"
VIRTUAL_YOU_PORT="${VIRTUAL_YOU_PORT:-8081}"
WEB_PORT="${WEB_PORT:-3000}"

start() {  # start <名稱> <port> <health 路徑> <指令...>
  local name="$1" port="$2" health="$3"; shift 3
  local pidfile="$RUN_DIR/$name.pid"

  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "  $name 已經在跑（pid $(cat "$pidfile")）"
    return
  fi
  # 沒有 pid 檔但 port 被佔住：多半是上一輪手動起的，先清掉才不會兩份互搶。
  if lsof -ti:"$port" >/dev/null 2>&1; then
    echo "  :$port 被佔用，先關掉舊的"
    lsof -ti:"$port" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi

  ( "$@" >"$LOG_DIR/$name.log" 2>&1 & echo $! >"$pidfile" )

  for _ in $(seq 1 60); do
    if curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$port$health"; then
      echo "  $name  :$port  ok"
      return
    fi
    if ! kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      echo "！$name 啟動就掛了，看 $LOG_DIR/$name.log：" >&2
      tail -20 "$LOG_DIR/$name.log" >&2
      exit 1
    fi
    sleep 1
  done
  echo "！$name 60 秒內沒有健康，看 $LOG_DIR/$name.log" >&2
  exit 1
}

echo "python: $PY"
echo "catalog: $ENGINE02_CATALOG"
echo

# ENGINE 02（推薦）。mcp_servers.catalog.main 自己有 /health 跟 /retrieve，
# 另外把整個 engine02.api 掛在 /engine02 底下——ENGINE01 打的是後者，所以
# 這支一定要用 mcp_servers.catalog.main，不能直接跑 engine02.api。
# ENGINE02_PUBLIC_BASE 要帶 /engine02，否則回應裡組出來的圖片網址會 404。
# ENGINE02_ENCODER 預設 hash：不需要 torch，秒開。要跑真正的向量檢索品質就在
# .env 改成 marqo-fashionSigLIP，但那需要先 pip install torch（好幾 GB）。
start engine02 "$ENGINE02_PORT" /health \
  env ENGINE02_DEMO=1 \
      ENGINE02_ENCODER="${ENGINE02_ENCODER:-hash}" \
      ENGINE02_CATALOG="$ENGINE02_CATALOG" \
      ENGINE02_PUBLIC_BASE="http://localhost:$ENGINE02_PORT/engine02" \
      "$PY" -m uvicorn mcp_servers.catalog.main:app --host 127.0.0.1 --port "$ENGINE02_PORT"

# ENGINE 03（回饋）
start engine03 "$ENGINE03_PORT" /health \
  env "$PY" -m uvicorn bff.feedback.main:app --host 127.0.0.1 --port "$ENGINE03_PORT"

# ENGINE 01（意圖）。前端直接打這支的 /intent 跟 /recommend，所以 CORS 要放行
# 前端的來源。ENGINE02_BASE_URL 指的是「ENGINE02 的根」，不要帶 /engine02——
# backend/engine01_intent/engine02_client.py 自己會接上那段前綴。
start engine01 "$ENGINE01_PORT" /health \
  env DEV_BYPASS_AUTH="${DEV_BYPASS_AUTH:-false}" \
      SESSION_SECRET="${SESSION_SECRET:-}" \
      GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}" \
      CORS_ALLOWED_ORIGINS="${CORS_ALLOWED_ORIGINS:-http://localhost:3000}" \
      ENGINE02_BASE_URL="http://localhost:$ENGINE02_PORT" \
      PINTEREST_ACCESS_TOKEN="${PINTEREST_ACCESS_TOKEN:-}" \
      PINTEREST_BOARD_NAME="${PINTEREST_BOARD_NAME:-}" \
      "$PY" -m uvicorn backend.engine01_intent.main:app --host 127.0.0.1 --port "$ENGINE01_PORT"

# 生圖 BFF（前端的「AI 生成單品」打這支）
start bff "$BFF_PORT" /health \
  env CORS_ALLOWED_ORIGINS="${CORS_ALLOWED_ORIGINS:-http://localhost:3000}" \
      ENGINE01_URL="http://localhost:$ENGINE01_PORT" \
      ENGINE02_URL="http://localhost:$ENGINE02_PORT" \
      ENGINE03_URL="http://localhost:$ENGINE03_PORT" \
      "$PY" -m uvicorn bff.main:app --host 127.0.0.1 --port "$BFF_PORT"

# Virtual You（去背／試穿，main 在 2026-09-19 併進來的）。它要 rembg，那包很大，
# 沒裝就跳過——核心的 意圖→推薦→生成 這條線不需要它，不該被它擋住。前端打的是
# Next.js 的 /api/virtual-you/*，那層再轉給這支；沒起的話只有試穿功能不能用。
if "$PY" -c "import rembg" >/dev/null 2>&1; then
  start virtualyou "$VIRTUAL_YOU_PORT" /healthz \
    env PERSON_EXTRACTION_MODEL="${PERSON_EXTRACTION_MODEL:-birefnet-portrait}" \
        VIRTUAL_TRY_ON_PROVIDER="${VIRTUAL_TRY_ON_PROVIDER:-mock}" \
        VIRTUAL_TRY_ON_WORKER_URL="${VIRTUAL_TRY_ON_WORKER_URL:-}" \
        VIRTUAL_TRY_ON_TIMEOUT_SECONDS="${VIRTUAL_TRY_ON_TIMEOUT_SECONDS:-180}" \
        CODEX_BIN="${CODEX_BIN:-codex}" \
        "$PY" -m uvicorn backend.virtual_you.main:app --host 127.0.0.1 --port "$VIRTUAL_YOU_PORT"
else
  echo "  virtualyou 跳過（沒裝 rembg：$PY -m pip install rembg pillow）"
fi

if [[ "${1:-}" == "--web" ]]; then
  start web "$WEB_PORT" / \
    env npm --prefix "$ROOT/frontend" run dev -- --port "$WEB_PORT"
fi

echo
echo "後端就緒。downstream 狀態："
curl -s "http://127.0.0.1:$BFF_PORT/health"; echo
echo "log：$LOG_DIR/"
