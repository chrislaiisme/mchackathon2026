# ENGINE 02 併入團隊框架的整合計畫

本文比對本分支（`engine02-research`）與團隊 repo（`origin/main`、`origin/engine01-intent`），給出可直接執行的整合決策。
所有引用皆為唯讀讀取（`git show`），未修改任何程式碼、未切換分支。

**核對來源**：`origin/main` 的 `backend/engine01_intent/main.py`、`backend/shared/{auth,schemas}.py`、`backend/requirements.txt`、
`CLAUDE.md`、`README.md`、`.env.example`、`.gitignore`、`docs/{interface-contract,frontend,engine02-retrieval,engine03-feedback,validation-plan,hackathon-brief}.md`、
`index.html`、`scripts/{README.md,engine01-test-page/index.html}`；本分支的 `engine02/{api,contracts,pipeline,service,explain,handshake,diversify}.py`、`pyproject.toml`、`.gitignore`、`README.md`。
`origin/engine01-intent` 與 `origin/main` 的差異僅 4 個 md 檔、20 行（`git diff --stat`），本文以 `origin/main` 為準。

---

## 0. 先講最硬的一件事：兩個分支沒有共同祖先

```
git merge-base origin/main HEAD      → 無輸出，exit 1
git rev-list --max-parents=0 HEAD    → f96ed8e
git rev-list --max-parents=0 main    → eb9fff5      （136 commits vs 12 commits）
```

`git merge origin/main` 會直接拒絕（`refusing to merge unrelated histories`）。
這不是欄位對不上的問題，是**整份 git 歷史對不上**。處理方式見 §6.1。

同時，兩邊實際重疊的**已追蹤路徑只有兩個**：

```
comm -12 <(git ls-tree -r --name-only origin/main | sort) <(git ls-tree -r --name-only HEAD | sort)
→ .gitignore
→ README.md
```

`docs/` 底下**沒有任何同名檔案**（我們是 `docs/engine02-design.md`、`docs/engine02-pipeline.md`、`docs/contract/`、`docs/research/`；
他們是 `docs/engine01-intent.md`、`docs/engine02-retrieval.md`、`docs/interface-contract.md` 等）。
本分支**沒有 CLAUDE.md**（已追蹤與工作目錄都沒有），所以 CLAUDE.md 不是衝突，是「我們單方面繼承對方規則」的問題（§6.4）。

---

## 1. Layout：檔案放哪裡

### 1.1 engine01 的實際慣例

`backend/engine01_intent/main.py` 第 1–3 行 docstring：

```
"""ENGINE01 FastAPI service: one sentence -> structured intent.
Run locally:
    uvicorn backend.engine01_intent.main:app --reload
"""
```

即：**每個引擎資料夾各自持有一個 `FastAPI` 物件**（`app = FastAPI(title="ENGINE01 - Intent Understanding")`），
以 `backend.<engine>.main:app` 的模組路徑從 repo 根目錄啟動，共用 `backend/shared/` 的 schema 與 auth。
`backend/` 本身沒有 `__init__.py`（PEP 420 namespace package），只有 `backend/shared/__init__.py` 與 `backend/engine01_intent/__init__.py`。

### 1.2 決策：`engine02/` 留在根目錄當函式庫，在 `backend/engine02_retrieval/` 放薄服務層

**不搬套件**。理由是可驗證的，不是偷懶：

- `engine02/api.py:49`、`compat_ot.py:24`、`complete_look.py:41`、`llm.py:14` 都寫死 `ROOT = Path(__file__).resolve().parents[1]`，
  預期自己位在 repo 根目錄下一層。搬到 `backend/engine02_retrieval/` 後 `parents[1]` 會指到 `backend/`，
  所有 `data/catalog/...` 預設路徑全部失效。
- `pyproject.toml` 的 `packages = ["engine02"]`、`tests/` 全部 14 個測試檔、`scripts/` 全部 40+ 個腳本、
  `docs/contract/*.schema.json` 的範例，都以 `engine02` 為頂層匯入名。搬家等於在比賽前兩天動 ~80 個檔的 import。
- `origin/main` 上**沒有任何程式碼 import `backend.engine02_retrieval`**——那個資料夾目前只有一份 README。
  所以「套件實體位置」沒有任何人依賴；真正被依賴的接縫是**啟動指令與 HTTP 介面**，那個接縫我們照 engine01 的慣例做。

代價要講清楚：`CLAUDE.md` 的「Repo 結構」區塊明文把 ENGINE02 放在 `backend/engine02_retrieval/`，
所以這個決定**必須拿到 ENGINE01 負責人（CLAUDE.md 作者）的明確同意**，並同步改 `CLAUDE.md` 那個區塊，不能默默違反。

### 1.3 要新增／修改的具體檔案

| 路徑 | 動作 | 內容 |
|---|---|---|
| `engine02/`（60+ 模組）+ `pyproject.toml` | 原封不動搬入 | 不改 import、不改 `parents[1]`、不改測試 |
| `backend/engine02_retrieval/__init__.py` | 新增 | 空檔＋中文註解（照 `backend/shared/__init__.py` 寫法） |
| `backend/engine02_retrieval/main.py` | 新增 | ENGINE02 的對外 FastAPI app：`POST /retrieve`（`Intent` → `RetrievalResult`）、`GET /health`；CORS 讀 `CORS_ALLOWED_ORIGINS`；`Depends(get_current_user)`；用 `app.mount("/engine02", engine02.api.app)` 把既有 22 個端點原樣掛進來，不重寫 |
| `backend/engine02_retrieval/adapter.py` | 新增 | 純翻譯層：`intent_to_request()`（`Intent`+`FeedbackResult` → `Engine02Request`）、`response_to_cards()`（`Engine02Response` → `ProductCard[]`）、`compute_match_score()`（§4.3）。不含任何排序邏輯 |
| `backend/engine02_retrieval/README.md` | 覆寫佔位 | 指向 `engine02/`、`docs/engine02-pipeline.md`、啟動指令、資料前置作業 |
| `backend/shared/schemas.py` | **只加不改**（§4） | `ProductCard` 加選填欄位；`RetrievalResult.concept_image` 改 `Optional`；`match_score` 補 docstring |
| `backend/requirements.txt` | 補齊（§2.3） | 加 numpy/pandas/pyarrow/pillow/httpx 與版本下限 |
| `docs/engine02-retrieval.md` | 覆寫骨架 | 現在是「負責人：待確認」的抄寫稿，換成指向 `docs/engine02-design.md` / `engine02-pipeline.md` 的真規格 |
| `scripts/engine02/`（由 `scripts/*.py` 移入） | 移動 | 避免 40 個 eval 腳本淹掉團隊的 `scripts/`；`scripts/README.md` 加一條 bullet |

---

## 2. 後端實際怎麼跑

### 2.1 一個引擎一個 app，沒有統一入口

`origin/main` 上只有 engine01 有 app。`engine03_feedback/`、`generation/`、`pinterest/`、`frontend/`、`validation/` **全部只有 README**。
沒有 aggregator、沒有 gateway、沒有任何模組負責把 ENGINE02 與 generation 的結果合併成一個 `RetrievalResult`——
但 `docs/interface-contract.md` §5 明寫「由 ENGINE02 和生成模組一起產出（兩者同一輪並行執行，結果合併成一個回應給前端）」。
**這個合併責任目前無人認領**，建議由 `backend/engine02_retrieval/main.py` 的 `/retrieve` 承擔（§4.4）。

### 2.2 Port、runner、部署

- engine01：`8000`（`scripts/engine01-test-page/index.html:75` 寫死 `const API_BASE = "http://127.0.0.1:8000"`）。
- 前端／測試頁：`5173`（`.env.example:41` `CORS_ALLOWED_ORIGINS=http://localhost:5173`）。
- ENGINE02 取 `8002`（本分支 README 既有慣例），與上述不衝突。
- **沒有 runner 腳本、沒有 Dockerfile、沒有 Procfile、沒有部署文件。** `docs/hackathon-brief.md:351` 明文：
  「Docker：非必要項目，demo 當天直接跑 `npm run dev`＋`uvicorn`，GitHub README 負責可重現性。」
  → 我們要自己提供一行啟動指令寫進 `backend/engine02_retrieval/README.md`，不要期待別人的 runner。
- CORS 差異：engine01 用 `allow_origins=<env 清單>` + `allow_credentials=True`；
  我們 `engine02/api.py:163` 是 `allow_origins=["*"]`（且未開 credentials）。薄服務層要改用 env 清單與 engine01 一致。

### 2.3 `backend/requirements.txt` vs `pyproject.toml`：逐項衝突

`backend/requirements.txt` 全檔**完全沒有版本上下限**（除 `pydantic>=2`、`openai>=1.40`）。逐項對照：

| 我們需要 | requirements.txt 現況 | 判定 |
|---|---|---|
| `numpy>=2.0` | **完全沒列**（靠 faiss/sentence-transformers 間接帶入） | **真衝突**。`faiss-cpu` 部分輪子相依 `numpy<2`；一旦解析器選到那組，我們的 `engine02/` 全線爆。必須顯式寫 `numpy>=2` |
| `pandas>=2.2` | **完全沒列** | **硬缺**。`engine02/catalog.py` 直接用 DataFrame |
| `pyarrow>=17.0` | **完全沒列** | **硬缺，會直接 crash**。目錄是 `items.parquet`，沒有 pyarrow `Catalog.load` 起不來 |
| `pillow>=11.0` | **完全沒列** | 硬缺（`/visual-search`、`GET /images/{item_id}`） |
| `httpx>=0.27` | **完全沒列** | 硬缺（`fastapi.testclient`、`scripts/api_check.py`） |
| `fastapi>=0.115` | `fastapi`（無下限） | 需補下限，否則新環境可能裝到舊版 |
| `pydantic>=2.9` | `pydantic>=2` | 需把下限提到 `2.9` |
| `uvicorn>=0.30` | `uvicorn[standard]`（無下限） | 補下限即可 |
| `torch>=2.4`（選配） | 未列，但 `sentence-transformers` **會間接帶入一個 torch** | **最陰的一個**。`pip install -r backend/requirements.txt` 會靜默裝上 CPU 版 torch；等到現場設 `ENGINE02_DEVICE=cuda` 才發現沒有 CUDA 輪子。我們 `pyproject.toml` 註解明寫「先裝對應機器的 torch build，再裝其他」——這個順序要求必須寫進 requirements.txt 的註解 |
| `rank-bm25` | 列為正式相依 | 對我們只是**測試相依**（`tests/test_sparse.py` 拿它逐分比對我們自寫的 postings）。可留，但要註明用途 |
| `sentence-transformers`、`faiss-cpu` | 列為 ENGINE02 相依 | **我們兩個都沒用**：dense 走 `open_clip`/`transformers`，檢索走 numpy 暴力 + 自寫 BM25。這兩個是替「原規劃的 ENGINE02」列的，現在只會拖慢安裝並製造 numpy 衝突。建議刪除或註解掉，需團隊同意 |
| `openai>=1.40` | 有 | 相容（我們的 LLM 改寫是選配，`ENGINE02_LLM=none` / `ENGINE02_DEMO=1` 可完全關掉） |

Python 版本：我們 `requires-python = ">=3.11"`，`CLAUDE.md` 寫「Python 3.11+」，**無衝突**。

`CLAUDE.md` 明文「不要每個引擎各自開一份 venv／requirements」——所以 `pyproject.toml` 進 repo 這件事要挑明：
建議 `pyproject.toml` 保留（`pip install -e .` 是跑我們測試的方式），但**把上表的版本下限同步寫進 `backend/requirements.txt`**，
並在 requirements.txt 註明「ENGINE02 的權威清單在根目錄 pyproject.toml，兩邊要同步」。

---

## 3. Auth

**會。** `backend/shared/auth.py` + `backend/engine01_intent/main.py` 的流程是：
前端拿 Google `credential` → `POST /auth/google` → 後端 `verify_google_id_token()` → 簽自家 HMAC session token（7 天）→
之後每個請求帶 `Authorization: Bearer <session_token>`，由 `Depends(get_current_user)` 解出 `UserProfile`。
`DEV_BYPASS_AUTH=true` 時全部跳過，固定回傳 `dev-local-user`。

**我們的端點需要嗎？需要，但理由不是「防駭客」。** `engine02/api.py` 目前完全沒有 auth，且 `allow_origins=["*"]`。
不加的具體後果：

1. **session 身分會對不上（真正的功能問題）**。engine01 用 `(user.sub, session_id)` 當 session key
   （`session_store.get_or_create(user.sub, request.session_id)`），而我們的 `Engine02Request.session_id` 是**前端自己傳的字串**。
   兩個評審同時在台上操作、剛好撞到同一個 `session_id`，ENGINE02 這側的 `FeedbackState`／`ProfilePrior` 會互相污染，
   而 engine01 那側不會——症狀是「意圖對但推薦莫名其妙」，現場最難 debug 的那種。
2. **偏好可被覆寫**。`ProfilePrior.weights`、`FeedbackState.design_weight_delta` 都是請求體帶進來的，
   沒有身分綁定等於任何人都能替別人的 session 設先驗。
3. **demo 本身不會壞**。誠實講：不加 auth，`/retrieve` 照樣回卡片，評審看不出來。這是「正確性與治理」問題，不是「能不能跑」問題。

建議作法：auth 只加在**薄服務層**的 `/retrieve`，並在 `adapter.intent_to_request()` 內把 session key 命名空間化成
`f"{user.sub}:{session_id}"`；內層 `engine02.api` 的 22 個端點維持無 auth，但 **bind 在 `127.0.0.1`**（或掛在同一個 `Depends` 下）。

**一個會踩到的陷阱**：`backend/shared/auth.py:_session_secret()` 在 `SESSION_SECRET` 未設時直接 `raise RuntimeError`。
所以 `adapter.py` 不可以在 module level import auth，否則我們 250 個測試在沒有 `.env` 的機器上會整批掛掉。
auth 只出現在 `main.py` 的 route 簽名裡。

---

## 4. 契約：`RetrievalResult` 每個欄位我們能誠實填什麼

`backend/shared/schemas.py:180–197` 是真相來源。逐欄位：

| 欄位 | ENGINE 02 來源 | 誠實度備註 |
|---|---|---|
| `session_id` | `Engine02Response.session_id`（原樣回傳） | 直通 |
| `round` | `Engine02Response.round` | 直通 |
| `products[].product_id` | `RankedItem.item_id` | 直通 |
| `products[].image_url` | **沒有現成的 URL**，只有 `RankedItem.image_path`（本機檔案路徑） | 需用既有的 `GET /images/{item_id}`（`api.py:662`，回 `FileResponse`）組成 `{ENGINE02_PUBLIC_BASE}/images/{item_id}`。**沒設這個 env 前端會拿到讀不到的路徑**——這是最容易在 demo 前 10 分鐘才發現的 bug |
| `products[].title` | `RankedItem.title` | 直通 |
| `products[].attributes` | `category` / `subcategory` / `color` / `season` / `occasion` / `gender`（只放非 null，`price` 轉字串） | 這正好回答 `docs/interface-contract.md` 結尾「`ProductCard` 的 `attributes` 具體要放哪些 key」那條待確認事項——由我們 `GET /vocabulary` 的實際目錄欄位決定，不是猜的 |
| `products[].score` | `RankedItem.score` | **要談**。我們的 score 是 z-score 加總，**不是 0–1，可以是負的**；`interface-contract.md` 範例寫 `0.91`，前端很可能當百分比畫進度條。建議：`score` 送原始值並在 docstring 註明範圍，UI 該顯示名次而非百分比；若前端堅持要 0–1，只能加一個明確標示為「僅供顯示」的 slate 內 min-max 值，不可宣稱是機率 |
| `products[].reason` | `RankedItem.explanation` | 見 §4.1 |
| `concept_image` | **不是我們產的** | 見 §4.2 |
| `match_score` | 見 §4.3 | |

### 4.1 `reason` 是單一字串，我們的解釋是有分數的貢獻清單

不需要妥協。`RankedItem.explanation`（`engine02/contracts.py:269`）**本來就已經是單一字串**：
由 `engine02/explain.py:template_reasons()` 產出模板句，若 LLM 改寫通過事實查核才替換，否則退回模板
（`explanation_source: "llm" | "template"`）。所以 `ProductCard.reason = item.explanation`，直通，不損失。

真正會被丟掉的是**分數分解**。作法是在 `backend/shared/schemas.py` 的 `ProductCard` **加選填欄位**（只加不改，舊消費者不受影響）：

```python
class ReasonContribution(BaseModel):
    term: str            # "dense" / "design:structured_shoulders"
    group: str           # dense | bm25 | design | compat | freshness | penalty | rerank
    label: str           # 中文顯示字串（engine02/explain.py 的 GROUP_LABEL / element_labels）
    contribution: float  # weight * normalized
    necessary: bool | None = None   # 拿掉這一項會掉出 top-k
    sufficient: bool | None = None  # 單靠這一項就足以留在 top-k

# ProductCard 新增（全部選填，預設空）：
    reason_contributions: list[ReasonContribution] = []
    reason_mode: str | None = None              # sufficient / necessary / contrastive
    explanation_source: str | None = None       # "llm" | "template"
    attribute_notes: list[str] = []
    margin_vs_cutoff: float | None = None
    relaxed_constraints: list[str] = []         # 來自 ConstraintReport.relaxed
```

並在 docstring 釘住不變式：**`sum(c.contribution for c in reason_contributions) == score`**（我們的測試已釘住這條）。
這樣「理由就是分數分解本身」這個賣點不會在契約邊界蒸發。

> **為什麼一定要改 schema 而不是「多回傳一些欄位」**：FastAPI 的 `response_model` 會**靜默過濾掉**不在 model 上的欄位。
> 不改 `schemas.py` 而多塞欄位，結果是前端什麼都收不到，而且沒有任何錯誤訊息。

### 4.2 `concept_image`：目前是必填，回 null 會直接 500

`RetrievalResult.concept_image: ConceptImage` **沒有預設值**，是必填。
而 `backend/generation/` 在 `origin/main` 上只有一份 README（與我們的 `engine02_retrieval/` 同為佔位）。
所以現況是：**只要 generation 沒做完，任何人都組不出一個合法的 `RetrievalResult`。**

我們產不出概念圖（我們只**消費**它：`POST /concept-image/nearest`、`FeedbackState.concept_image_embedding`）。
建議改成：

```python
    concept_image: Optional[ConceptImage] = None
```

一行、向後相容、不動任何既有欄位，但**必須先知會 ENGINE01 負責人**（`CLAUDE.md`：改 `shared/schemas.py` 欄位前要先知會）。
前端在 `concept_image is None` 時只顯示商品側欄位即可——`docs/frontend.md` 說兩者「並排呈現」，少一邊是版面問題，不是崩潰。

### 4.3 `match_score`：repo 裡有沒有定義？

**有文字定義，沒有公式，也沒有任何實作。** 完整搜尋結果（`git grep -n "match_score\|符合度" origin/main`）：

- `backend/shared/schemas.py:196–197` — 只有型別 `float` 與一行 docstring，無範圍、無算法。
- `docs/interface-contract.md:139` — 「回饋前後都會顯示的符合度分數」，範例值 `0.62`。
- `docs/interface-contract.md:146` — **自己列為待確認**：「`match_score` 的單位／範圍——目前都是 0–1 的浮點數，請確認」。
- `docs/engine03-feedback.md:27` / `docs/validation-plan.md:12` / `docs/hackathon-brief.md:272` — 三處口徑一致的**散文定義**：
  「目前結果跟目前結構化意圖的符合程度（例如意圖要求的顏色／場合／預算條件，**推薦清單裡實際符合的比例**）」。
- `origin/main` 上**沒有任何 `.py` 計算它**。負責人依 `validation-plan.md:12` 是「ENGINE02/03 加前端，一起負責」。

結論：**沒有人定義過怎麼算，這件事落在我們身上。**

#### 提案（可從既有輸出誠實算出）

第一項就是散文定義的字面實作，我們已經有：

```
A = metrics.hard_constraint_satisfaction      # engine02/pipeline.py:778
    = 展示卡片中，滿足使用者明說硬條件（顏色／品類／場合／季節／性別／預算）的比例
    RoundMetrics docstring 已釘死：「computed from item attributes, never from the score」
```

問題是 A 會很快飽和到 1.0（`tests/test_engine02.py:316`、`tests/test_attribute_fill.py:166` 都斷言 `== 1.0`），
台上永遠是 100% → 100%，說不出 62%→89% 的故事。所以加第二項：

```
B = need_alignment = mean over top-k of  Σ_d β_d·c(i,d)      # engine02/eval/tasks.py:334 已實作為離線指標
    即「展示的卡片在多大程度上表達了 ENGINE01/03 推斷出的需求」

match_score = 0.5·A + 0.5·norm(B)
```

`norm(B)` 必須用**離線一次算好的固定參考尺**（例如全目錄 B 分佈的 5%–95% 分位數），寫死成常數存進
`engine02/resources/`，**不可以用當輪候選集重新標準化**。

同時回傳分項，不要只給一個數字：`match_score_parts = {"constraint": A, "need": norm(B)}`，
外加 `constraint_report.relaxed` 與 `metrics.feedback_violations`。

#### 什麼情況下這個數字就是在說謊

1. **每輪用當輪 slate 重新 min-max**——最好的一張永遠是 100%，分數必然上升。這是最常見的造假法，明令禁止。
2. **拿排序分數（`RankedItem.score`）當 match_score**——循環論證：ENGINE03 調高某個權重，分數依定義必然變高，
   證明不了任何事。`RoundMetrics` 的 docstring 之所以寫「never from the score」就是為了擋這個。
3. **移動球門**：第 2 輪的意圖已經被回饋改過，拿「新意圖 vs 新結果」對比「舊意圖 vs 舊結果」，
   上升可能全部來自意圖變寬鬆。**解法**：同時回傳 `match_score_prev_intent`（第 N 輪的卡片，用第 N−1 輪的意圖去評），
   兩個數都給前端。如果只有前者漲、後者沒漲，那就是球門移動，我們要自己說出來。
4. **倖存者偏差**：硬條件過濾會先把不合格的商品移除，A 是在過濾後的集合上算的，天然接近 1。
   若 `ConstraintReport.relaxed` 非空（放寬過條件），A 是對**放寬後**的條件算的，此時**必須在畫面上標出放寬了什麼**，
   否則 100% 是假的。
5. **不允許下降**。如果某一輪回饋讓分數掉了，就顯示它掉了。一個只會上升的數字不是指標，是動畫。

### 4.4 誰來組 `RetrievalResult`

建議 `backend/engine02_retrieval/main.py` 的 `POST /retrieve` 做：
`Intent` →（adapter）→ `Engine02Request` → `engine02` pipeline → `Engine02Response` →（adapter）→ `products` + `match_score`，
`concept_image` 欄位由 generation 模組完成後以 `asyncio.gather` 併入；未完成前填 `None`。
這是本文的**提案**，需要團隊指派確認（§7）。

---

## 5. 前端實際消費什麼

### 5.1 `origin/main` 上沒有前端

- `frontend/` 只有一份 README.md（「負責人：待確認」「這是建 repo 骨架時順便建立的佔位資料夾」）。
- 根目錄 `index.html` / `privacy.html` / `styles.css` 是**給 Pinterest App 審核用的隱私權政策靜態網站**，
  `CLAUDE.md` 明文「不要重新調整或刪除」，全檔 79 行，**沒有任何 fetch**。
- 唯一會呼叫 API 的 JS 是 `scripts/engine01-test-page/index.html`：`API_BASE = "http://127.0.0.1:8000"`，
  只打 `/auth/google` 與 `/intent`，帶 `Authorization: Bearer`。**它不消費 `RetrievalResult`。**
- `docs/frontend.md` 的規格（結果卡片並排 `ProductCard[]` + `ConceptImage` + `match_score`，
  輪次對比要凸顯 `match_score` 變化）目前是**紙上規格，沒有實作**。

### 5.2 但有一個分支已經在寫前端，而且型別對不上

`origin/feature/frontend-user-ui`（不在我的指定閱讀範圍，唯讀查證後列出，供交叉確認）已有完整 Next.js 16 + React 19 + shadcn 應用。
它的 `frontend/lib/types.ts`：

```ts
export interface FashionRecommendation {
  id, name, imageUrl, explanation, attributes: string[], priceBand: string, confidence: number, feedback?
}
```

與 `ProductCard` 的落差：`name` vs `title`、`explanation` vs `reason`、`confidence` vs `score`、
**`attributes` 是 `string[]` 而契約是 `dict[str,str]`**、多出 `priceBand`、**完全沒有 `match_score`、沒有 `concept_image`、沒有 `round`**
（`git grep -i "matchscore\|concept" -- frontend` 零命中）。
且 `lib/services/auth.ts` 與 `lib/services/conversations.ts` **全部是 localStorage mock**，`signInWithGoogle()` 直接寫入一個寫死的 `demoUser`，
整個 `frontend/` **沒有任何 fetch 呼叫後端**。技術選型也與 `docs/frontend.md`（「React + Vite，不用 Next.js／SSR」）相反。

### 5.3 會被靜默丟掉的欄位

即使前端接上契約，以下我們算得出來、但 `RetrievalResult` 裡沒有位置的東西會被 `response_model` 靜默濾掉：
`contributions`（逐項貢獻）、`need_contributions`、`design_scores`、`margin_vs_cutoff`、
`constraint_report`（**放寬了什麼**——這是可解釋性的核心，丟掉最可惜）、`metrics.feedback_violations`、
`/view` 的全部面板（說了／沒說、Div@k、來源、輪次 diff）、`/facets` 的 2–3 群讀法、`diversification`。
§4.1 的選填欄位救回其中最重要的一部分；其餘要靠前端直接打 `POST /engine02/view`（掛載路徑）取得。

---

## 6. 合併風險與處置

### 6.1 無共同祖先（最高風險）
`git merge --allow-unrelated-histories` 技術上可行，但會產生一個沒人看得懂的合併點，且兩邊 `.gitignore`/`README.md` 立刻衝突。
**建議**：`git checkout -b engine02-integration origin/main` → 把本分支的檔案樹複製進去（依 §1.3 的位置）→ 少數幾個有意義的 commit。
本分支 `engine02-research` 保持 push 在遠端不刪，README 加一行連結留住 136 個 commit 的來歷（來源可信度規則）。

### 6.2 `README.md`（唯二實體衝突之一）
main 的是**英文交付物**（開頭明寫「This file stays in English per the competition's deliverable requirement」），
配一份 `README_TW.md` 中文版，`CLAUDE.md` 要求兩份同步。我們的是 97 行中文。
**處置**：保留 main 的 `README.md` / `README_TW.md`；我們的內容搬去 `backend/engine02_retrieval/README.md`（覆寫佔位），
另在 `README.md` 與 `README_TW.md` 的 ENGINE 02 段落各補 3–5 行（兩邊都要改，這是 CLAUDE.md 的硬規則）。

### 6.3 `.gitignore`（唯二實體衝突之二）
取聯集。兩邊共有 `.env`、`__pycache__/`、`*.pyc`、`.venv/`、`data/`。
我們獨有：`models/`、`artifacts/`、`third_party/`、`reports/{ablation,server,agents,demo,llm_paraphrase}/`。
main 獨有：`*.egg-info/`、`.pytest_cache/`、`node_modules/`、`frontend/dist/`、`frontend/.vite/`、`*.faiss`、`*.chroma/`、
`backend/pinterest/cache/`、`backend/generation/output/`、`.DS_Store`、`Thumbs.db`、`.vscode/`、`.idea/`、`.claude/`。
順帶：本分支工作目錄現有未追蹤且未被忽略的 `engine02.egg-info/` 與 `reports/latency/`——
聯集後 `*.egg-info/` 會被 main 的規則蓋掉，`reports/latency/` 要自己補一條。

### 6.4 `CLAUDE.md`：不是衝突，是繼承
本分支沒有 CLAUDE.md，合併後我們**自動受 main 的 CLAUDE.md 約束**，其中兩條我們現在就違反：
1. 「**所有 `.py` 檔都要寫足夠的註解……註解用中文寫**」——我們 60+ 個模組是英文註解。
   兩天內全部翻譯不現實，而且會製造大量無意義 diff。**建議明確協商一條寫進 CLAUDE.md 的例外**
   （「`engine02/` 因既有規模與測試覆蓋，維持英文註解」），不要默默違反。
2. 「不要每個引擎各自開一份 venv／requirements」——見 §2.3 的處置。
另外「Repo 結構」區塊與「介面契約」區塊都要因本文的決定而更新。

### 6.5 `docs/`
**無同名檔案衝突**（已逐檔比對）。但 `docs/contract/*.schema.json`（我們）與 `docs/interface-contract.md` + `backend/shared/schemas.py`（他們）
是兩套會彼此矛盾的真相來源。**處置**：在 `docs/contract/README` 或各 schema 旁註明——
`backend/shared/schemas.py` 管跨引擎邊界（`Intent` / `RetrievalResult`），`docs/contract/*.schema.json` 管 ENGINE02 內部的 `/rank` 請求回應，
兩者由 `backend/engine02_retrieval/adapter.py` 橋接。`docs/research/` 24 個檔是新子樹，不衝突。

### 6.6 `scripts/` 與 `tests/`
`scripts/` 無同名衝突（main 只有 `README.md` 與 `engine01-test-page/`），但 40+ 個 eval 腳本倒進去會淹掉那個資料夾 → 移到 `scripts/engine02/`。
`tests/` main 根目錄沒有（engine01 的測試在 `backend/engine01_intent/tests/`），我們的 `tests/` 可原位保留。
**但有一顆地雷**：`backend/engine01_intent/tests/test_accuracy.py` 依其 README「跑一次會真的打 10 次 `codex exec`（約 2–3 分鐘，會消耗共用額度）」。
合併後任何人在 repo 根目錄裸跑 `pytest` 都會觸發它。→ 在 `pyproject.toml` 加 `[tool.pytest.ini_options] testpaths = ["tests"]`。

### 6.7 `data/`：最大的「在我機器上可以跑」風險
`data/` 在**兩邊的 `.gitignore` 都被忽略**。我們的 17,783 件目錄、預先算好的 embedding index、
`ot_items.npz` 快取**全部不在 git 裡**。接手的人 clone 下來跑 `uvicorn` 會直接在 `Catalog.load` 掛掉。
→ `backend/engine02_retrieval/README.md` 必須第一段就寫重建步驟（`scripts/engine02/prepare_catalog.py`、`precompute_ot_cache.py`）
或約定用 USB／雲端硬碟傳遞，並註明檔案大小。

### 6.8 `.env.example`
main 的沒有任何 `ENGINE02_*`。純新增一段：`ENGINE02_CATALOG`、`ENGINE02_ENCODER`、`ENGINE02_DEVICE`、
`ENGINE02_DEMO`、`ENGINE02_OT`、`ENGINE02_LLM`、`ENGINE02_PUBLIC_BASE`、`ENGINE02_PORT`。無衝突。

### 6.9 絕對不要動
`index.html`、`privacy.html`、`styles.css`、`assets/`、`.nojekyll`、`gh-pages` 分支（`CLAUDE.md` 明文禁止）。

---

## 7. 我無法核實的部分

- **團隊是否同意 `engine02/` 留在根目錄**。這與 `CLAUDE.md` 的 Repo 結構區塊直接衝突，需 ENGINE01 負責人簽核。
- **`concept_image` 改 `Optional`、`ProductCard` 加欄位是否會被接受**。`CLAUDE.md` 要求改 `shared/schemas.py` 前先知會其他引擎負責人。
- **誰負責把 ENGINE02 與 generation 合併成一個 `RetrievalResult`**。契約說「兩者並行、結果合併」，但 repo 裡沒有任何模組承擔，
  §4.4 是我的提案而非既成事實。
- **`origin/feature/frontend-user-ui` 是否為官方前端**。它是 Next.js（與 `docs/frontend.md` 的「不用 Next.js」相反）、
  全 mock、型別與契約不符。我只讀了 `types.ts` / `services/*.ts` / `package.json`，沒有讀 `components/`，
  也不知道團隊是否打算合併它。§5.2 的落差表需要跟前端負責人當面對。
- **`faiss-cpu` / `sentence-transformers` 與 `numpy>=2` 在隊友機器上是否真的解析失敗**。我沒有實跑 pip 解析，只從輪子相依慣例判斷。
- **port 8002 是否已被別人預約**、以及 demo 當天是否有部署網址要加進 `CORS_ALLOWED_ORIGINS`。
- **`origin/engine02-research` 遠端內容是否等同本地 HEAD**（我只讀了本地工作樹與 `HEAD`）。
- **`match_score` 的 `norm(B)` 參考尺該用哪個分位數**。需要在真實目錄上跑一次分佈才能定，本文只給方法。

---

## 8. 實作檢查清單（依序執行）

1. **取得三項簽核**（在動任何程式碼之前，這三項會改變後面所有步驟）：
   (a) `engine02/` 留在 repo 根目錄、`CLAUDE.md` Repo 結構區塊同步更新；
   (b) `backend/shared/schemas.py` 的兩項變更：`concept_image` 改 `Optional[ConceptImage] = None`、`ProductCard` 新增選填解釋欄位；
   (c) `engine02/` 的英文註解例外，寫進 `CLAUDE.md` 的「程式碼註解規則」。
2. `git fetch origin && git checkout -b engine02-integration origin/main`（**不要** merge `engine02-research`，無共同祖先）。
3. 把 `engine02/`、`tests/`、`pyproject.toml`、`reports/model_verification.*` 原位複製進來；
   `scripts/*.py` 複製到 `scripts/engine02/`；`docs/{engine02-design,engine02-literature-review,engine02-pipeline}.md`、
   `docs/contract/`、`docs/research/`、`docs/agents/` 直接複製（無同名衝突）。
4. `.gitignore` 改成 §6.3 的聯集，另補 `reports/latency/`。
5. `README.md` 保留 main 版；我們的中文 README 內容移到 `backend/engine02_retrieval/README.md`；
   在 `README.md`（英）與 `README_TW.md`（中）的 ENGINE 02 段落各補 3–5 行。
6. `pyproject.toml` 加 `[tool.pytest.ini_options] testpaths = ["tests"]`（避免裸跑 pytest 燒掉 codex 額度）。
7. 依 §2.3 更新 `backend/requirements.txt`：補 `numpy>=2`、`pandas>=2.2`、`pyarrow>=17`、`pillow>=11`、`httpx>=0.27`，
   把 `fastapi`→`fastapi>=0.115`、`pydantic>=2`→`pydantic>=2.9`、`uvicorn[standard]>=0.30`；
   加註 torch 安裝順序；提案刪除 `faiss-cpu` / `sentence-transformers`（附理由，等回覆再刪）。
8. `.env.example` 追加 `ENGINE02_*` 區塊（含 `ENGINE02_PUBLIC_BASE`，§4 的 `image_url` 靠它）。
9. 建 `backend/engine02_retrieval/__init__.py`（中文註解的空檔）。
10. 寫 `backend/engine02_retrieval/adapter.py`：`intent_to_request()`、`response_to_cards()`、`compute_match_score()`。
    **不 import `backend.shared.auth`**（`SESSION_SECRET` 會在測試環境炸開）。
11. 實作 §4.3 的 `match_score`：`0.5·hard_constraint_satisfaction + 0.5·norm(need_alignment)`，
    把 `need_alignment` 從 `engine02/eval/tasks.py` 提升為 serving 期計算；
    參考尺離線算好存進 `engine02/resources/`；一併回傳 `match_score_parts` 與 `match_score_prev_intent`。
12. 寫 `backend/engine02_retrieval/main.py`：`FastAPI(title="ENGINE02 - Retrieval & Ranking")`、
    CORS 改讀 `CORS_ALLOWED_ORIGINS`（與 engine01 一致，`allow_credentials=True`）、
    `POST /retrieve`（帶 `Depends(get_current_user)`，session key 用 `f"{user.sub}:{session_id}"`）、`GET /health`、
    `app.mount("/engine02", engine02.api.app)`。
13. 為 adapter 與 `/retrieve` 補測試（放 `tests/test_integration_contract.py`）：
    契約欄位齊全、`concept_image=None` 可通過驗證、`Σ reason_contributions == score`、
    `match_score` 在放寬條件時會下降（**明確測「會掉」**，這是誠實性的保險絲）。
14. 覆寫 `docs/engine02-retrieval.md`（現為骨架），並在 `docs/interface-contract.md` 的「待確認事項」下
    回填三項答案：`attributes` 的 key 清單、`score` 的範圍、`match_score` 的定義。
15. 端到端驗證：一個 terminal 跑 engine01（`:8000`），一個跑 `uvicorn backend.engine02_retrieval.main:app --port 8002`，
    以 `DEV_BYPASS_AUTH=true` 從 `/intent` 拿到 `Intent` 直接餵進 `/retrieve`，確認回來的 `RetrievalResult` 能通過 pydantic 驗證。
16. 跑 `scripts/engine02/integration_check.py`（22 項斷言）＋ 全部 `pytest tests/`，確認搬家後零迴歸。
17. 把 §5.2 的前端型別落差表拿去跟 `feature/frontend-user-ui` 的負責人當面對齊
    （`attributes` 的 `string[]` vs `dict`、缺 `match_score`／`concept_image`／`round`、全 mock 無 fetch）。
18. 確認 `data/` 的重建或傳遞方式，並在 demo 機器上實跑一次冷啟動（`GET /health` 檢查 `n_items` / `demo_mode` / `warm_ms`）。
19. 開 PR 前先跟使用者確認（`CLAUDE.md`：推共用遠端或開 PR 一律先確認）。
