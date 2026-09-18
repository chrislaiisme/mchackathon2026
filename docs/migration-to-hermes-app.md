# 搬遷對照：現有分支 → Hermes Agent 應用結構

決議：本專案以 Hermes Agent 應用的形式建置與交付（PRD 第 7 章）。這份文件列出三個進行中的分支，每個檔案要搬到哪裡、什麼要改、什麼不用改。

**先搬位置，再改呼叫方式。** 第一階段只是移動檔案，不改任何邏輯，確保搬完仍然可以跑。

## 1. engine01-intent（HoYunChen）

| 現在 | 搬到 | 說明 |
|---|---|---|
| `backend/engine01_intent/main.py` | `bff/` | FastAPI 服務改為 runtime 的端點 |
| `backend/engine01_intent/session_store.py` | `bff/` | session 狀態由 runtime 管理 |
| `backend/engine01_intent/prompts.py` | `agent/skills/intent-extractor/SKILL.md` | 提示詞政策改寫成 skill 內容 |
| `backend/engine01_intent/llm_client.py` | 由 runtime 內嵌的 Hermes Agent 取代 | 不再自行建立 LLM client |
| `backend/engine01_intent/tests/` | `evals/intent/` | 意圖準確率測試 |
| `backend/shared/schemas.py` | `contracts/` | 保留 Pydantic 形式，各模組直接 import |
| `backend/shared/auth.py`、`user_store.py` | `bff/` | 登入與使用者資料 |
| `backend/engine02_retrieval/` | `mcp_servers/catalog/` | |
| `backend/engine03_feedback/` | `bff/feedback/` | |
| `backend/generation/` | `bff/images/` | |
| `backend/pinterest/` | `mcp_servers/trends/` | |
| `backend/requirements.txt` | repo 根目錄 | |
| `docs/`、`scripts/`、`validation/` | `docs/`、`scripts/`、`evals/` | |
| `frontend/README.md` | `web/` | |
| `CLAUDE.md`、`README_TW.md`、`.env.example` | repo 根目錄 | |

## 2. engine02-research（Evan-Jiamg）

| 現在 | 搬到 | 說明 |
|---|---|---|
| `engine02/*.py`（catalog、encoders、fusion、ltr、rerank 等） | `mcp_servers/catalog/` | 檢索與排序邏輯原封不動 |
| `engine02/api.py` | `mcp_servers/catalog/` | HTTP 介面改成 MCP 工具；過渡期可先保留 HTTP，由 runtime 直接呼叫 |
| `engine02/eval/` | `evals/recommendation/` | |
| `docs/contract/*.schema.json` | `contracts/` | 與 `backend/shared/schemas.py` 擇一為準，不要兩套並存 |
| `tests/` | `mcp_servers/catalog/tests/` | |
| `reports/` | `evals/results/` | |
| `scripts/`、`pyproject.toml` | `scripts/`、repo 根目錄 | |

## 3. feature/frontend-user-ui（許綺文）

| 現在 | 搬到 | 說明 |
|---|---|---|
| `frontend/`（Next.js） | `web/` | 只改資料夾名稱，框架不動 |

前端維持 Next.js。PRD 與 `engine01-intent` 的 README 寫的是 React + Vite，以實際的 Next.js 為準，兩份文件要更新。

## 要改的四件事

1. **LLM 呼叫**：各模組不再自己接 OpenAI client；由 `bff/` 內嵌 Hermes Agent，每個端點預載一支 skill。
2. **生圖**：改走 Hermes 內建的生圖能力（選項圖的單變因保留度已實測可行）。
3. **engine02**：包成 MCP 工具服務，由 Hermes 註冊成工具。
4. **打包**：`agent/distribution.yaml` 讓整個 agent 一行指令安裝，對應「GitHub 原始碼＋英文 README 可重現」的交付要求。

## 不用改的部分

- 混合檢索與重排序的演算法
- Polyvore 資料處理流程
- 前端畫面與元件
- 驗證迴圈的設計
- Pydantic schema 的欄位定義

## 建議順序

1. 純搬移位置，不改邏輯，確認搬完還能跑。
2. `bff/` 內嵌 Hermes Agent，先只接需求理解一個端點，其餘維持原本呼叫。
3. 生圖改走 Hermes。
4. engine02 包成 MCP 工具服務。
5. `agent/` 打包與英文 README。
