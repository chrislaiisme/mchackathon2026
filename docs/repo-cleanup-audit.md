# Repo 冗餘檔案盤點

一次性盤點「現在這條 demo 用不到、可能可以刪或整併」的東西。**這份文件只列清單、標判斷依據，不代表已經執行任何刪除**——凡是牽涉到其他組員負責的資料夾（ENGINE02、Hermes app 遷移分支），一律先列出來，動手前要跟對應負責人確認。

最後盤點：2026-09-20，方法是讀程式碼 import 關係、`git log`、`git ls-files`、`diff -rq` 實測比對，不是憑印象或猜測。

## 分類說明

- **確定死碼**：repo 內沒有任何程式碼引用，功能已被別的路徑取代。
- **已分岔的重複目錄**：本來應該是同一份，現在內容不一樣了，需要決定哪一份是真相來源。
- **平行技術棧占位（非死碼）**：`CLAUDE.md` 已經說明是刻意保留給 `integration/hermes-app` 分支的東西，不要誤判成可刪。
- **孤兒／過時文件**：文件本身還在，但沒有任何地方連結它，或內容已經被別份文件取代。
- **不確定，交給團隊判斷**：有理由懷疑用不到了，但無法 100% 排除還有人在用。

## 確定死碼

| 路徑 | 說明 | 證據 |
|---|---|---|
| `backend/generation/` | 只有一份規劃階段的 `README.md`，完全沒有 `.py` 檔 | repo 內 grep `backend.generation`／`backend/generation`／`from backend import generation` 全部零命中；實際生圖走 `bff/images/concept.py::generate_concepts()` → `agent/scripts/generate_grid.py`／`slice_grid.py`，跟這個資料夾完全無關 |
| `scripts/patch_e01_stub.py` | 一次性 patch 工具：把「沒裝 `codex`」的 stub 邏輯注入**另一個 worktree**的 `bff/engine01_intent/llm_client.py`，用來在沒裝 `codex` 的 GPU 伺服器上測試 | repo 內零引用，不屬於任何文件化流程 |

**建議**：`backend/generation/` 可以直接刪除，同時修正 `CLAUDE.md`／`AGENTS.md` 模組表，把「生成模組」欄位的資料夾改指向 `bff/images/concept.py` ＋ `agent/scripts/`（已在本次文件更新裡一併修正）。`scripts/patch_e01_stub.py` 屬於一次性開發工具，確認沒有人還在用「沒裝 codex 的 GPU 伺服器」這個測試路徑後可以刪除。

## 已分岔的重複目錄

| 路徑 | 說明 | 證據 |
|---|---|---|
| `backend/engine02_retrieval/` vs `mcp_servers/catalog/` | `CLAUDE.md`、`docs/engine02-retrieval.md` 都寫「這兩份逐位元組相同」，**這個說法已經不成立** | `diff -rq` 實測：兩邊 `main.py`、`README.md` 都不一樣。`mcp_servers/catalog/main.py` 多 try `bff.shared.auth`（`backend/engine02_retrieval/main.py` 只 try `backend.shared.auth`）；`mcp_servers/catalog/README.md` 有 `/engine02` 掛載路徑修正、`ENGINE02_CATALOG=hm_filled` 修正等較新內容，`backend/engine02_retrieval/README.md` 是舊版原文 |

**現場真正在跑的是哪一份**：`mcp_servers/catalog/`——`scripts/start-demo.ps1` 直接執行 `mcp_servers.catalog.main:app`，`CLAUDE.md`「環境備註」的官方啟動指令也是這一份。

**`backend/engine02_retrieval/` 不是完全孤立**：`scripts/simulate_sessions.py`、`tests/test_intent_adapter.py` 都寫了「先 import `mcp_servers.catalog`，失敗才退回 `backend.engine02_retrieval`」的 fallback，是刻意保留給只有舊版目錄結構的 checkout 用的相容路徑，不是意外殘留的死碼。

**建議**：跟 ENGINE02 負責人（Evan-Jiamg）確認：(a) 是否要把 `backend/engine02_retrieval/` 標記為正式棄用、只保留給上面兩支 fallback 用，(b) 之後修 bug 要不要規定「兩邊都要改」還是「乾脆讓 fallback 也失效、只留一份」。這是跨團隊決定，不建議 ENGINE01 這邊單方面刪除。

## 平行技術棧占位（非死碼，不要誤刪）

`CLAUDE.md`「Repo 結構」已經說明 `agent/`、`bff/`、`mcp_servers/`、`web/`、`contracts/`、`evals/` 是 2026-09-19 團隊決議建置 Hermes Agent 應用時新增的平行技術棧，目的是給 `integration/hermes-app` 分支用。這次盤點確認：**其中一部分其實已經被現在的 demo 直接引用**（見下方「文件需要修正」），其餘大部分維持純占位，尚未開始：

| 路徑 | 現況 |
|---|---|
| `mcp_servers/trends/` | 只有 `README.md`，零 `.py` |
| `contracts/`、`contracts/samples/` | 只有 2 份 README，連 schema／範例 JSON 都還沒加 |
| `web/` | `frontend/` 的完整複本，但接的是 `bff/main.py:8100`／`engine02.api:8004`（跟現場實際的 `mcp_servers.catalog:8002` 不同 port 布局），README 自己也寫「比賽現場再建立前端專案...尚未開始」 |
| `bff/engine01_intent/`、`bff/feedback/`、`bff/main.py`、`bff/activity_log/` | 只在 `bff/README.md` 描述的獨立框架（另一組 port：8000／8002／8003／8100）底下運作，`docs/status.md` 已經明確記錄「目前不影響現在在跑的 demo 架構」 |
| `evals/intent/`、`evals/recommendation/`、`evals/results/`、`evals/simulated_user/` | 只有 README，尚未開始 |
| `agent/skills/feedback-interpreter`、`intent-extractor`、`need-probe-planner`、`recommendation-explainer` | 28 行的 TODO stub（`author: "TODO"`），只有 `concept-image-director/SKILL.md`（281 行）有實際內容，但目前也沒有任何呼叫端在用（生圖走的是直接呼叫腳本，不是 Hermes skill 觸發） |

**不建議刪除**——這些是其他組員／未來分支要接手的地基，刪了會影響 `integration/hermes-app` 分支的後續工作，跟今天的 demo 完全無關。

### 文件需要修正（miscategorized，不是刪除問題）

以下路徑**其實已經是現在這條 demo 真的在用的程式碼**，但 `CLAUDE.md`／`AGENTS.md` 目前的敘述把它們歸類成「純新增、不影響 backend/frontend」，這是文件過時，已在本次更新中修正：

- `bff/images/concept.py`（＋它 import 的 `bff/shared/schemas.py`、`bff/shared/user_store.py`）——`backend/engine01_intent/main.py` 第 62 行直接 `from bff.images.concept import ...`。
- `agent/scripts/generate_grid.py`、`agent/scripts/slice_grid.py`、`agent/scripts/grid_common.py`、`agent/scripts/hermes_image.py`——被 `bff/images/concept.py` 呼叫的子行程腳本。
- `mcp_servers/catalog/`——現場 ENGINE02 的實際啟動進入點。

另外 `agent/scripts/check_cells.py`、`agent/scripts/pinterest_palette.py` 是有實作、但不在自動路徑上的手動工具（`evals/choice_images/README.md` 有記錄怎麼用），也不是死碼，只是要手動觸發。

## 孤兒／過時文件

| 文件 | 說明 |
|---|---|
| `docs/engine02-retrieval.md` | 自己開頭就寫「這份文件已經過時，留著只是給歷史脈絡用」，純粹是導覽頁，指向 `engine02-design.md`／`engine02-pipeline.md`／`engine02-literature-review.md`／`backend/engine02_retrieval/README.md`。**它自己指向 `backend/engine02_retrieval/README.md` 這個連結也過時了**（現場真正該看的是 `mcp_servers/catalog/README.md`，見上面「已分岔的重複目錄」），已一併修正連結目標，內容本身維持導覽頁定位不變。|
| `docs/engine02-overview.md`（148 行） | **完全沒有被任何文件連結**——`CLAUDE.md`「想找更多細節的話」的索引、`docs/README.md` 都沒提到它，內容疑似是 `docs/engine02-design.md`（1116 行、完整版）出現前的早期草稿，後來忘記下架或補進索引。建議跟 ENGINE02 負責人確認要收進索引還是直接刪除。 |
| `docs/prd.md` | `docs/README.md` 自己已經記錄「目前有兩份 PRD（這條分支的 `docs/prd.md`，以及 Hermes 應用版，只存在於 `integration/hermes-app` 分支），合併前要先決定哪份為準」——這是已知的跨分支重複，不是這條分支能單獨處理的問題。 |
| `AGENTS.md` | 跟 `CLAUDE.md` 應該逐字同步（給 Codex CLI 用的複本），但這次盤點發現少了 2026-09-20 「`ENGINE02_CATALOG` 預設要帶 `hm_filled`」那次修正——已在本次更新中補上，之後 `CLAUDE.md` 有任何修改都要記得同步一份到 `AGENTS.md`。 |

## 不確定，交給團隊判斷

| 路徑 | 說明 |
|---|---|
| `scripts/fetch_pinterest_boards.py` | 一次性 Pinterest 板子資料拉取工具，輸出（`data/pinterest/pins_20260919.json`）已經 commit，工作看起來已經做完，除非要重新拉取否則用不到 |
| `scripts/verify_qwen_reranker_official.py` | ENGINE02 的一次性 reranker benchmark 腳本，需要另外 `git clone third_party/qwen3-vl-embedding` 才能跑，屬於 ENGINE02 研究工具的一部分 |
| `validation/` | 只有 `README.md`，完全沒有程式碼——不是「死碼」（沒有東西可以死），是從一開始規劃的離線驗證迴圈功能還沒實作。團隊要決定這次要不要真的做，還是先刪掉這個占位資料夾 |

## 非本次盤點對象（明確排除）

`scripts/` 底下其餘約 55 支 `eval_*.py`／`fetch_*.py`／`build_*.py`／`prepare_catalog*.py`／`crawl_*.py` 等，都被 `docs/engine02-design.md`／`docs/research/*.md` 或彼此引用，是 ENGINE02 團隊完整的資料前處理與評測工具鏈，不是本次盤點的對象，也不建議 ENGINE01 這邊單方面處理。`docs/research/` 底下 40 幾份文獻回顧／實驗報告同理，不在這次盤點範圍內。

## 根目錄與 `data/`：確認乾淨

`git ls-files` 確認沒有 `__pycache__`／`.pyc`／`node_modules`／`.venv`／`.venv-engine02`／log 檔被意外 track 進 git，`.gitignore` 對這些都有正確排除。`data/` 底下實際被 commit 的檔案（`data/catalog/*`／`data/inspiration/`／`data/labels/`／`data/pinterest/`／`data/trends/`／`data/crawl_dataset/`／`data/context/` 等）在 `.gitignore` 裡都有對應的 `!data/...` 白名單註解說明原因（例如需要 GPU 或金鑰才能重新產生），沒有發現意外或不明原因被 track 的檔案。這部分不需要任何動作。
