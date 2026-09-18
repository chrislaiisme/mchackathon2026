# 搬遷對照：現有分支 → Hermes Agent 應用結構

> **這條分支的定位（2026-09-18 決議）**
>
> 比賽前一晚不改動 `main`。`main` 維持原本的結構（`backend/`、`frontend/`、`validation/`），
> 三位分支作者照常開發，**不需要 rebase，也不需要搬任何檔案**。
>
> Hermes Agent 應用的結構與三方整合的結果只存在於 `integration/hermes-app`，**demo 從這條分支跑**。
> 大家推新 commit 之後，這條分支重新合併一次即可。結構要不要併回 `main`，賽後再決定
> （原本的 PR #2 已關閉）。

決議：本專案以 Hermes Agent 應用的形式建置與交付（PRD 第 7 章）。這份文件列出三個進行中的分支，每個檔案要搬到哪裡、什麼要改、什麼不用改。

**先搬位置，再改呼叫方式。** 第一階段只移動檔案、不改邏輯。

## 目前進度

| 階段 | 狀態 |
|---|---|
| 1. 搬移位置（`main` 上已合併的 engine01 程式） | ✅ 已在本 PR 完成，import 路徑同步更新，語法檢查通過 |
| 2. `bff/` 內嵌 Hermes Agent，先接需求理解一個端點 | 待做 |
| 3. 生圖改走 Hermes | 待做 |
| 4. engine02 包成 MCP 工具服務 | 待做（等 `engine02-research` 合併） |
| 5. `agent/` 打包與英文 README | 待做 |

整合在 `integration/hermes-app` 分支上進行，**不需要動到任何人的分支**。分支作者照常在自己的分支開發，整合分支會定期重新合併。

## 1. engine01-intent（HoYunChen）— ✅ 已完成

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

## 2. engine02-research（Evan-Jiamg）— ✅ 已整合（package 維持原位）

| 現在 | 搬到 | 說明 |
|---|---|---|
| `engine02/*.py` | **維持在根目錄不搬** | 是 Python package，多處絕對 import 與 `pyproject.toml` 依賴它的位置；`mcp_servers/catalog/` 放 MCP 包裝層去 import 它 |
| `engine02/api.py` | 維持原位 | HTTP 介面保留；MCP 包裝層在 `mcp_servers/catalog/` |
| `engine02/eval/` | 維持原位 | 屬於 package 的一部分 |
| `docs/contract/*.schema.json` | `contracts/` | 與 `backend/shared/schemas.py` 擇一為準，不要兩套並存 |
| `tests/`、`reports/`、`docs/contract/` | 維持原位 | 被 `pyproject.toml`、程式與文件引用 |

| `scripts/`、`pyproject.toml` | `scripts/`、repo 根目錄 | |

## 3. feature/frontend-user-ui（許綺文）— ✅ 已完成

| 現在 | 搬到 | 說明 |
|---|---|---|
| `frontend/`（Next.js） | `web/` | ✅ 已在整合分支完成，框架不動 |

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
