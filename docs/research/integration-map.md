# 整合地圖：全系統長什麼樣、每塊在哪、缺什麼才跑得起來

> **2026-09-19 更新**：這份是對 **2026-09-18 當時**各分支狀態的分析，內容照原樣保留。
> `main` 已經不是文中描述的「舊結構」——它現在同時具備 `backend/`＋`frontend/`（原有）
> 與 `bff/`＋`mcp_servers/`＋`agent/`＋`web/`（新增），兩套並存、都可運作。
> 因此文中「在 hermes-app 上 `backend.engine02_retrieval` 不存在」這類敘述**只適用於
> `integration/hermes-app`**，在 `main` 上兩個模組路徑都成立。

調查時間：2026-09-19。方法：`git ls-tree -r --name-only origin/<branch>` 與 `git show origin/<branch>:<path>`，全程唯讀，未 checkout 任何其他分支、未 push。
本文件是 ENGINE 02（`engine02-research`）為了「我們要服務誰、服務什麼 payload」而做的全域盤點。

---

## 1. 分支盤點

`git rev-list --count origin/main..origin/<b>` / 反向：

| 分支 | HEAD | 作者／日期 | 相對 main 領先 | 落後 | 內容 | 定位 |
|---|---|---|---|---|---|---|
| `main` | `3790eaa` | HO,YUN-CHEN 09-18 | — | — | 舊結構 `backend/`＋`frontend/`＋`validation/`；只有 engine01 有實作，engine02/03 是空 README | **基準線，不是交付目標**（見 `docs/migration-to-hermes-app.md`：「比賽前一晚不改動 main」） |
| `engine01-intent` | `a442138` | HoYunChen 09-18 | 2 | 1 | 相對 main 只多 4 個**文件**改動（`CLAUDE.md`、`docs/frontend.md`、`docs/interface-contract.md`、`docs/pinterest-and-generation.md`，共 +20 行）。程式碼已經在 main 裡 | 已被整合分支吸收，**死路** |
| `engine02-research`（我們） | `fb13824` | Evan-Jiamg 09-19 | 145 | 12 | 根目錄 `engine02/` package（38 檔）＋`backend/engine02_retrieval/`（服務層）＋`tests/`（14 檔）＋`scripts/`（43 支）＋`docs/contract/`＋`docs/research/`（27 篇） | 已全部併入整合分支；我們繼續在這裡開發 |
| `engine03-feedback` | `e697d8d` | chrislaiisme 09-19 | 1 | 1 | 單一 commit，`backend/engine03_feedback/{contracts,prompts,service,main}.py`＋`examples/`＋`tests/`（+833 行） | **唯一還沒被整合的實作**，是必須拉進來的活分支 |
| `integration/hermes-app` | `748cf42` | Tony 09-19（Merge `origin/engine02-research`） | 158 | 0 | Hermes app 結構：`agent/`、`bff/`、`engine02/`、`mcp_servers/`、`web/`、`contracts/`、`evals/` | **唯一的整合目標** |
| `chore/repo-skeleton` | `a516f63` | Tony 09-18 | 4 | 0 | Hermes 骨架的來源 commit（`agent/`、`bff/`、`contracts/`、`evals/`、`mcp_servers/` 的 README 佔位） | 已被整合分支完整包含，**死路** |
| `feature/frontend-user-ui` | `cdb978a` | 許綺文 09-18 | 1 | 0 | 舊結構下的 `frontend/`（Next.js IntentWeave prototype） | 已被整合分支吸收（搬成 `web/`），**死路** |
| `gh-pages` | `b0751d0` | Tony 09-17 | 0 | 10 | 只有 5 個檔：`index.html`、`privacy.html`、`styles.css`、`assets/`、`.nojekyll` | GitHub Pages 靜態宣傳頁，與系統無關 |

### 正式整合目標：`integration/hermes-app`（已證明）

```
$ git merge-base --is-ancestor origin/main                    origin/integration/hermes-app  # → 0 MERGED
$ git merge-base --is-ancestor origin/engine01-intent         origin/integration/hermes-app  # → 0 MERGED
$ git merge-base --is-ancestor origin/engine02-research       origin/integration/hermes-app  # → 0 MERGED
$ git merge-base --is-ancestor origin/chore/repo-skeleton     origin/integration/hermes-app  # → 0 MERGED
$ git merge-base --is-ancestor origin/feature/frontend-user-ui origin/integration/hermes-app # → 0 MERGED
$ git merge-base --is-ancestor origin/engine03-feedback       origin/integration/hermes-app  # → 1 NOT merged
```

`integration/hermes-app` 落後 main 0 個 commit、領先 158 個，且已包含 5 條分支中的 4 條（含我們 `fb13824` 的最新 HEAD）。
唯一缺口是 `engine03-feedback`。
對照 `docs/migration-to-hermes-app.md`（該檔只在 `integration/hermes-app` 上；main 未收錄，因為它的前提是「不改動 main」）：「Hermes Agent 應用的結構與三方整合的結果只存在於 `integration/hermes-app`，**demo 從這條分支跑**。」

反過來，沒有任何一條分支被併回 `main`（六次 `--is-ancestor ... origin/main` 全部回 1）。**`main` 是過期的。**

---

## 2. Hermes app 佈局：什麼跑在哪裡

`integration/hermes-app` 把 `backend/` 整個移除（`git ls-tree | grep -c '^backend/'` → **0**），改成：

```
agent/          Hermes Profile Distribution（安裝：hermes profile install ./agent --alias）
  SOUL.md         agent 身分
  config.yaml     profile 設定
  distribution.yaml  發佈 manifest
  skills/         5 支 SKILL.md ＋ shared/（詞表，非 skill）
bff/            Runtime：內嵌 Hermes Agent 的後端服務（只對 127.0.0.1 開放）
  engine01_intent/  ← 由 backend/engine01_intent/ 原地搬來（唯一有程式碼的子目錄）
  shared/           auth.py / schemas.py / user_store.py
  feedback/         只有 README，狀態「尚未開始」
  images/           只有 README
  activity_log/     只有 README
engine02/       我們的 Python package，刻意留在根目錄
mcp_servers/catalog/main.py   ← ENGINE 02 的 HTTP 服務層搬到這裡
web/            Next.js 前端（原 frontend/）
contracts/ evals/ data/ docs/ scripts/ tests/ reports/
```

### 2.1 什麼是「ChatGPT 側的 agent skill」、什麼是 Python 服務

**`agent/skills/*` 全部是 Markdown 檔，零程式碼。** 它們是要給 Hermes runtime 載入的提示詞政策，不是服務：

| skill | description（frontmatter 實文） | 負責線 |
|---|---|---|
| `intent-extractor` | "Turn one consumer sentence into a structured apparel intent, marking stated, salient, inferred and unmentioned attributes." | 線 1 |
| `need-probe-planner` | "Plan the next image choice question that changes exactly one unstated attribute while keeping stated constraints fixed." | 線 1 |
| `recommendation-explainer` | "Write recommendation reasons grounded only in the attributes of retrieved catalog products." | 線 2（＝我們） |
| `concept-image-director` | "Write abstract concept-image descriptions from the current intent and revise them with feedback, without naming brands." | 線 3 |
| `feedback-interpreter` | "Convert dimension ratings and free-text feedback into preference adjustments or intent revisions." | 線 4 |

**五支 skill 的正文全部是佔位符。** 每一支的 `## When to Use` / `## Procedure` / `## Pitfalls` / `## Verification` 四節內容一字不差都是 `TODO`，`author` 與 `license` 也是 `"TODO"`。`agent/SOUL.md` 同樣是 `TODO：撰寫 agent 的身分與互動原則`（只列了五條要涵蓋的原則）。

`agent/config.yaml` **沒有任何設定鍵**，整份檔案只有註解（不寫死 provider/model，另警告 `image_gen.use_gateway: true` 會覆蓋 provider）。`agent/distribution.yaml` 有 `name: consumer-intent-agent`、`version: 0.1.0`、`hermes_requires: ">=0.21.2"`，而 `env_requires: []`（TODO 未填）。

`agent/README.md` 明說：「暫不放 `mcp.json`：工具服務由 `bff/` 啟動時自行註冊」。

### 2.2 誰呼叫 ENGINE 02、送什麼 payload

**目前沒有任何程式會呼叫 ENGINE 02。** 推論鏈：

1. skill 是 Markdown，不能發 HTTP；`recommendation-explainer/SKILL.md` 的 Procedure 是 `TODO`，沒有寫要呼叫哪個端點。
2. 該由 `bff/` 的流程控制去呼叫。但 `bff/README.md` 自述「目前狀態：尚未開始」，`bff/` 底下唯一的程式碼是 `engine01_intent/`（`/intent`、`/auth/google`、`/profile`、`/health`）＋`shared/`，沒有任何 orchestrator。
3. `agent/` 沒有 `mcp.json`，`mcp_servers/catalog/` 也**不是** MCP server——它是一個 FastAPI app（`from fastapi import FastAPI`），沒有任何 MCP SDK 的痕跡，資料夾名稱與實作不符。`integration/hermes-app` 的 `docs/migration-to-hermes-app.md` 進度表把「engine02 包成 MCP 工具服務」列為「待做」。
4. `web/` 前端完全是 mock：`git grep -c 'fetch(' origin/integration/hermes-app -- 'web/*'` → **零個檔案有 `fetch(`**，狀態存在 `localStorage`（`intentweave.conversations`），資料來自 `web/lib/mock/stylist.ts`、`web/lib/mock/insights.ts`。

**目前唯一真實存在的 ENGINE 02 呼叫介面**是 `mcp_servers/catalog/main.py`（與 `origin/engine02-research:backend/engine02_retrieval/main.py` **逐字元相同**，diff 為空）：

```python
class RetrieveRequest(BaseModel):
    session_id: str = "engine01"
    round: int = 0
    message: str | None = None
    intent: dict = {}
    prev_intent: dict | None = None
    feedback: dict | None = None
    top_k: int = 5
    arm: str | None = None
```

- `POST /retrieve` — ENGINE 01 的 `Intent` → 團隊的 `RetrievalResult`
- `GET /health` — catalog / encoder / warm-up 狀態
- `/engine02/*` — ENGINE 02 完整 API 原樣掛載（`/rank`、`/rank/plain`、`/view`、`/facets`、`/complete-look`、`/visual-search`、`/kansei`、`/vocabulary`、`/arms`、`/trends`、`/gap/*`、`/profile*`、`/concept-image/nearest`、`/items/{id}`、`/images/{id}`…）

**skill 期待拿回什麼**：`recommendation-explainer` 的 description 寫「reasons grounded **only in the attributes of retrieved catalog products**」——這正好對上我們 `RankedItem.explanation`＋`Contribution`（分數分解加總等於總分）。但 `bff/shared/schemas.py` 的 `ProductCard` 只有 `reason: str` 一個欄位，**逐項貢獻會被 FastAPI 的 `response_model` 靜默丟掉**（`mcp_servers/catalog/README.md` 已列為「需要團隊改的三件事」第 2 項）。

---

## 3. ENGINE 03 現況

### 3.1 `integration/hermes-app` 上的 `bff/feedback/`

**只有 `README.md`，沒有任何 `.py`。** 內容是兩段 README 疊在一起：上半是線 4 的骨架描述（結尾「目前狀態：尚未開始。」），下半是從舊 `backend/engine03_feedback/README.md` 併過來的佔位文（「負責人：待確認」）。

`git ls-tree -r origin/integration/hermes-app | grep -i feedback` 只有：`agent/skills/feedback-interpreter/SKILL.md`（TODO）、`bff/feedback/README.md`、`docs/contract/engine03_feedback.schema.json`、`docs/contract/example_engine03_handshake.json`、`docs/engine03-feedback.md`、`docs/research/implicit-negative-feedback.md`。**零行 ENGINE 03 程式碼。**

### 3.2 `engine03-feedback` 分支上的實作

`backend/engine03_feedback/`：`contracts.py`、`prompts.py`、`service.py`（214 行）、`main.py`、`examples/click_only_request.json`、`tests/test_service.py`。

- **入口**：`POST /feedback`（別名 `POST /api/engine3/process_feedback`），body 是 `Engine3Request`＝`current_intent`(共用 `Intent`)＋`feedback_inputs`(共用 `FeedbackInput`×0–2)＋`engine02_request`＋`engine02_response`(含 `items[].design_scores`)＋`interaction`＋`allowed_design_elements`＋`allowed_attribute_values`。
- **出口**：`Engine3Response`＝`contract_version`、`reasoning`、`engine02_feedback`(=`FeedbackRound`)、`updated_intent`、`generation_prompt`、`rejected_ops`。
- **實作方式**：`service.py` 用 `openai` SDK（`_client()` 要 `OPENAI_API_KEY`，model 取 `ENGINE3_MODEL`，預設 `gpt-4o-mini`）做 structured output；純點選（click-only）走 deterministic path，不需 key。有 `_validate_ops()` 驗證 item_id 必須出現在本輪 `items`、`adjust.element` 必須在 `allowed_design_elements`、屬性值必須在 `allowed_attribute_values`，不合格的進 `rejected_ops`。
- **它送給 ENGINE 02 的東西**：`engine02_feedback`，一個 `FeedbackRound`：`{session_id, round, utterance, ops: [...]}`，ops 為 8 種之一（`exclude` / `require` / `adjust` / `choice` / `feeling` / `critique` / `anchor` / `exclude_item`）。
- **它預期 ENGINE 02 怎麼吃**（README「ENGINE 02 handoff」段）：

```python
from engine02.handshake import FeedbackRound, apply_round
feedback = FeedbackRound.model_validate(engine3_response.engine02_feedback.model_dump())
handoff = apply_round(previous_engine02_request, previous_engine02_response, feedback, kansei=kansei)
```

### 3.3 與 `docs/contract/engine03_feedback.schema.json` 的欄位比對

該 schema 由我們從 `engine02.handshake.FeedbackRound.model_json_schema()` 匯出（`scripts/export_contract.py`）。逐欄比對 `engine03-feedback:backend/engine03_feedback/contracts.py` 對應類別：

| 位置 | 我們發佈的 schema | ENGINE 03 的 `contracts.py` | 判定 |
|---|---|---|---|
| root `FeedbackRound` | `required: [session_id, round]`，props `session_id/round/utterance/ops` | 相同 | ✅ |
| `ExcludeOp` | `required:[attribute,value]`，attribute enum 6 值 | 相同（`AttributeName`） | ✅ |
| `RequireOp` | 同上 | 相同 | ✅ |
| **`AdjustOp.step`** | `enum:[-1,1]`、**`default: 1`**（root `required` 只有 `element`） | `step: Literal[-1, 1]`，**沒有 default → 必填** | ⚠️ **唯一的欄位層級不符** |
| `ChoiceOp` | `required:[]`，4 欄 | 相同 | ✅ |
| `FeelingOp` | `required:[quote]`，`lam` default 1.0，`needs_override` | 相同 | ✅ |
| `CritiqueOp` | `required:[reference_item_id]`，attribute enum 5 值、direction enum 3 值 | 相同（`CritiqueAttribute`） | ✅ |
| `AnchorOp` / `ExcludeItemOp` | `required:[]` | 相同 | ✅ |
| `NeedProbability` | `required:[need_id, prob]`，prob 0–1 | 相同 | ✅ |

**operation 集合本身是對齊的**（八種、欄位名、enum 值全同）。實質的不符不在欄位名，而在下面三處：

1. **`AdjustOp.step` 必填性相反。** 我們的 `handshake.AdjustOp.step: Literal[-1,1] = 1`；ENGINE 03 的沒有 default。後果：ENGINE 03 的 `GET /contract/engine02-feedback` 回的 schema 與我們發佈的那份**不是同一份**，兩邊都對外宣稱是「contract 0.1.0」。誰的 schema 被餵給 LLM 做 structured output，決定了模型會不會漏填 `step`。
2. **`FeedbackRound` 根本送不進我們的 HTTP 介面（最嚴重）。**
   - `engine02/contracts.py::Engine02Request.feedback` 的型別是 **`FeedbackState`**（欄位：`design_adjust_steps`、`chosen_item_ids`、`rejected_item_ids`、`excluded_item_ids`、`anchor_item_ids`、`concept_image_embedding`、`reference_item_id`、`critique`、`choice_history`、`design_weight_delta`），**不是 `FeedbackRound`**。`docs/contract/engine02_request.schema.json` 的 `feedback` 是 `$ref: #/$defs/FeedbackState`，確認無誤。
   - `mcp_servers/catalog/main.py` 的 `/retrieve` 把 `body.feedback` 丟給 `engine02/intent_adapter.py::feedback_from_engine03()`。該函式只認兩種形狀：(a) 已經是我們的 ledger（`set(payload) & {"choice_history","chosen_item_ids",...}` 非空 → 原樣通過）；(b) 團隊的 `FeedbackInput`（`attribute_scores` / `selected_option_id` / `free_text`）。
   - `FeedbackRound` 的鍵是 `{session_id, round, utterance, ops}`，**兩種都不是** → 函式走到底，`out` 全空，回傳 `({}, [])`。**所有 ops 會被靜默丟棄，不報錯、不進 `unresolved_from_intent`。** 這是整條回饋迴圈最可能在台上無聲失效的點。
   - 真正會正確處理 ops 的是 `engine02/handshake.py::apply_round()`，但 `engine02/api.py` **沒有任何端點暴露它**（`grep -n 'handshake\|apply_round' engine02/api.py` 無結果）。ENGINE 03 README 給的是 in-process Python 呼叫，而 ENGINE 03 自己是獨立的 FastAPI 服務——**沒有人是那個 in-process orchestrator。**
3. **回應型別與團隊書面契約不一致。** `docs/interface-contract.md` §4 定義的是 `FeedbackResult`（`bff/shared/schemas.py` 有 `FeedbackResult` 與 `WeightAdjustment`）。ENGINE 03 回的是 `Engine3Response`，欄位完全不同。沒有人消費 `FeedbackResult`，但兩份定義同時掛在 repo 裡。

---

## 4. 要讓 E1+E2+E3 在同一台機器跑起來，缺什麼

### 4.1 我們的服務層確實沒有以 `bff/` 的形式存活下來（已驗證）

- `git ls-tree -r origin/integration/hermes-app | grep '^bff/'` → 只有 `README.md`、`engine01_intent/*`、`shared/*`、以及 `activity_log/`、`feedback/`、`images/` 三個純 README 目錄。**沒有 `bff/engine02_retrieval/`，沒有任何 engine02 相關的 `.py`。**
- 檔案本身沒有遺失：它被搬成 `mcp_servers/catalog/main.py`，內容與 `origin/engine02-research:backend/engine02_retrieval/main.py` 完全相同。
- 但搬家後留下三個沒跟著改的東西：
  1. 檔案 docstring 仍寫 `uvicorn backend.engine02_retrieval.main:app --port 8002`——**在 `integration/hermes-app` 上這個模組路徑不存在**（`main` 上存在），照抄會 `ModuleNotFoundError`。正確指令是 `uvicorn mcp_servers.catalog.main:app --port 8002`。
  2. `optional_user()` 裡 `from backend.shared.auth import decode_session_token`——hermes-app 上是 `bff.shared.auth`。因為包在 `try/except Exception` 裡，後果不是崩潰而是**任何帶 `Authorization` header 的請求都會被當成匿名**，session 不再依 user 命名空間化。
  3. `mcp_servers/` 沒有 `__init__.py`（只有 `mcp_servers/catalog/__init__.py`）。靠 Python 3 namespace package 仍可 import，但前提是 **cwd 必須是 repo 根目錄**。

**`bff/` 底下需要存在什麼**：一個 orchestrator（`bff/main.py` 或 `bff/orchestrator.py`），目前**完全不存在**，它要負責：
- 呼叫 E01 `/intent` → 拿 `Intent`
- 呼叫 E02 `/retrieve`（或 `/engine02/rank`）→ 拿 `RetrievalResult` / `Engine02Response`
- 把本輪 `Engine02Request`＋`Engine02Response`＋前端的 `FeedbackInput` 打包成 `Engine3Request` → 呼叫 E03 `/feedback`
- 把 E03 回的 `FeedbackRound` 餵進 `engine02.handshake.apply_round()` 產生下一輪 `Engine02Request`——**或者**由我們在 `mcp_servers/catalog/main.py` 加一個 `POST /handshake` 端點，讓這一步有 HTTP 接縫（推薦，因為 E03 是獨立 process）
- 記錄 `bff/activity_log/`

### 4.2 其餘缺口清單

| # | 缺什麼 | 證據 | 誰補 |
|---|---|---|---|
| 1 | ENGINE 03 程式碼不在整合分支 | `origin/engine03-feedback` 未被 `--is-ancestor` 包含 | 線 4 merge，並把 `backend/engine03_feedback/` → `bff/feedback/`、`backend.shared.*` → `bff.shared.*` |
| 2 | `FeedbackRound` → ENGINE 02 沒有 HTTP 接縫 | `engine02/api.py` 無 `apply_round` 端點 | ENGINE 02（我們） |
| 3 | `feedback_from_engine03()` 收到 `FeedbackRound` 會靜默回空 | `intent_adapter.py:495` 的 `ours` 集合不含 `ops`/`utterance` | ENGINE 02（我們） |
| 4 | `bff/` orchestrator 不存在 | `bff/README.md`「目前狀態：尚未開始」 | 線 4 |
| 5 | 5 支 SKILL.md 全是 TODO、`SOUL.md` 是 TODO、`config.yaml` 無設定鍵 | 上文 §2.1 | 各負責線 |
| 6 | 前端完全 mock，沒有一行 `fetch(` | `git grep -c 'fetch(' -- 'web/*'` 無輸出 | 線 5 |
| 7 | `bff/images/`（生圖）、`mcp_servers/trends/`（Pinterest）、`bff/activity_log/` 都只有 README | tree | 線 3 / 線 2 |
| 8 | `RetrievalResult.concept_image` 宣告為必填，E02 填不出來 | `bff/shared/schemas.py:195 concept_image: ConceptImage` | 線 1 改成 `Optional[...] = None` |
| 9 | `ProductCard` 沒有 `reason_contributions`，可解釋性會被靜默丟掉 | `bff/shared/schemas.py:174-181` | 線 1 |
| 10 | 商品庫不在 git | `data/README.md`「只存在本機，不進版控」 | 見 §5 |
| 11 | `agent/distribution.yaml` 的 `env_requires: []` 未填、`author`/`license` 是 `"TODO"` | 該檔 | 線 4 |

---

## 5. 單機啟動計畫（一台 Linux、一張 GPU）

前提：`integration/hermes-app` 已 checkout 到 `/srv/hermes`，且**已先 merge `origin/engine03-feedback` 並把 import 從 `backend.shared` 改成 `bff.shared`**（第 0 步）。所有指令的 working directory 都是 repo 根目錄 `/srv/hermes`。

### 第 0 步：環境與相依

```bash
cd /srv/hermes
uv venv --python 3.12 .venv
source .venv/bin/activate

# 先裝符合這台機器 CUDA 版本的 torch（https://pytorch.org/get-started/locally/）
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

# ENGINE 02：serving path ＋ 編碼器
uv pip install -e ".[dev]"
uv pip install -e ".[models]"

# ENGINE 01 / 03 / bff 的相依（注意：這份與 pyproject.toml 衝突，見 §6）
uv pip install fastapi "uvicorn[standard]" "pydantic>=2" python-dotenv google-auth requests "openai>=1.40"
# ↑ 刻意不裝 requirements.txt 裡的 faiss-cpu / sentence-transformers：
#   engine02 兩個都沒用，且 faiss-cpu 的部分 wheel 相依 numpy<2，會打爆 pyproject 的 numpy>=2
```

**git 裡沒有、必須自備的東西：**

| 項目 | 取得方式 | 誰需要 |
|---|---|---|
| `data/catalog/kagl/`（items.parquet＋images/＋index/） | `python scripts/prepare_catalog.py --source Marqo/KAGL --limit 5000 --shuffle-buffer 256 --seed 0 --out data/catalog/kagl` | E02 |
| `data/catalog/polyvore/`＋`category_cooccurrence.json` | `python scripts/prepare_catalog.py --source Marqo/polyvore --limit 3000 --out data/catalog/polyvore --full-cooccurrence`（約 10 分鐘） | E02 的 `/complete-look` |
| `Marqo/marqo-fashionSigLIP` 權重（約 2 GB） | 首次啟動自動從 HF 下載；請先設 `HF_HOME` 到大容量磁碟 | E02 |
| OutfitTransformer checkpoints＋`index/ot_items.npz` | `python scripts/precompute_ot_cache.py`；沒有 checkpoint 時 `ENGINE02_OT=1` 只會 warning 並退回影像相似度，不會擋啟動 | E02 `/complete-look` |
| `codex` CLI，且跑過一次 `codex login` | ENGINE 01 用 `codex exec --output-schema`，**不需要 `OPENAI_API_KEY`** | E01 |
| `OPENAI_API_KEY` | platform.openai.com；ENGINE 03 只要有文字／選項／評分回饋就必須有 | E03 |
| `GOOGLE_CLIENT_ID` | Google Cloud OAuth Client ID（Web application 型） | E01 登入 |
| `SESSION_SECRET` | `python -c "import secrets; print(secrets.token_hex(32))"` | E01/E03 |

`.env`（從 `.env.example` 複製，放在 repo 根目錄）：

```dotenv
OPENAI_API_KEY=sk-...
ENGINE3_MODEL=gpt-4o-mini
GOOGLE_CLIENT_ID=<your>.apps.googleusercontent.com
SESSION_SECRET=<token_hex(32)>
DEV_BYPASS_AUTH=true          # demo 當天必須改回 false
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

### 第 1 步：ENGINE 02（port 8002）— 先起，因為它要載模型＋暖機

```bash
cd /srv/hermes && source .venv/bin/activate
export HF_HOME=/srv/hf-cache
ENGINE02_CATALOG=data/catalog/kagl \
ENGINE02_ENCODER=marqo-fashionSigLIP \
ENGINE02_DEVICE=cuda \
ENGINE02_OT=1 \
ENGINE02_DEMO=1 \
ENGINE02_LLM=none \
ENGINE02_ARM=full_zclip3 \
ENGINE02_PUBLIC_BASE=http://localhost:8002 \
CORS_ALLOWED_ORIGINS=http://localhost:3000 \
uvicorn mcp_servers.catalog.main:app --host 127.0.0.1 --port 8002
```

- `ENGINE02_DEMO=1` 保證服務路徑不連網、不等 LLM。`ENGINE02_LLM=none` 關掉理由改寫（想開就拿掉，需要 `OPENAI_API_KEY`）。
- 啟動會跑 warm-up（`ENGINE02_WARMUP=0` 可關）。等 `GET http://127.0.0.1:8002/health` 回 200 再進下一步。
- **不要**照抄檔案 docstring 裡的 `backend.engine02_retrieval.main:app`，那個模組在這條分支上不存在。
- 冒煙測試：`curl -s -X POST localhost:8002/engine02/rank -H 'content-type: application/json' -d @docs/contract/example_round1_request.json | head -c 400`

### 第 2 步：ENGINE 01（port 8000）

```bash
cd /srv/hermes && source .venv/bin/activate
codex login                    # 一次性；沒做這步整個 E01 跑不動
CORS_ALLOWED_ORIGINS=http://localhost:3000 \
uvicorn bff.engine01_intent.main:app --host 127.0.0.1 --port 8000
```

冒煙測試（`DEV_BYPASS_AUTH=true` 時；第一次呼叫會等 8–17 秒）：

```bash
curl -X POST http://127.0.0.1:8000/intent -H 'content-type: application/json' \
  -d '{"message": "我想要件簡約風格的黑色外套"}'
```

### 第 3 步：ENGINE 03（port 8003）

合併後（模組路徑改成 `bff.feedback`）：

```bash
cd /srv/hermes && source .venv/bin/activate
uvicorn bff.feedback.main:app --host 127.0.0.1 --port 8003
```

若尚未搬遷、暫時用 `engine03-feedback` 分支的另一個 worktree，則是 `uvicorn backend.engine03_feedback.main:app --port 8003`（該 worktree 要有自己的 `backend/shared/`）。

不需要 API key 的冒煙測試：

```bash
curl -X POST http://127.0.0.1:8003/feedback -H 'Authorization: Bearer dev' \
  -H 'content-type: application/json' \
  -d @bff/feedback/examples/click_only_request.json
```

### 第 4 步：前端（port 3000）

```bash
cd /srv/hermes/web && npm install && npm run dev      # Next.js 預設 3000
```

注意：`web/` 目前**完全是 mock**，不會打任何後端。這一步只證明畫面起得來。

### 第 5 步：上台前的閘門

```bash
cd /srv/hermes && source .venv/bin/activate
pytest -q tests                                      # ENGINE 02 的測試，model-free
python scripts/integration_check.py --catalog data/catalog/kagl --encoder marqo-fashionSigLIP --device cuda --ot
```

**不要裸跑 `pytest`**：`bff/engine01_intent/tests/test_accuracy.py` 會真的呼叫 10 次 `codex exec`，燒團隊共用額度（約 2–3 分鐘）。

### 依賴順序總結

```
8002 ENGINE 02 (先起，載模型＋暖機) → 8000 ENGINE 01 (需 codex login) → 8003 ENGINE 03 (需 OPENAI_API_KEY) → 3000 web
```

**目前這四個 process 之間沒有任何程式把它們串起來**（§4.1 第 4 點）。上面能做到的是「四個服務各自活著且各自可以用 curl 打通」，不是端到端 demo。

---

## 6. 衝突與風險

1. **兩份互相打架的依賴清單並存。** 根目錄同時有 `requirements.txt`（`faiss-cpu`、`sentence-transformers`、無版本釘選）與 `pyproject.toml`（`numpy>=2.0`、`pandas>=2.2`、`pyarrow>=17.0`）。`faiss-cpu` 部分 wheel 相依 `numpy<2`，與 `numpy>=2` 直接衝突；而 `requirements.txt` 缺 `pyarrow`——**沒有 pyarrow 就讀不了 `items.parquet`，ENGINE 02 連啟動都不行**。`mcp_servers/catalog/README.md` 已經提過，但整合分支上兩份檔案仍然同時存在。
2. **`CLAUDE.md` 對 repo 結構的描述是錯的。** `CLAUDE.md:53` 寫 `bff/engine02_retrieval/`，實際位置是 `mcp_servers/catalog/`。`docs/migration-to-hermes-app.md` 又寫 `backend/engine02_retrieval/` → `mcp_servers/catalog/`。三份文件對同一件事有三種說法。
3. **`mcp_servers/catalog/` 名實不符。** 目錄名宣稱是 MCP server，內容是純 FastAPI app，沒有任何 MCP SDK。真正把它包成 MCP 工具是 migration doc 進度表上的「待做」項。任何人照目錄名去找 MCP 註冊碼都會撲空。
4. **ENGINE 03 的 handoff 是 in-process 呼叫，但兩邊是不同 process。** README 給的是 `from engine02.handshake import apply_round`，而 E03 跑在 8003、E02 跑在 8002。沒有第三方 orchestrator 就接不起來。
5. **`FeedbackRound` 送進 `/retrieve` 的 `feedback` 會靜默被丟掉**（§3.3 第 2 點）。這是「看起來有跑、結果沒變」的典型無聲失效，demo 當天最危險。
6. **contract 0.1.0 有兩份 schema。** 我們發佈的 `docs/contract/engine03_feedback.schema.json`（`AdjustOp.step` 有 default 1）vs ENGINE 03 `GET /contract/engine02-feedback` 動態產生的（`step` 必填）。兩份都自稱 `0.1.0`。
7. **`FeedbackResult` vs `Engine3Response` 兩套回饋回應契約並存**，`docs/interface-contract.md` §4 與 `bff/shared/schemas.py` 定義了前者但沒有人實作。
8. **`RetrievalResult.concept_image` 必填但 ENGINE 02 填不出來**——包成 `RetrievalResult` 會直接 `ValidationError`。修法是一行（改成 `Optional[ConceptImage] = None`），但要線 1 同意。
9. **`.env.example` 仍引用已不存在的路徑**：註解寫 `backend/engine01_intent/llm_client.py`、`used by backend/pinterest only`，這兩個路徑在 hermes-app 上都沒有。
10. **`bff/engine01_intent/README.md` 內嵌別人機器的絕對路徑**（`C:\Users\Celestine\OneDrive\桌面\Hackathon`），且指令是 PowerShell。要在 Linux demo 機上跑必須整段忽略。
11. **`agent/distribution.yaml` 的 `env_requires: []`**——`hermes profile install ./agent` 不會檢查任何金鑰，缺 key 的失敗會延到執行期才爆。
12. **`main` 是死的但長得像活的。** 沒有任何分支被併回 `main`，`main` 上的 `backend/engine02_retrieval/README.md`、`backend/engine03_feedback/README.md` 都還是空骨架。任何從 `main` clone 的人會拿到一個只有 ENGINE 01 的 repo。
13. **catalog 名稱不一致。** `mcp_servers/catalog/README.md` 的啟動指令用 `data/catalog/kagl_polyvore_filled`，但本機 `data/catalog/` 底下只有 `kagl/`、`kagl_polyvore/`（只有兩個 VLM 屬性檔，沒有 `items.parquet`）、`polyvore/`——**`kagl_polyvore_filled` 不存在**。§5 因此改用 `data/catalog/kagl`。

---

## 我無法核實的部分

- **Hermes runtime 本身。** repo 裡沒有 Hermes 的原始碼或 lock 檔，我沒有執行過 `hermes profile install ./agent`，無法確認 `hermes_requires: ">=0.21.2"` 是否對得上現行版本、`config.yaml` 這種「只有註解、沒有鍵」的檔案 Hermes 是否接受。
- **實際執行結果。** 我沒有啟動任何服務、沒有跑 `pytest`、沒有跑 `scripts/integration_check.py`。§5 的指令是從 `engine02/README.md`、`mcp_servers/catalog/README.md`、`bff/engine01_intent/README.md`、`engine02/api.py` 的 env 讀取邏輯與 `engine03-feedback` 的 README 推導出來的，未經實機驗證。本機甚至沒有 `pandas`（`import engine02.handshake` 在我的環境直接 `ModuleNotFoundError`）。
- **`AdjustOp.step` 以外的 schema 差異。** 我用逐欄人工比對而非 `model_json_schema()` 實跑比對（因為缺 pandas 無法 import `engine02.handshake`）。八種 op 的欄位名、型別、enum 值我都逐行看過，但序列化細節（`$defs` 排序、`discriminator` 區塊）沒有機器驗證。
- **`data/catalog/kagl/index/` 是否完整、以及是用哪個 encoder 建的**——我只列了目錄名，沒有檢查裡面的向量檔是否與 `marqo-fashionSigLIP` 對應。若不對應，首次啟動會重新編碼整個商品庫。
- **GPU 規格與 `ENGINE02_DEVICE=cuda` 的可行性。** `reports/model_verification.md` 是在**純 CPU** 的 Ryzen 7 7735U 上量的，沒有 GPU 實測數字。
- **`agent/scripts/`、`contracts/samples/`、`evals/*` 的內容**——這些目錄在 tree 裡只有 README，我沒有逐一開啟確認是否真的沒有其他檔案以外的東西。
- **誰是「線 1～線 5」的實際負責人**，以及 `distribution.yaml` 的 `author`/`license` 該填什麼。
