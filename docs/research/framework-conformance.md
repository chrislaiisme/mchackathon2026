# ENGINE 02 併入團隊框架的整合計畫

比對本分支（`engine02-research`）與團隊 repo（`origin/main`、`origin/engine01-intent`），給出可執行的整合決策。
全部唯讀（`git show`），未修改程式碼、未切換分支。

**核對來源**：`origin/main` 的 `backend/engine01_intent/main.py`、`backend/shared/{auth,schemas}.py`、`backend/requirements.txt`、
`CLAUDE.md`、`README.md`、`.env.example`、`.gitignore`、`docs/{interface-contract,frontend,engine02-retrieval,engine03-feedback,validation-plan,hackathon-brief}.md`、
`index.html`、`scripts/{README.md,engine01-test-page/index.html}`；本分支的 `engine02/{api,contracts,pipeline,service,explain,intent_adapter}.py`、`pyproject.toml`、`.gitignore`、`README.md`。
`origin/engine01-intent` 與 `origin/main` 僅差 4 個 md 檔、20 行，本文以 `origin/main` 為準。

---

## 0. 最硬的兩件事

**(a) 兩個分支沒有共同祖先。**

```
git merge-base origin/main HEAD    → 無輸出，exit 1
root commit: f96ed8e (ours, 136 commits)  vs  eb9fff5 (main, 12 commits)
```

`git merge origin/main` 會直接拒絕（`refusing to merge unrelated histories`）。處置見 §6.1。

**(b) 實際重疊的已追蹤路徑只有兩個**（`comm -12` 逐檔比對）：`.gitignore`、`README.md`。
`docs/` 底下**沒有任何同名檔案**；本分支**沒有 CLAUDE.md**（已追蹤與工作目錄都沒有），
所以 CLAUDE.md 不是衝突，是「我們單方面繼承對方規則」（§6.4）。

---

## 1. Layout

### 1.1 engine01 的實際慣例

`backend/engine01_intent/main.py` docstring：`uvicorn backend.engine01_intent.main:app --reload`。
即**每個引擎資料夾各自持有一個 `FastAPI` 物件**（`app = FastAPI(title="ENGINE01 - Intent Understanding")`），
以 `backend.<engine>.main:app` 從 repo 根目錄啟動，共用 `backend/shared/` 的 schema 與 auth。
`backend/` 本身沒有 `__init__.py`（PEP 420 namespace package），只有 `backend/shared/__init__.py` 與 `backend/engine01_intent/__init__.py`。

### 1.2 決策：`engine02/` 留在根目錄當函式庫，薄服務層放 `backend/engine02_retrieval/`

**不搬套件**，理由可驗證：

- `engine02/api.py:49`、`compat_ot.py:24`、`complete_look.py:41`、`llm.py:14` 都寫死 `ROOT = Path(__file__).resolve().parents[1]`，
  預期自己在 repo 根目錄下一層。搬到 `backend/engine02_retrieval/` 後 `parents[1]` 指到 `backend/`，所有 `data/catalog/...` 預設路徑失效。
- `pyproject.toml` 的 `packages = ["engine02"]`、14 個測試檔、40+ 個腳本、`docs/contract/*.schema.json` 範例都以 `engine02` 為頂層匯入名。
- `origin/main` 上**沒有任何程式碼 import `backend.engine02_retrieval`**——那裡只有一份 README。
  沒有人依賴套件實體位置；真正被依賴的接縫是**啟動指令與 HTTP 介面**，那個接縫照 engine01 慣例做。

代價要講清楚：`CLAUDE.md` 的「Repo 結構」明文把 ENGINE02 放在 `backend/engine02_retrieval/`，
所以**必須拿到 ENGINE01 負責人（CLAUDE.md 作者）明確同意**並同步改那個區塊，不能默默違反。

### 1.3 要新增／修改的檔案

| 路徑 | 動作 | 內容 |
|---|---|---|
| `engine02/` + `pyproject.toml` | 原封搬入 | 不改 import、不改 `parents[1]`、不改測試 |
| `engine02/intent_adapter.py` | **已存在** | 平行工作中的 agent 已實作 `intent_to_request()`、`match_score()`、`response_to_retrieval_result()`（§4）。**目前是未 commit 的工作目錄變更，仍在異動中** |
| `backend/engine02_retrieval/__init__.py` | 新增 | 空檔＋中文註解（照 `backend/shared/__init__.py`） |
| `backend/engine02_retrieval/main.py` | 新增 | 對外 FastAPI app：`POST /retrieve`（`Intent` → `RetrievalResult`，呼叫 `intent_adapter`）、`GET /health`；CORS 讀 `CORS_ALLOWED_ORIGINS`；`Depends(get_current_user)`；`app.mount("/engine02", engine02.api.app)` 把既有 22 個端點原樣掛進來 |
| `backend/engine02_retrieval/README.md` | 覆寫佔位 | 指向 `engine02/`、啟動指令、**`data/` 重建步驟**（§6.7） |
| `backend/shared/schemas.py` | **只加不改**（§4） | `ProductCard` 加選填欄位；`RetrievalResult.concept_image` 改 `Optional` |
| `backend/requirements.txt` | 補齊（§2.3） | numpy/pandas/pyarrow/pillow/httpx 與版本下限 |
| `docs/engine02-retrieval.md` | 覆寫骨架 | 現為「負責人：待確認」的抄寫稿，換成指向 `docs/engine02-design.md` / `engine02-pipeline.md` |
| `scripts/engine02/`（由 `scripts/*.py` 移入） | 移動 | 避免 40 個 eval 腳本淹掉團隊的 `scripts/`；`scripts/README.md` 加一條 bullet |

---

## 2. 後端實際怎麼跑

### 2.1 一個引擎一個 app，沒有統一入口

`origin/main` 上只有 engine01 有 app。`engine03_feedback/`、`generation/`、`pinterest/`、`frontend/`、`validation/` **全部只有 README**。
沒有 aggregator、沒有 gateway、沒有任何模組負責把 ENGINE02 與 generation 的結果合併成一個 `RetrievalResult`——
但 `docs/interface-contract.md` §5 明寫「由 ENGINE02 和生成模組一起產出（兩者同一輪並行執行，結果合併成一個回應給前端）」。
**這個合併責任目前無人認領**，建議由 `backend/engine02_retrieval/main.py` 的 `/retrieve` 承擔（提案，需指派）。

### 2.2 Port、runner、部署

- engine01：`8000`（`scripts/engine01-test-page/index.html:75` 寫死 `API_BASE = "http://127.0.0.1:8000"`）。
- 前端／測試頁：`5173`（`.env.example:41` `CORS_ALLOWED_ORIGINS=http://localhost:5173`）。ENGINE02 取 `8002`，不衝突。
- **沒有 runner 腳本、沒有 Dockerfile、沒有 Procfile、沒有部署文件。**
  `docs/hackathon-brief.md:351` 明文：「Docker：非必要項目，demo 當天直接跑 `npm run dev`＋`uvicorn`」。
  → 啟動指令要自己寫進 `backend/engine02_retrieval/README.md`，不要期待別人的 runner。
- CORS 差異：engine01 用 `allow_origins=<env 清單>` + `allow_credentials=True`；
  我們 `engine02/api.py:163` 是 `allow_origins=["*"]`。薄服務層要改用 env 清單與 engine01 一致。

### 2.3 `backend/requirements.txt` vs `pyproject.toml`：逐項衝突

該檔**完全沒有版本上下限**（除 `pydantic>=2`、`openai>=1.40`）。

| 我們需要 | requirements.txt 現況 | 判定 |
|---|---|---|
| `numpy>=2.0` | **完全沒列**（靠 faiss / sentence-transformers 間接帶入） | **真衝突**。`faiss-cpu` 部分輪子相依 `numpy<2`；解析器一旦選到那組，`engine02/` 全線爆。必須顯式寫 `numpy>=2` |
| `pandas>=2.2` | **完全沒列** | 硬缺（`engine02/catalog.py` 直接用 DataFrame） |
| `pyarrow>=17.0` | **完全沒列** | **硬缺，會直接 crash**：目錄是 `items.parquet`，沒 pyarrow `Catalog.load` 起不來 |
| `pillow>=11.0` | **完全沒列** | 硬缺（`/visual-search`、`GET /images/{item_id}`） |
| `httpx>=0.27` | **完全沒列** | 硬缺（`fastapi.testclient`、`scripts/api_check.py`） |
| `fastapi>=0.115` | `fastapi`（無下限） | 補下限，否則新環境可能裝到舊版 |
| `pydantic>=2.9` | `pydantic>=2` | 下限提到 `2.9` |
| `uvicorn>=0.30` | `uvicorn[standard]`（無下限） | 補下限 |
| `torch>=2.4`（選配） | 未列，但 `sentence-transformers` **會間接帶入一個 torch** | **最陰的一個**：`pip install -r` 會靜默裝上 CPU 版 torch，等現場設 `ENGINE02_DEVICE=cuda` 才發現沒 CUDA 輪子。我們 pyproject 註解明寫「先裝對應機器的 torch build」，這個順序要求要寫進 requirements.txt 註解 |
| `rank-bm25` | 列為正式相依 | 對我們只是**測試相依**（`tests/test_sparse.py` 拿它逐分比對自寫 postings）。可留，註明用途 |
| `sentence-transformers`、`faiss-cpu` | 列為 ENGINE02 相依 | **我們兩個都沒用**（dense 走 open_clip/transformers，檢索走 numpy + 自寫 BM25）。只會拖慢安裝並製造 numpy 衝突，建議刪除，需團隊同意 |
| `openai>=1.40` | 有 | 相容（LLM 改寫是選配，`ENGINE02_LLM=none` / `ENGINE02_DEMO=1` 可全關） |

Python 版本：我們 `requires-python = ">=3.11"`，`CLAUDE.md` 寫「Python 3.11+」，**無衝突**。
`CLAUDE.md` 明文「不要每個引擎各自開一份 venv／requirements」→ `pyproject.toml` 保留（`pip install -e .` 是跑測試的方式），
但把上表下限同步進 `backend/requirements.txt`，並註明兩邊要同步。

---

## 3. Auth

**會。** `backend/shared/auth.py` + `engine01_intent/main.py`：前端拿 Google `credential` → `POST /auth/google` →
`verify_google_id_token()` → 簽自家 HMAC session token（7 天）→ 之後每個請求帶 `Authorization: Bearer <token>`，
由 `Depends(get_current_user)` 解出 `UserProfile`。`DEV_BYPASS_AUTH=true` 全部跳過，固定回 `dev-local-user`。

**我們需要嗎？需要，但理由不是「防駭客」。** `engine02/api.py` 目前完全沒有 auth，且 `allow_origins=["*"]`。不加的後果：

1. **session 身分會對不上（真正的功能問題）**。engine01 用 `(user.sub, session_id)` 當 key
   （`session_store.get_or_create(user.sub, request.session_id)`），而我們的 `Engine02Request.session_id` 是**前端自己傳的字串**。
   兩位評審同時操作、撞到同一個 `session_id`，ENGINE02 這側的 `FeedbackState`／`ProfilePrior` 會互相污染，engine01 那側不會——
   症狀是「意圖對但推薦莫名其妙」，現場最難 debug 的那種。
2. **偏好可被覆寫**：`ProfilePrior.weights`、`FeedbackState.design_weight_delta` 都由請求體帶入，沒有身分綁定等於誰都能替別人設先驗。
3. **demo 本身不會壞**。誠實講：不加 auth，`/retrieve` 照樣回卡片，評審看不出來。這是正確性與治理問題，不是「能不能跑」。

作法：auth 只加在**薄服務層**的 `/retrieve`，並在 `intent_to_request()` 呼叫端把 session key 命名空間化成 `f"{user.sub}:{session_id}"`；
內層 `engine02.api` 的端點維持無 auth 但 bind `127.0.0.1`（或掛在同一個 `Depends` 下）。

**陷阱**：`backend/shared/auth.py:_session_secret()` 在 `SESSION_SECRET` 未設時直接 `raise RuntimeError`。
所以 `engine02/intent_adapter.py` **不可以** import auth，否則 250 個測試在沒有 `.env` 的機器上整批掛掉。auth 只出現在 `main.py` 的 route 簽名裡。

---

## 4. 契約：`RetrievalResult` 每個欄位

`backend/shared/schemas.py:180–197` 是真相來源。
**現況**：`engine02/intent_adapter.py:318 response_to_retrieval_result()` 已經把映射寫好了，以下是對它的核對與必要修正。

| 欄位 | 來源 | 備註 |
|---|---|---|
| `session_id` / `round` | `Engine02Response.session_id` / `.round` | 直通 |
| `products[].product_id` | `RankedItem.item_id` | 直通 |
| `products[].image_url` | `f"{image_base}/{item_id}"`，預設 `/images` | 對應既有 `GET /images/{item_id}`（`api.py:662`，回 `FileResponse`）。**相對路徑只在同源時有效**——前端在 `:5173`、我們在 `:8002`，必須由 `main.py` 傳入絕對的 `ENGINE02_PUBLIC_BASE`，否則前端拿到 404 |
| `products[].title` | `RankedItem.title` | 直通 |
| `products[].attributes` | `category`/`subcategory`/`color`/`occasion`/`season`/`gender`，跳過空值，全轉字串 | 這正好回答 `docs/interface-contract.md` 結尾「`attributes` 具體要放哪些 key」那條待確認事項——由真實目錄欄位決定，不是猜的 |
| `products[].score` | `RankedItem.score`（原始加總分） | **要談**：我們的 score 是 z-score 加總，**不是 0–1，可以是負的**；`interface-contract.md` 範例寫 `0.91`，前端很可能當百分比畫進度條。建議 UI 顯示名次而非百分比，並在 schema docstring 註明範圍 |
| `products[].reason` | 目前取 `it.reasons[0]` | **見 §4.1，建議改** |
| `concept_image` | 固定 `None` | **見 §4.2，目前會 500** |
| `match_score` | `match_score()` 計算 | **見 §4.3** |
| `engine02`（額外 key） | 完整證據包 | **見 §4.1 的警告：會被靜默丟掉** |

### 4.1 `reason` 是單一字串，我們的解釋是有分數的貢獻清單

**建議把 `reasons[0]` 改成 `it.explanation`。** `RankedItem.explanation`（`contracts.py:269`）**本來就已經是單一字串**：
由 `engine02/explain.py:template_reasons()` 產模板句，LLM 改寫通過事實查核才替換，否則退回模板
（`explanation_source: "llm" | "template"`）。取 `reasons[0]` 只拿到第一個子句，**丟掉整段已驗證的敘述與 LLM 改寫成果**——
那是我們花力氣做事實查核的地方。

**更關鍵的警告**：`response_to_retrieval_result()` 目前把所有證據放在一個額外的 `"engine02"` key。
**FastAPI 的 `response_model=RetrievalResult` 會靜默過濾掉不在 model 上的欄位**——沒有錯誤訊息，前端什麼都收不到。
所以證據要活下來，**必須改 `backend/shared/schemas.py`**（只加不改，向後相容）：

```python
class ReasonContribution(BaseModel):
    term: str            # "dense" / "design:structured_shoulders"
    group: str           # dense | bm25 | design | compat | freshness | penalty | rerank
    label: str           # 中文顯示字串（explain.py 的 GROUP_LABEL / element_labels）
    contribution: float  # weight * normalized
    necessary: bool | None = None    # 拿掉這一項會掉出 top-k
    sufficient: bool | None = None   # 單靠這一項就足以留在 top-k

# ProductCard 新增（全部選填，預設空）：
    reason_contributions: list[ReasonContribution] = []
    reason_mode: str | None = None            # sufficient / necessary / contrastive
    explanation_source: str | None = None     # "llm" | "template"
    attribute_notes: list[str] = []
    margin_vs_cutoff: float | None = None
    relaxed_constraints: list[str] = []       # 來自 ConstraintReport.relaxed

# RetrievalResult 新增：
    match_score_detail: dict | None = None
    engine02_diagnostics: dict | None = None  # constraint_report / metrics / arm / encoder / timings
```

並在 docstring 釘住不變式：**`sum(c.contribution) == score`**（測試已釘住）。
不改 schema 而只多塞 key，等於「理由就是分數分解本身」這個賣點在契約邊界蒸發，而且無聲無息。

### 4.2 `concept_image`：目前是必填，回 `None` 會直接 500

`RetrievalResult.concept_image: ConceptImage` **沒有預設值**。
`response_to_retrieval_result()` 現在硬填 `None`，一旦包成 `RetrievalResult` 就會 `ValidationError`。
而 `backend/generation/` 在 `origin/main` 上只有一份 README。我們產不出概念圖（我們只**消費**它：
`POST /concept-image/nearest`、`FeedbackState.concept_image_embedding`）。

```python
    concept_image: Optional[ConceptImage] = None
```

一行、向後相容，**但必須先知會 ENGINE01 負責人**（`CLAUDE.md`：改 `shared/schemas.py` 欄位前要先知會）。
前端在 `None` 時只顯示商品側即可——`docs/frontend.md` 說兩者「並排呈現」，少一邊是版面問題，不是崩潰。

### 4.3 `match_score`：repo 裡有沒有定義？

**`origin/main` 上有文字定義，沒有公式，也沒有任何實作。** 完整搜尋（`git grep -n "match_score\|符合度" origin/main`）：

- `backend/shared/schemas.py:196–197` — 只有型別 `float` 與一行 docstring，無範圍、無算法。
- `docs/interface-contract.md:139` — 「回饋前後都會顯示的符合度分數」，範例 `0.62`；
  **第 146 行自己列為待確認**：「`match_score` 的單位／範圍——目前都是 0–1 的浮點數，請確認」。
- `docs/engine03-feedback.md:27`、`docs/validation-plan.md:12`、`docs/hackathon-brief.md:272` — 三處口徑一致的**散文定義**：
  「目前結果跟目前結構化意圖的符合程度（例如意圖要求的顏色／場合／預算條件，**推薦清單裡實際符合的比例**）」。
- `origin/main` 上**沒有任何 `.py` 計算它**。依 `validation-plan.md:12`，負責人是「ENGINE02/03 加前端」。

**我們這側已經有實作**：`engine02/intent_adapter.py:257 match_score()` ——
對每個使用者說出口的要求（`category`/`color`/`occasion`/`season`/`gender` 的硬條件值，加上
`feedback.design_adjust_steps` 指名的設計要素軸）算出卡片滿足比例，再取平均，回傳逐項 breakdown。
這**忠實實作了散文定義**，並且 docstring 明寫「it can go down…A number that only ever rises is a lie」。核可。

需要補強三點：

1. **飽和問題**。硬條件是先過濾再展示，滿足率天然接近 1.0
   （`tests/test_engine02.py:316`、`test_attribute_fill.py:166` 都斷言 `hard_constraint_satisfaction == 1.0`）。
   台上可能出現 100% → 100%，說不出 62%→89% 的故事。design 軸那一項是解藥，但只在使用者給過回饋後才存在（第一輪沒有）。
   → 開場第一輪可納入 `needs` 對齊項（`engine02/eval/tasks.py:334` 的 `need_alignment` 已有離線實作），
   並用**離線算好的固定參考尺**標準化（存進 `engine02/resources/`）。
2. **倖存者偏差**：滿足率是在硬過濾**之後**的集合上算的。若 `ConstraintReport.relaxed` 非空（放寬過條件），
   分數是對**放寬後**的條件算的，此時必須在畫面上標出放寬了什麼，否則 100% 是假的。→ 隨 `match_score_detail` 一起送 `relaxed`。
3. **移動球門**：第 2 輪的意圖已被回饋改過，「新意圖 vs 新結果」對比「舊意圖 vs 舊結果」，上升可能全來自意圖變寬鬆。
   → 同時回傳 `match_score_prev_intent`（第 N 輪卡片、用第 N−1 輪意圖評）。只有前者漲、後者沒漲，就是球門移動，我們自己要說出來。

**什麼情況下這個數字就是在說謊**（現行實作都避開了，寫下來是為了守住）：

- 每輪用當輪 slate 重新 min-max → 最好的一張永遠 100%，分數必然上升。最常見的造假法。
- 拿排序分數（`RankedItem.score`）當 match_score → 循環論證：ENGINE03 調高權重，分數依定義必然變高，證明不了任何事。
  `RoundMetrics` docstring 的「computed from item attributes, never from the score」就是為了擋這個。
- 把不滿足的卡片從 slate 移除後再算滿足率而不揭露（同上第 2 點）。
- **不允許下降**。某輪回饋讓分數掉了，就顯示它掉了。只會上升的數字不是指標，是動畫。

---

## 5. 前端實際消費什麼

### 5.1 `origin/main` 上沒有前端

- `frontend/` 只有 README.md（「負責人：待確認」「建 repo 骨架時順便建立的佔位資料夾」）。
- 根目錄 `index.html` / `privacy.html` / `styles.css` 是**Pinterest App 審核用的隱私權政策靜態網站**，
  `CLAUDE.md` 明文「不要重新調整或刪除」，全檔 79 行，**沒有任何 fetch**。
- 唯一呼叫 API 的 JS 是 `scripts/engine01-test-page/index.html`：只打 `/auth/google` 與 `/intent`，帶 `Authorization: Bearer`。
  **它不消費 `RetrievalResult`。**
- `docs/frontend.md` 的規格（`ProductCard[]` + `ConceptImage` 並排 + `match_score`、輪次對比要凸顯 `match_score` 變化）
  目前是**紙上規格，沒有實作**。

### 5.2 但有一個分支已經在寫前端，型別對不上

`origin/feature/frontend-user-ui`（不在指定閱讀範圍，唯讀查證後列出供交叉確認）已有完整 Next.js 16 + React 19 + shadcn 應用。
`frontend/lib/types.ts`：

```ts
export interface FashionRecommendation {
  id, name, imageUrl, explanation, attributes: string[], priceBand: string, confidence: number, feedback?
}
```

落差：`name` vs `title`、`explanation` vs `reason`、`confidence` vs `score`、
**`attributes` 是 `string[]` 而契約是 `dict[str,str]`**、多出 `priceBand`、
**完全沒有 `match_score`、`concept_image`、`round`**（`git grep -i "matchscore\|concept" -- frontend` 零命中）。
`lib/services/auth.ts` 與 `conversations.ts` **全部是 localStorage mock**，`signInWithGoogle()` 直接寫入寫死的 `demoUser`，
整個 `frontend/` **沒有任何 fetch 呼叫後端**。技術選型也與 `docs/frontend.md`（「React + Vite，不用 Next.js／SSR」）相反。

### 5.3 會被靜默丟掉的

即使前端接上契約，以下算得出來但 `RetrievalResult` 沒有位置的東西會被 `response_model` 濾掉：
`contributions`、`need_contributions`、`design_scores`、`margin_vs_cutoff`、
`constraint_report`（**放寬了什麼**——可解釋性的核心，丟掉最可惜）、`metrics.feedback_violations`、
`/view` 的全部面板（說了／沒說、Div@k、來源、輪次 diff）、`/facets` 的 2–3 群讀法。
§4.1 的選填欄位救回最重要的部分；其餘靠前端直接打 `POST /engine02/view`（掛載路徑）取得。

---

## 6. 合併風險與處置

**6.1 無共同祖先（最高風險）** — `--allow-unrelated-histories` 技術上可行，但會產生沒人看得懂的合併點。
建議 `git checkout -b engine02-integration origin/main`，把本分支檔案樹依 §1.3 複製進去，少數幾個有意義的 commit。
`engine02-research` 保持 push 在遠端不刪，README 加一行連結留住 136 個 commit 的來歷。

**6.2 `README.md`** — main 的是**英文交付物**（開頭明寫「stays in English per the competition's deliverable requirement」），
配 `README_TW.md`，`CLAUDE.md` 要求兩份同步。我們的是 97 行中文。
→ 保留 main 的兩份；我們的搬去 `backend/engine02_retrieval/README.md`（覆寫佔位），在 `README.md` 與 `README_TW.md` 的 ENGINE 02 段落各補 3–5 行（兩邊都要改）。

**6.3 `.gitignore`** — 取聯集。共有 `.env`、`__pycache__/`、`*.pyc`、`.venv/`、`data/`。
我們獨有 `models/`、`artifacts/`、`third_party/`、`reports/{ablation,server,agents,demo,llm_paraphrase}/`；
main 獨有 `*.egg-info/`、`.pytest_cache/`、`node_modules/`、`frontend/dist/`、`*.faiss`、`*.chroma/`、
`backend/pinterest/cache/`、`backend/generation/output/`、`.DS_Store`、`.vscode/`、`.idea/`、`.claude/`。
順帶：工作目錄現有未追蹤且未忽略的 `engine02.egg-info/`（聯集後被 `*.egg-info/` 蓋掉）與 `reports/latency/`（要自己補一條）。

**6.4 `CLAUDE.md`：不是衝突，是繼承** — 本分支沒有 CLAUDE.md，合併後自動受 main 約束，其中兩條我們現在就違反：
(a)「**所有 `.py` 檔都要寫足夠的註解……註解用中文寫**」——我們 60+ 個模組是英文註解，兩天內全翻不現實且製造大量無意義 diff。
**建議明確協商一條例外寫進 CLAUDE.md**（「`engine02/` 因既有規模與測試覆蓋維持英文註解」），不要默默違反。
(b)「不要每個引擎各自開一份 venv／requirements」——見 §2.3。另外「Repo 結構」與「介面契約」兩個區塊都要因本文決定而更新。

**6.5 `docs/`** — **無同名檔案衝突**（已逐檔比對）。但 `docs/contract/*.schema.json`（我們）與
`docs/interface-contract.md` + `backend/shared/schemas.py`（他們）是兩套會彼此矛盾的真相來源。
→ 在我們的 schema 旁註明：`backend/shared/schemas.py` 管跨引擎邊界（`Intent` / `RetrievalResult`），
`docs/contract/*.schema.json` 管 ENGINE02 內部的 `/rank` 請求回應，由 `engine02/intent_adapter.py` 橋接。
`docs/research/` 是新子樹，不衝突。

**6.6 `scripts/` 與 `tests/`** — 無同名衝突，但 40+ 個 eval 腳本倒進去會淹掉 `scripts/` → 移到 `scripts/engine02/`。
`tests/` 可原位保留。**地雷**：`backend/engine01_intent/tests/test_accuracy.py` 依其 README「跑一次會真的打 10 次 `codex exec`
（約 2–3 分鐘，會消耗共用額度）」。合併後任何人在根目錄裸跑 `pytest` 都會觸發。
→ `pyproject.toml` 加 `[tool.pytest.ini_options] testpaths = ["tests"]`。

**6.7 `data/`：最大的「在我機器上可以跑」風險** — `data/` 在**兩邊 `.gitignore` 都被忽略**。
17,783 件目錄、預算好的 embedding index、`ot_items.npz` 快取**全部不在 git 裡**。
接手的人 clone 後跑 `uvicorn` 會直接在 `Catalog.load` 掛掉。
→ `backend/engine02_retrieval/README.md` 第一段就要寫重建步驟或約定離線傳遞方式，並註明檔案大小。

**6.8 `.env.example`** — main 的沒有任何 `ENGINE02_*`。純新增一段：`ENGINE02_CATALOG`、`ENCODER`、`DEVICE`、`DEMO`、`OT`、`LLM`、`PUBLIC_BASE`、`PORT`。無衝突。

**6.9 絕對不要動** — `index.html`、`privacy.html`、`styles.css`、`assets/`、`.nojekyll`、`gh-pages` 分支（`CLAUDE.md` 明文禁止）。

---

## 7. 我無法核實的部分

- **團隊是否同意 `engine02/` 留在根目錄**（與 `CLAUDE.md` Repo 結構直接衝突，需 ENGINE01 負責人簽核）。
- **`concept_image` 改 `Optional`、`ProductCard` 加欄位是否會被接受**（`CLAUDE.md` 要求改 `shared/schemas.py` 前先知會）。
- **誰負責把 ENGINE02 與 generation 合併成一個 `RetrievalResult`**。契約說「並行、合併」，但 repo 裡沒有模組承擔；§2.1 是提案。
- **`engine02/intent_adapter.py` 的最終形狀**。它是另一個平行進行中的 agent 的**未 commit 工作目錄變更**
  （`git status` 顯示 `engine02/{contracts,explain,intent_adapter,pipeline}.py` 與 `tests/test_intent_adapter.py` 皆為 `M`），
  本文 §4 的核對是對「我讀到的那一版」。落地前要重讀。
- **`origin/feature/frontend-user-ui` 是否為官方前端**。Next.js（與 `docs/frontend.md` 相反）、全 mock、型別不符。
  我只讀了 `types.ts` / `services/*.ts` / `package.json`，沒讀 `components/`，也不知道團隊是否打算合併它。
- **`faiss-cpu` / `sentence-transformers` 與 `numpy>=2` 在隊友機器上是否真的解析失敗**。未實跑 pip 解析，僅依輪子相依慣例判斷。
- **port 8002 是否已被預約**，以及 demo 當天是否有部署網址要加進 `CORS_ALLOWED_ORIGINS`。
- **`match_score` 第一輪的 `need_alignment` 參考尺該用哪個分位數**。需在真實目錄上跑一次分佈才能定，本文只給方法。

---

## 8. 實作檢查清單（依序執行）

1. **取得三項簽核**（會改變後面所有步驟，先做）：(a) `engine02/` 留在 repo 根目錄、`CLAUDE.md` Repo 結構同步更新；
   (b) `backend/shared/schemas.py` 兩項變更：`concept_image` 改 `Optional`、`ProductCard`/`RetrievalResult` 加選填欄位；
   (c) `engine02/` 的英文註解例外寫進 `CLAUDE.md`。
2. 等 `engine02/intent_adapter.py` 的平行變更 commit 完成後再開始，並重讀該檔（§7）。
3. `git fetch origin && git checkout -b engine02-integration origin/main`（**不要** merge，無共同祖先）。
4. 複製：`engine02/`、`tests/`、`pyproject.toml`、`reports/model_verification.*` 原位；`scripts/*.py` → `scripts/engine02/`；
   `docs/{engine02-design,engine02-literature-review,engine02-pipeline}.md`、`docs/{contract,research,agents}/` 直接複製（無同名衝突）。
5. `.gitignore` 改成 §6.3 的聯集，另補 `reports/latency/`。
6. `README.md` 保留 main 版；我們的中文 README 移到 `backend/engine02_retrieval/README.md`；`README.md` 與 `README_TW.md` 各補 ENGINE 02 段落。
7. `pyproject.toml` 加 `[tool.pytest.ini_options] testpaths = ["tests"]`（避免裸跑 pytest 燒掉 codex 額度）。
8. 依 §2.3 更新 `backend/requirements.txt`：補 `numpy>=2`、`pandas>=2.2`、`pyarrow>=17`、`pillow>=11`、`httpx>=0.27`；
   `fastapi>=0.115`、`pydantic>=2.9`、`uvicorn[standard]>=0.30`；加註 torch 安裝順序；提案刪除 `faiss-cpu` / `sentence-transformers`（附理由）。
9. `.env.example` 追加 `ENGINE02_*` 區塊（含 `ENGINE02_PUBLIC_BASE`，§4 的 `image_url` 靠它）。
10. 依 §4.1 修改 `backend/shared/schemas.py`（`ReasonContribution` + `ProductCard` 選填欄位 + `RetrievalResult.match_score_detail` / `engine02_diagnostics` + `concept_image` 改 `Optional`）。
11. 修 `engine02/intent_adapter.py:response_to_retrieval_result()`：`reason` 改用 `it.explanation`；
    把 `"engine02"` 那包搬進新增的具名欄位（否則被 `response_model` 靜默丟掉）；`image_base` 改吃絕對 URL。
12. 依 §4.3 補強 `match_score()`：第一輪納入 `need_alignment`（離線固定參考尺，存 `engine02/resources/`）、
    隨附 `constraint_report.relaxed`、加算 `match_score_prev_intent`。
13. 建 `backend/engine02_retrieval/__init__.py`（中文註解空檔）。
14. 寫 `backend/engine02_retrieval/main.py`：`FastAPI(title="ENGINE02 - Retrieval & Ranking")`、
    CORS 改讀 `CORS_ALLOWED_ORIGINS`（`allow_credentials=True`，與 engine01 一致）、
    `POST /retrieve`（`Depends(get_current_user)`，session key 用 `f"{user.sub}:{session_id}"`）、`GET /health`、
    `app.mount("/engine02", engine02.api.app)`。**不在 module level import auth 以外的東西**。
15. 補契約測試（`tests/test_integration_contract.py`）：欄位齊全、`concept_image=None` 可通過驗證、
    `Σ reason_contributions == score`、**`match_score` 在加入目錄給不出的要求時會下降**（誠實性的保險絲）。
16. 覆寫 `docs/engine02-retrieval.md`，並在 `docs/interface-contract.md` 的「待確認事項」回填三項答案：
    `attributes` 的 key 清單、`score` 的範圍、`match_score` 的定義。
17. 端到端驗證：一個 terminal 跑 engine01（`:8000`），一個跑 `uvicorn backend.engine02_retrieval.main:app --port 8002`，
    以 `DEV_BYPASS_AUTH=true` 從 `/intent` 拿到 `Intent` 餵進 `/retrieve`，確認回應能通過 pydantic 驗證。
18. 跑 `scripts/engine02/integration_check.py`（22 項斷言）＋ 全部 `pytest tests/`，確認搬家零迴歸。
19. 把 §5.2 的前端型別落差表拿去跟 `feature/frontend-user-ui` 負責人當面對齊。
20. 確認 `data/` 的重建或傳遞方式，在 demo 機器上實跑一次冷啟動（`GET /health` 檢查 `n_items` / `demo_mode` / `warm_ms`）。
21. 開 PR 前先跟使用者確認（`CLAUDE.md`：推共用遠端或開 PR 一律先確認）。
