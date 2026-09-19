# mcp_servers/catalog/

負責線：線 2｜商品推薦與流行趨勢
對應功能：FR-005 Product Recommendation；FR-010 中的三種推薦做法比較

## 負責內容

- 以 Polyvore Outfits Dataset 為商品庫
- 依風格相似度與精確條件（顏色、價格區間、季節、尺寸）檢索
- 合併風格、穿搭相容性、使用者偏好與流行趨勢重新排序，並保留排序依據
- 圖片相似度計算：概念圖併入推薦、驗證流程使用

## 介面

- 需要：結構化意圖（線 1）、概念圖（線 3）、偏好權重（線 4）
- 提供：推薦結果與排序依據（線 4）、圖片相似度計算（線 1）

## 整合前先用

手寫的結構化意圖與固定的偏好權重（`contracts/samples/`）。

資料集本體放在 `data/polyvore/`（本機，不進版控）。

目前狀態：尚未開始。

---

（以下併自 `backend/engine02_retrieval/README.md`）

# ENGINE02 — 檢索與排序（已實作）

**負責人：ENGINE 02。** 這份取代原本的骨架摘要。實作完成、測試 258 項全綠、在 cfda4 GPU 與純 CPU 筆電上都驗收過。

- 設計與全部實驗（§3.1–§3.35）：[`docs/engine02-design.md`](../../docs/engine02-design.md)
- 管線、現場腳本、檢查清單：[`docs/engine02-pipeline.md`](../../docs/engine02-pipeline.md)
- 介面轉接的實況調查：[`docs/research/engine01-output-reality.md`](../../docs/research/engine01-output-reality.md)、[`docs/research/framework-conformance.md`](../../docs/research/framework-conformance.md)

## 怎麼跑

先照 `data/README.md` 步驟 0、1 裝好環境、建好 `data/catalog/kagl`。然後從 repo 根目錄：

```bash
# 等級 A：沒有 GPU、沒裝 torch（只需要 [data,dev]）
ENGINE02_CATALOG=data/catalog/hm_filled ENGINE02_ENCODER=hash ENGINE02_DEMO=1 \
ENGINE02_PUBLIC_BASE=http://localhost:8002/engine02 CORS_ALLOWED_ORIGINS=http://localhost:5173 \
uvicorn mcp_servers.catalog.main:app --host 0.0.0.0 --port 8002

# 等級 B：真正的 demo 編碼器（先裝 torch，再 uv pip install -e ".[models]"；CPU 也能跑）
ENGINE02_CATALOG=data/catalog/hm_filled ENGINE02_ENCODER=marqo-fashionSigLIP ENGINE02_DEMO=1 \
ENGINE02_PUBLIC_BASE=http://localhost:8002/engine02 CORS_ALLOWED_ORIGINS=http://localhost:5173 \
uvicorn mcp_servers.catalog.main:app --host 0.0.0.0 --port 8002
```

**不設 `ENGINE02_ENCODER` 時預設是 `marqo-fashionSigLIP`，沒裝 torch 會啟動失敗**
（`ModuleNotFoundError: No module named 'torch'`）。`ENGINE02_DEVICE` 預設 `auto`，不要寫死 `cuda`。
`ENGINE02_OT=1`（OutfitTransformer）需要 `third_party/` 的權重，缺了會退回圖片相似度而不會失敗。

> **2026-09-20，ENGINE01 負責人補上 `ENGINE02_CATALOG`**：上面兩個等級原本都沒帶這個變數，
> 會落到 `engine02/api.py` 的預設值 `data/catalog/kagl`（5,000 件、比賽前的舊商品庫）。
> `data/README.md` 步驟 5 另外準備了 `data/catalog/hm_filled`（9,870 件 H&M，那份文件明講
> 「demo 建議用這個」），但只有那一處提到，這裡跟 `CLAUDE.md`／`.env.example` 一起校正成
> 預設帶上它。第一次用要先跑 `python scripts/fetch_catalog_images.py --catalog
> data/catalog/hm_filled` 補圖片（`items.parquet`／向量索引已經隨 repo 附上）。

> **2026-09-19，ENGINE01 負責人實測發現並修正：兩個等級的 `ENGINE02_PUBLIC_BASE` 都要帶
> `/engine02` 這段路徑**——原本兩邊都寫 `http://localhost:8002`（沒有 `/engine02`），
> 對著真實跑起來的服務＋真瀏覽器測過，商品圖網址會 404。這支 app 是用
> `app.mount("/engine02", ...)` 掛的，`intent_adapter.py` 拿
> `ENGINE02_PUBLIC_BASE + "/images/<id>"` 組圖片網址時沒有算進這段 mount 前綴，
> 真正能連到的路徑是 `/engine02/images/<id>`，不是 `/images/<id>`。已經改成上面這樣，
> 兩邊都測過確認能載出真圖。

| 端點 | 用途 |
|---|---|
| `POST /retrieve` | **ENGINE 01 的 `Intent` → `RetrievalResult`**（`docs/interface-contract.md`） |
| `GET /health` | 商品庫、編碼器、預熱狀態 |
| `/engine02/*` | ENGINE 02 完整 API 原樣掛載（`/rank`、`/view`、`/facets`、`/complete-look`、`/visual-search`、缺口盤…） |

`ENGINE02_CATALOG` 預設就是 `data/catalog/kagl`，那是 `scripts/prepare_catalog.py` 一行就能建出來的
商品庫。其他腳本的說明裡出現的 `kagl_polyvore_filled` 是屬性補值實驗用的，**要另外建**（見
`data/README.md`），一般開發與 demo 不需要。

`ENGINE02_DEMO=1` 保證服務路徑不連網、不等 LLM。沒有 GPU 也能跑（純 CPU `/rank` p50 111 ms）。

## 套件為什麼留在根目錄 `engine02/`

`engine02/{api,compat_ot,complete_look,llm}.py` 都用 `ROOT = Path(__file__).resolve().parents[1]`
解析 `data/catalog/...`。搬進 `backend/engine02_retrieval/` 會讓 `parents[1]` 指到 `backend/`，
所有預設資料路徑、14 個測試檔、40+ 個腳本與已發佈的 JSON Schema 全部失效。
團隊真正依賴的接縫是**啟動指令與 HTTP 介面**，這個檔案就是那個接縫。

`main` 上同時存在 `backend/engine02_retrieval/main.py`，兩份服務層內容等價（同樣的
`/retrieve`、同樣的 ENGINE 03 ops 套用、同樣把 `/engine02/*` 掛上去）。測試與
`scripts/simulate_sessions.py` 優先 import 這一份，缺了才退回 `backend/` 那份。
**改動其中一份時另一份要一起改**——這是兩套結構並存的代價，等結構收斂後應該只留一份。

> 這一點與 `CLAUDE.md` 的「Repo 結構」寫法不同，**需要 ENGINE 01 負責人確認**後同步更新該段落。

## 需要團隊改的三件事（都只加不改、向後相容）

### 1. `RetrievalResult.concept_image` 目前是必填，我們填不出來

概念圖屬於 `backend/generation/`；我們只**消費**它（`POST /engine02/concept-image/nearest`、
`FeedbackState.concept_image_embedding`）。現在回 `null`，包成 `RetrievalResult` 會 `ValidationError`。

```diff
 class RetrievalResult(BaseModel):
     session_id: str
     round: int
     products: list[ProductCard]
-    concept_image: ConceptImage
+    concept_image: Optional[ConceptImage] = None
     match_score: float
```

我們不會為了滿足型別而生一張假圖。

### 2. `ProductCard` 只有一個 `reason: str`，會把可解釋性丟掉

我們每張卡片的分數分解**加起來剛好等於總分**，這是整個專案的賣點。
`reason` 我們填的是**通過事實查核的完整敘述**（`RankedItem.explanation`），
但逐項貢獻需要欄位才活得下來——**FastAPI 的 `response_model` 會靜默丟掉 model 上沒有的欄位**。

```diff
+class ReasonContribution(BaseModel):
+    term: str                 # "dense" / "design:structured_shoulders"
+    group: str                # dense | bm25 | design | compat | freshness | critique | penalty
+    contribution: float       # 不變式：sum(contribution) == ProductCard.score
+    cited: bool = False       # 有沒有被寫進卡片理由
+
 class ProductCard(BaseModel):
     product_id: str
     image_url: str
     title: str
     attributes: dict[str, str] = Field(default_factory=dict)
     score: float
     reason: str
+    reason_contributions: list[ReasonContribution] = Field(default_factory=list)
+    explanation_source: Optional[str] = None      # "llm"（通過查核的改寫）或 "template"
```

### 3. `requirements.txt` 缺的套件會直接讓我們載不起來

`numpy`、`pandas`、`pyarrow`、`pillow`、`httpx` 目前都沒列；**沒有 `pyarrow` 就讀不了 `items.parquet`**。
另外 `faiss-cpu` 與 `sentence-transformers` 我們兩個都沒用，而 `faiss-cpu` 的部分輪子相依 `numpy<2`，
和我們的 `numpy>=2` 直接衝突。我們的清單是根目錄 `pyproject.toml`。

## 合併注意事項

- **兩個分支沒有共同祖先**（`git merge-base` 無輸出），`git merge` 會拒絕。
  建議從 `origin/main` 開 `engine02-integration`，把檔案樹複製進去再提 PR。
  實際重疊的已追蹤路徑只有 `.gitignore` 與 `README.md` 兩個。
- **`data/` 兩邊都被 gitignore**：17,783 件商品庫與向量索引不在 git 裡，
  clone 下來要先跑 `scripts/prepare_catalog.py`（或直接複製既有的 `data/catalog/`），否則 `Catalog.load` 會掛。
- **合併後不要裸跑 `pytest`**：`backend/engine01_intent/tests/test_accuracy.py` 會真的呼叫 10 次
  `codex exec`，燒團隊共用額度。我們的測試請跑 `pytest -q tests`。

## 給 ENGINE 03 的

回饋照 `docs/contract/engine03_feedback.schema.json` 送進 `/engine02/rank` 的 `feedback`；
`/retrieve` 也吃同一份 `feedback`。第二輪請一併送 `prev_intent`，我們會同時回
「用本輪意圖評」與「用上一輪意圖評」兩個 match_score——
**只有前者上升代表是意圖變寬鬆，不是結果變好**，這個對照是我們自己要求要顯示的。

---

## 引擎實作的位置

檢索排序的實作是 repo 根目錄的 `engine02/`，**刻意不搬進這個資料夾**：它是一個 Python package，`api.py`、`ltr.py`、`tests/`、`scripts/` 有多處絕對 import（`from engine02.x import ...`），`pyproject.toml` 也寫死 `packages = ["engine02"]`。搬動會破壞這些引用，而且會跟持續進行中的開發不斷衝突。

包裝成 MCP 工具服務不需要先搬動 package：這個資料夾放 MCP 包裝層，直接 import 根目錄的 `engine02`。等 engine02 的開發告一段落，再決定要不要實際搬進來。

`tests/`、`reports/`、`docs/contract/` 同理維持原位（被 `pyproject.toml`、程式與文件引用）。
