# ENGINE01 — 需求理解

一句話 → 結構化意圖 JSON（品項、顏色、場合、預算、風格關鍵字...），系統推斷的欄位跟使用者原話分開標示，意圖還太模糊、搜不出結果時會出澄清選擇題。

完整規格與設計理由：[../../docs/engine01-intent.md](../../docs/engine01-intent.md)。跨引擎 JSON 契約：[../../docs/interface-contract.md](../../docs/interface-contract.md)。

## 執行方式：`codex exec`，不用 API key

這個模組透過 OpenAI 的 Codex CLI（`codex exec --output-schema`）呼叫模型，不是用 `openai` Python SDK，所以除了你原本就有的 ChatGPT Plus/Pro 訂閱之外不會產生額外花費。為什麼這樣選、實測出來的代價（每次呼叫約 8–17 秒、吃掉團隊共用 Codex 額度約 14–20K token），見根目錄 [CLAUDE.md](../../CLAUDE.md) 的「ENGINE01 執行方式：codex exec」。

**一次性設定**，沒做這步整個模組都跑不動：

```bash
codex login
```

（這個模組不需要 `OPENAI_API_KEY`。其他引擎可能還是需要——見 CLAUDE.md。）

## 登入：Google OAuth（必須登入才能用 `/intent`）

`/intent`、`/profile` 都要求登入。需要一組 Google Cloud 的 OAuth Client ID——怎麼建見根目錄 [CLAUDE.md](../../CLAUDE.md) 的「Google OAuth Client ID」，建好後填進 `.env` 的 `GOOGLE_CLIENT_ID`，另外自己隨便生一個亂數字串填進 `SESSION_SECRET`（`python -c "import secrets; print(secrets.token_hex(32))"`）。

**還沒建 Google Client ID、只想先測後端邏輯**：`.env` 設 `DEV_BYPASS_AUTH=true`，所有端點會直接當作一個固定的本機測試使用者登入，不用走真的 Google 登入流程。**這個開關正式 demo 絕對不能開著。**

## 本機執行

從 repo 根目錄：

```bash
pip install -r backend/requirements.txt
cp .env.example .env   # 至少填 SESSION_SECRET；GOOGLE_CLIENT_ID 沒建好前先設 DEV_BYPASS_AUTH=true
uvicorn backend.engine01_intent.main:app --reload
```

`DEV_BYPASS_AUTH=true` 時試打一次（第一次呼叫會等好幾秒，見上面的延遲說明）：

```bash
curl -X POST http://127.0.0.1:8000/intent \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"我想要件簡約風格的黑色外套\"}"
```

`DEV_BYPASS_AUTH` 關掉之後，要先用真的 Google 登入拿 session token（前端會處理這步；手動測試的話要自己組一個 Google ID token 丟給 `POST /auth/google`），再把回傳的 `session_token` 帶進 `Authorization: Bearer <token>` header。

## 檔案說明

- `main.py` — FastAPI app，`POST /intent`、`POST /auth/google`、`GET /profile`、`PUT /profile`。
- `llm_client.py` — `codex exec` 結構化輸出呼叫（`extract_intent`）。
- `session_store.py` — 記憶體內的 per-`(user_id, session_id)` 對話狀態（沒有資料庫）。
- `prompts.py` — 驅動抽取／推斷／澄清問題的 system prompt。
- `tests/test_cases.json` ＋ `tests/test_accuracy.py` — 離線 slot-filling 準確率檢查（目前 10 句起始集，正式在簡報引用這個數字前要擴充到 30–50 句）。跑一次會真的打 10 次 `codex exec`（約 2–3 分鐘，會消耗一些共用額度）——沒事不要重複跑。這組測試直接呼叫 `extract_intent()`，跟登入無關。
- `../shared/auth.py` — Google ID token 驗證＋自家 session token（不在這個資料夾裡，是全 backend 共用的，見 `docs/engine01-intent.md`）。
- `../shared/user_store.py` — per-user 的 JSON 檔案存取（`data/users/<sub>.json`）。

## 離線準確率檢查

```bash
python -m backend.engine01_intent.tests.test_accuracy
```

需要先跑過一次 `codex login`（見上面）。
