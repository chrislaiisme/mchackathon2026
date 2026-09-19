# 有價格的商品目錄選型（ENGINE 02，2026-09-19）

> 背景：主辦提供的規格要求商品目錄是**含價格、描述、影像的公開資料集**，並點名 H&M
> Personalized Fashion Recommendations 與 Amazon Clothing metadata。我們現行目錄
> （`data/catalog/kagl_polyvore`，17,783 件）**完全沒有 price 欄位**，`engine02/constraints.py`
> 的 budget 過濾與 `budget:x1.2` / `budget:drop` 兩段放寬階梯因此是死碼。
>
> 本文是 `docs/research/catalog-options.md`（2026-09-17）的續篇，**不重複**該文已驗證的欄位表，
> 只補上「價格」這條軸線、修正其中兩項當時未查證的事實，並給出可執行的做法。
>
> 驗證方式：HF Hub API（`/api/datasets`、`/tree`、README YAML）、HF datasets-server
> `/first-rows`、對 `.jsonl` 做 HTTP Range 取樣後**實際解析真實資料列**、Kaggle 公開
> `/api/v1/datasets/list`、以及各資料集官方授權頁。沒有整包下載，沒有使用任何 token。

---

## 1. 候選資料集（本次實測）

| 資料集 | 來源 URL | 授權 | 需要帳號／接受規則 | 磁碟 | 筆數 | price | description | image | category | colour | season/occasion |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Amazon Reviews 2023 — Clothing_Shoes_and_Jewelry** | `huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023` → `raw/meta_categories/meta_Clothing_Shoes_and_Jewelry.jsonl` | **卡片與 tag 都沒有任何 `license:`**（HF API 實查） | 否（`gated:false`，公開，免 token） | 17.96 GB（單一 jsonl） | 7.2 M | ✔ **55.7%**（float，USD） | ✔ 54.6%（`description`）／94.7%（`features`）→ 合併後 ~99% | △ **只有 CDN URL**，需自行抓 | ✔ **100%** 階層路徑 | ✘（`details.Color` 僅 ~5%） | ✘ 完全沒有 |
| Amazon Reviews 2023 — Amazon_Fashion | 同上，`meta_Amazon_Fashion.jsonl` | 同上 | 否 | 1.42 GB | 825.9 K | ✘ **僅 13.6%** | ✘ 8.6% | △ URL | ✘ **0%**（`categories` 全空） | ✘ | ✘ |
| **H&M Personalized Fashion Recommendations** | `kaggle.com/competitions/h-and-m-personalized-fashion-recommendations` | 競賽規則（見 §5） | **要 Kaggle 帳號＋接受競賽規則** | 約 25 GB（含 images/） | articles 105,542 | ✘ **articles.csv 根本沒有 price 欄**；transactions 的 `price` 是**正規化值**（實測首列 `0.0508305084745762`） | ✔ `detail_desc` | ✔ 競賽 zip 內含 | ✔ `product_type_name` 等 | ✔ `colour_group_name` | ✘（只有 `index_group_name` 當性別） |
| Fashion Product Images（我們現用的 KAGL 上游） | `kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset`；HF 鏡像 `Marqo/KAGL` | **Kaggle API 實查：`licenseName = "MIT"`**（修正 09-17 的「未查證」） | 否（HF 鏡像免 token） | Kaggle 原始 **24.77 GB**；HF 鏡像 12.7 GB | 44,434 | ✘ | ✘（只有商品名） | ✔ 內嵌 1800×2400 | ✔ 三層 | ✔ `baseColour` | ✔ `season` / `usage` |
| Polyvore（`Marqo/polyvore`） | `huggingface.co/datasets/Marqo/polyvore` | apache-2.0（卡片自承不擁有資料） | 否 | 約 3 GB | 94,096（21,587 套 outfit） | ✘ | ✘ | ✔ 內嵌 274×400 | △ 很髒（21% → other） | ✘ | ✘ |
| ASOS（`UniqueData/asos-e-commerce-dataset`） | `huggingface.co/datasets/UniqueData/asos-e-commerce-dataset` | **cc-by-nc-nd-4.0（禁商用、禁改作）** | 否 | 小 | 30,845 | ✔ | ✔ | ✘ 只有 URL | ✔ | ✔ | ✘ |
| ASOS（`crawlfeeds/asos-fashion-products-dataset`） | 同上網域 | `other`（商業爬蟲免費樣本） | 否 | 小 | **1,000** | ✔ AUD | ✔ | ✘ 只有 URL | ✔ 麵包屑 | ✔ | ✘ |
| Myntra（`gatech-scheller-ai-in-business/myntra-products`） | `huggingface.co/datasets/gatech-scheller-ai-in-business/myntra-products` | apache-2.0 | 否 | 小 | viewer 無 size | ✔ INR | ✔ | ✘ 只有 URL | ✘ | ✘ | ✘ |
| Myntra（`Gssmc/myntra_dataset`） | `huggingface.co/datasets/Gssmc/myntra_dataset` | mit | 否 | 小 | 15,000 | ✔ INR | ✔ | ✘ **無影像** | ✔ | ✔ | △ specifications 內有 Occasion |
| DeepFashion（In-shop 等） | `mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html` | **「available for non-commercial research purposes only」，並明文禁止 reproduce / duplicate / resell 任何影像與衍生資料** | 要填表取得下載連結 | 數十 GB | 800 K+ 影像 | ✘ | △ 部分 | ✔ | ✔ 50 類 | △ | ✘ |
| Fashionpedia | `fashionpedia.github.io` | **標註 CC-BY-4.0；影像版權屬 Flickr/Unsplash/Pexels 等各平台，作者不擁有** | 否 | 未載明 | 48,825 影像 | ✘ | ✘ | ✔ | ✔ 27 類＋294 屬性 | ✔ 屬性內 | ✘ |

### 可再散布 vs. 受競賽／授權限制（直說）

- **可再散布（卡片層級）**：`Marqo/KAGL`（MIT，Kaggle API 實查確認）、`Marqo/polyvore`（apache-2.0）、
  `gatech-scheller-ai-in-business/myntra-products`（apache-2.0）、`Gssmc/myntra_dataset`（mit）、
  Fashionpedia **標註**（CC-BY-4.0）。注意：這幾個的「影像」上游都是零售商或圖庫，卡片授權不等於影像著作權。
- **不可再散布 / 受限**：
  - **H&M**：競賽資料，必須登入並接受競賽規則才能下載；**不得**把原始檔放進我們的 repo 或公開 demo 包。
  - **DeepFashion**：明文非商用且禁止重製散布 → 贊助商 demo 直接排除。
  - **`UniqueData/asos-e-commerce-dataset`**：CC-BY-NC-ND，禁商用也禁改作 → 排除。
  - **Amazon Reviews 2023**：**沒有宣告任何授權**。沒有授權不等於可自由使用；資料本身是 amazon.com 的爬取結果，
    影像留在 Amazon CDN 上、著作權屬 Amazon／賣家。可以本機建庫自用，**不要**把 items.parquet 或 images/ 對外散布。

---

## 2. 建議

### 結論：**新增**一個 `data/catalog/amz_clothing`（Amazon Clothing，有價格），**不要取代** `kagl_polyvore`，也**不要**把兩者 merge。

**為什麼是 Amazon Clothing 而不是 H&M（雖然主辦點名 H&M）**

H&M 那份資料**沒有商品層級的價格**。`articles.csv` 25 個欄位裡完全沒有 price；價格只存在於
`transactions_train.csv`，而且是被縮放過的相對值（實測首列 `0.0508305…`，單位未公開）。
要拿到「每件商品一個價格」必須自己對 3,180 萬筆交易做 median 聚合，得到的仍是**無單位的相對數**，
在畫面上寫不出「NT$」，也沒辦法對應使用者講的「兩千元以內」。加上必須接受競賽規則、下載約 25 GB，
CP 值遠低於 Amazon。**這點值得在簡報裡主動講**：主辦舉的例子之一其實不含可用價格，我們查證後改用另一個。

**Amazon Clothing 的實測體質**（首 533 列真實資料）

| 指標 | 值 |
|---|---|
| 通過「有價格＋有影像＋可映射類別」三道篩選的比例 | **55.7%**（297/533） |
| price 中位數 / 範圍 | 25.95 USD / 2.99–449.00 |
| description 覆蓋（含 features 遞補） | 294/297 ≈ **99%** |
| gender 覆蓋（`categories` 路徑或 `details.Department`） | 286/297 ≈ **96%** |
| colour 覆蓋 | 11/297 ≈ **4%** |
| coarse category 分佈 | other 82、shoes 52、top 44、accessory 41、dress 22、bottom 20、jewelry 18、outerwear 13、bag 5 |

**取捨（必須講清楚）**

| | 現行 `kagl_polyvore` | 新 `amz_clothing` |
|---|---|---|
| price / budget 過濾 | ✘ 死碼 | ✔ **100%**（腳本強制要求有價才收） |
| description（影響 BM25 與 `Catalog.texts()`） | ✘ 全 null | ✔ ~99% |
| colour 硬過濾 | ✔ 100% | ✘ ~4% |
| season / occasion 硬過濾 | ✔ ~99.7% | ✘ **0%（來源沒有這兩個欄位）** |
| outfit 結構（complete-look） | ✔ Polyvore 21,587 套 | ✘ 沒有（`bought_together` 實測 533 列全空） |
| 影像 | ✔ 資料集內嵌 | △ 需向 Amazon CDN 抓 |

也就是說：**換過去等於用 1 個活過來的 slot，換掉 3 個死掉的 slot**。所以建議是「兩個目錄並存、依 demo 情境切換」
（`scripts/demo_run.py --catalog …` 與 `ENGINE02_CATALOG` 本來就支援換路徑），而不是單向替換。
講預算的情境用 `amz_clothing`，講顏色／季節／完整搭配的情境用 `kagl_polyvore`。

**為什麼不要 merge 這兩個目錄**：`engine02/constraints.py:134` 是
`ok = ~np.isnan(price)` — **價格為 null 的商品會被 budget 過濾直接踢掉**。混合目錄一旦使用者講了預算，
所有 KAGL 商品會靜默消失，只剩 Amazon 商品，畫面上完全看不出原因。要 merge 就得先決定
「null price 是否 allow_unknown」並改 `constraints.py`，那是另一個設計決策，不該在 hackathon 當天做。

**colour / season / occasion 怎麼補**：`engine02/attribute_fill.py` 已經是為了這件事寫的
（`FILL_ATTRS = ("color","gender","occasion","season")`，零樣本 CLIP／VLM 預測＋低信心 abstain＋
`attr_source[attr] = "predicted:<model>"` provenance）。對 `amz_clothing` 跑一次 fill 就能把三個 slot
救回來，而且畫面會誠實標示「顏色為模型判讀」。**不要**用規則從標題硬拆顏色再假裝是 dataset 值。

**complete-look 怎麼辦**：`data/catalog/polyvore/category_cooccurrence.json` 是**聚合統計**（coarse×coarse 配對數），
與商品目錄無關，可以直接套在 `amz_clothing` 上餵 `engine02/compat.py` 的 NPMI。真正做 item-level 的
`FastOutfitTransformer` 需要 `outfit_ids`，Amazon 沒有 → 在 `amz_clothing` 上 `/complete-look`
只能退回 `similarity` / `ot`（OT 的 compatibility head 不需要目錄自帶 outfit，只需要 anchors＋candidate 的影像嵌入），
但 `ot_cir` 的品質無法用這個目錄自評。影像是乾淨的去背商品圖，Marqo-FashionSigLIP 可以直接嵌入。

**下載量**：8,000 件 ≈ metadata 串流 ~59 MB ＋ 影像 ~184 MB（CDN 端先縮到 400 px，實測 22.6 KB/張），
落地約 240 MB。**絕對不要**整包抓那個 17.96 GB 的 jsonl。

---

## 3. price 變成真值之後，ENGINE 02 要改什麼（實際查到的觸點）

### 3.1 先講最重要的發現：**光有價格還不會啟用 budget**

`engine02/intent_adapter.py:306-311` 是唯一處理 budget 的地方，它**從來沒有 assign `c.budget`**，
只把 ENGINE 01 的 `budget_min` / `budget_max` 轉成一條警告字串：

```python
if data.get("budget_min") is not None or data.get("budget_max") is not None:
    unresolved.append(f"預算 {…}–{…} 無法套用：公開商品庫沒有價格欄位（見 docs/engine02-design.md §7 限制）")
```

**這是第一個必改點**，否則換了目錄也沒有任何行為變化。
（`scripts/build_stack.py:96-98` 的 ENGINE 01 stub 已經會把「NT$2000」regex 成 `budget_max`，所以 demo 流量真的帶得到預算。）

### 3.2 budget 過濾（已實測可動）

用本文新增的腳本產出的 15 件 smoke 目錄實際跑過：

```
budget<=25 → 8 items; applied {'budget': ['0-25.0']}; relaxed []
budget<=10 → 15 items; relaxed ['budget:x1.2', 'budget:drop']   # 兩段梯子都真的觸發了
```

- `engine02/constraints.py:130-140` — 唯一的 budget filter，直接讀 `items["price"]`。
- `engine02/constraints.py:134` — `ok = ~np.isnan(price)`：**null price 會被排除**（見 §2 的 merge 警告）。
- `engine02/constraints.py:20-32` — `DEFAULT_LADDER` 第 6 段 `("budget","x1.2")`、第 8 段 `("budget","drop")` 從死碼變成活的。
- `engine02/taxonomy.py:456-465` — 階層類別回退時會先把 `("budget","drop")` 從梯子拿掉，這個保護仍然正確，不用改。
- `engine02/attrindex.py:22` — `INDEXED` 只有 7 個**類別型**欄位，**沒有數值範圍索引**。budget 因此是
  `build_mask` 裡唯一未加速的述詞，而且**每跑一段梯子就重做一次 `pd.to_numeric` 全欄掃描**。
  17.8 k 筆還撐得住，但這是之後的熱點。
- `engine02/composed.py:287` — critique 明文拒絕更新 budget（`attr not in ("budget","excluded_values")`），
  所以「太貴了，便宜一點」這種第二輪 critique 目前**改不動預算**。要做就是這一行。
- `engine02/pipeline.py:770-783` — `hard_constraint_satisfaction` 用 `build_mask(state={})`（**不放寬**）計算，
  budget 一旦上線，被梯子救回來的那些商品會讓這個 headline 指標下降。屬預期行為，但簡報要先知道。

### 3.3 放寬階梯的文案

- `engine02/explain.py:74-77` — 放寬步驟會直接渲染成中文句子，但**沒有把 slot 名稱本地化**：
  ```python
  reasons.append(f"注意：為了有足夠結果，放寬了「{slot}」條件（{r}）")
  ```
  budget 一旦觸發，使用者會看到「放寬了「budget」條件（budget:x1.2）」。
  `engine02/panels.py:52` 其實已經有 `SLOT_LABEL = {... "budget": "預算" ...}`，接上去即可。
- `engine02/panels.py:384` — `relaxed_human` 同樣的問題，同樣的修法。

### 3.4 面板與回報

- `engine02/panels.py:49-55` — `HARD_FILTER_SLOTS` 不含 budget，註解寫著「budget is dead while the
  catalog has no prices」。改目錄後這行註解與集合都要跟著調整。
- `engine02/panels.py:207-208` — `soft_only` 只要有**任何一張卡片**有價格就會停止把 budget 列為「只是軟條件」。
- `engine02/panels.py:363-389` — `provenance()`：`price_available = any(it.price is not None …)`，
  以及 caveat 字串「商品庫無價格資料，預算條件不做過濾（畫面需標示）」會自動消失。
- `engine02/panels.py:165-170` — `stated_vs_unstated` 的 budget 分支**只渲染 `max_price`**，
  只給 `min_price` 的情況會顯示成 `["set"]`。要做「價格帶」就得補這裡。
- `engine02/panels.py:553-580` — `category_color_gap()` 只看 `category` × `color`；
  **價格帶 gap 面板是全新的東西**，`CellGap` 要加欄位，`ElementGap`（Kansei）那條線與價格無關。

### 3.5 前端／契約邊界

- `engine02/intent_adapter.py:434-447` — `response_to_retrieval_result` 組 `products[]` 時只取
  `("category","subcategory","color","occasion","season","gender")`，**price 在這裡被靜默丟掉**。
  `RankedItem.price`（`contracts.py:263`）有值，但 FastAPI `/retrieve` 的回應沒有。要做價格 UI 就是改這裡。
- `engine02/intent_adapter.py:340-373` — `match_score` 不計 budget，畫面上的「符合度」會忽略使用者講的預算。
- `docs/contract/*.json` — 所有 example 的 `price` 都是 `null`、`budget` 都在 `unmentioned`、
  `example_view_round2.json:310` 寫死 `"price_available": false`。契約範例要重出。

### 3.6 會壞掉的測試（必須一併更新）

- `tests/test_audit.py:268-275` — `test_provenance_flags_missing_price_and_relaxation`
  斷言 `pv.price_available is False` 且 caveat 含「價格」。
- `tests/test_audit.py:218,220` — `assert "budget" in svu.unmentioned`、`assert svu.soft_only == []`。
- `tests/test_intent_adapter.py:83-85` — `test_an_unusable_constraint_is_reported_not_faked`
  斷言 `budget_max: 2000` 會產生「無法套用」警告且 `constraints.budget` 沒有值。
  **這個測試的名字就是我們現在要推翻的設計決策**，改的時候要連測試意圖一起改寫，不是刪掉。
- 另外 `tests/test_engine02.py:18-29` 與 `tests/test_ltr.py:30` 的 fixture **本來就有價格**，不受影響。

### 3.7 建庫腳本側（已經準備好了）

`scripts/prepare_catalog.py:43` 的 `ATTRS` 已含 `"price"`，`attr_source` JSON 也已經有 `"price"` key、
`stats.json` 的 `attr_coverage.price` 也已經在報 0.0。新腳本沿用同一套，直接變成 1.0。

---

## 4. 風險

1. **授權（最高風險）**。Amazon Reviews 2023 **沒有宣告授權**（HF tag 實查，沒有 `license:` 條目）。
   我們可以本機建庫、在台上展示，但**不應**把 `items.parquet` 或 `images/` 放進 git、放進交付包或公開連結。
   `.gitignore` 目前已排除 `data/`，要在報告與 README 明講這條線。
2. **影像必須向 Amazon CDN 抓**。`m.media-amazon.com/robots.txt` 實查：沒有 `User-agent: *` 區塊，
   但明文 `Disallow: /` 封鎖 GPTBot 與 CCBot。我們的腳本用自己的 UA、單張抓、4 個 worker、只抓縮圖尺寸，
   但**亞馬遜的 Conditions of Use 是否允許這種抓取，我無法核實**（見 §5）。緩解：只抓 demo 需要的幾千張、
   不對外散布、不轉存到公有雲。
3. **磁碟**。8,000 件約 240 MB，即使做到 3 萬件也只有 ~0.9 GB，對 88 GB 空閒完全不是問題
   （本機 E: 實測 753 GB free）。真正的地雷是**有人手滑整包抓那顆 17.96 GB 的 jsonl** —— 腳本用 HTTP 串流、
   達到 `--limit` 就關連線，`--limit 0` 在 help 裡標註「你不會想這樣做」。
4. **當天會出事的地方**：
   - CDN 限流或圖片 404 → 腳本會跳過該件並計數；**目錄必須在活動前建好、不要在台上現抓**。
   - 沒有 season / occasion → 任何「秋天穿的」「面試穿的」demo 腳本在這個目錄上會立刻走到
     `allow_unknown` 再 `drop`，畫面會出現放寬提示。要嘛先跑 `attribute_fill`，要嘛避開這類台詞。
   - 27.6% 落在 `other` → 用 `scripts/merge_catalogs.py --keep-categories top,bottom,outerwear,dress,shoes,bag`
     過一遍再上台。
   - **價格是 2023 年 9 月以前的爬取值、單位 USD**。台上講「NT$2000 以內」需要換算，
     而且必須標示「價格為公開資料集之歷史值，非即時售價」——這句話本來就該在畫面上，因為主辦要的是
     「搭配完整、可購買」而不是即時庫存。
   - `intent_adapter` 的那行警告字串（§3.1）如果沒改，換了目錄**畫面不會有任何變化**，
     會變成「做了但看不出來」。這是最容易在 demo 前一晚才發現的坑。

---

## 5. 我無法核實的部分

- **Kaggle H&M 競賽規則原文**。`kaggle.com/competitions/.../rules` 是 SPA，WebFetch 只拿得到標題；
  Kaggle 公開 API 對 competitions 端點回 401（需登入）。因此「Data Access and Use 是否限非商業」
  **本次沒有讀到條文**，表中只寫「競賽規則」而不下結論。要確認請用自己的 Kaggle 帳號開頁面看。
- **Amazon 的 Conditions of Use 是否允許為此用途抓取 CDN 影像**。robots.txt 沒有禁止我們這種 UA，
  但 robots.txt 不是授權書，我沒有去讀並引用 Amazon 的使用條款原文。
- **Amazon Reviews 2023 的授權狀態**。我只能證明「卡片與 tag 上沒有授權宣告」，
  不能由此推論「可自由使用」。arXiv:2403.03952 論文本文我沒有讀。
- **覆蓋率數字的母體**。price 55.7% / description 54.6% / categories 100% 是
  **Clothing shard 前 533 列**（HTTP Range 取前 1.5 MB）實際解析的結果，不是 720 萬筆全量統計。
  Amazon_Fashion 的 13.6% / 8.6% 同理來自前 221 列。全量分佈可能不同。
- **`paramaggarwal/fashion-product-images-dataset` 的 MIT**。這是 Kaggle API `licenseName` 欄位，
  也就是**上傳者自行宣告**的值，不是對 Myntra 商品影像著作權的法律判斷。
- **Fashionpedia 的下載體積**。官網未載明，我沒有去 cvdfoundation GitHub 實測。
- H&M `articles.csv` 欄位與 transactions `price` 的正規化，是從 HF 鏡像
  `einrafh/hnm-fashion-recommendations-data` 的 datasets-server `/first-rows` 讀到的，
  **不是 Kaggle 官方檔案**。鏡像與原始檔是否完全一致，我沒有核對。

---

## 6. 交付物：`scripts/prepare_catalog_priced.py`

```bash
# 只印會下載什麼，不寫任何檔案
.venv/Scripts/python.exe scripts/prepare_catalog_priced.py --name amz_clothing --limit 8000 --dry-run

# 映射單元測試（無網路、不寫檔）
.venv/Scripts/python.exe scripts/prepare_catalog_priced.py --self-test

# 小量試跑
.venv/Scripts/python.exe scripts/prepare_catalog_priced.py --name amz_smoke --limit 50

# 正式建庫（約 240 MB、視網路 10–20 分鐘）
.venv/Scripts/python.exe scripts/prepare_catalog_priced.py --name amz_clothing --limit 8000 --workers 4

# 已經有 jsonl 就不要再串流
.venv/Scripts/python.exe scripts/prepare_catalog_priced.py --name amz_clothing \
    --local-jsonl D:/dl/meta_Clothing_Shoes_and_Jewelry.jsonl --limit 8000
```

設計重點：

- **輸出 schema 與 `prepare_catalog.py` 完全一致**（15 欄、同樣的 pyarrow type、同樣的 `attr_source` JSON），
  `--self-test` 會去 parse `prepare_catalog.py` 的 `cols = [...]` 比對，欄位漂移會當場 fail。
- **串流＋提前中止**：`requests.get(stream=True)` 逐行讀，收滿 `--limit` 就關連線。8,000 件只讀約 59 MB。
- **CDN 端縮圖**：把 `…_AC_UL1500_.jpg` 改寫成 `…_AC_UL400_.jpg`（實測 22.6 KB vs 274 KB），
  落地再縮到 384 px JPEG q90，與現有目錄一致。`IMG_RE` 只接受 `m.media-amazon.com` 主機，
  其他網域一律拒絕（`--self-test` 有測）。`thumb`（38×50）永不採用。
- **不發明值**：`season` / `occasion` / `outfit_ids` 一律 null；`color` 只在 `details.Color` 存在時寫入；
  沒有價格、沒有影像、沒有可映射類別、沒有標題的列直接丟棄。
- **路徑封鎖**：`--name` 只接受 `[A-Za-z0-9._-]+`，輸出目錄 resolve 後必須是 `data/catalog/` 的直屬子目錄，
  否則 `SystemExit`（已測 `--name ../../evil`）。
- **憑證**：沒有任何硬編碼。只從環境變數 `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` 讀；
  這個 repo 目前是公開免 token，若哪天變成 gated，401/403 會印出明確的設定指引而不是 traceback。
- **`--dry-run` 會印出**：metadata URL 與完整檔案大小、預計讀取量、影像 URL 樣板與張數、
  預估傳輸量與落地大小、輸出路徑三個檔案、授權警語、以及「哪些欄位一定是 null」。

已驗證：

| 驗證 | 結果 |
|---|---|
| `--self-test`（47 個斷言：類別映射、BLOCK、性別、價格 parse、CDN URL 改寫、`adapt()` 拒收規則、欄位一致性） | **OK, 0 failures** |
| `--dry-run`（含 `--name ../../evil` 與不存在的 `--local-jsonl`） | 正確輸出／正確報錯 |
| 端對端 15 件（`--local-jsonl`，真實 Amazon 資料列） | 15 件、0 失敗、616 KB、price 覆蓋 1.0 |
| `Catalog.load()` → `texts()` / `image_paths()` | 15 欄齊全、圖檔存在、`texts()` 有實質描述 |
| `filter_with_relaxation` 對 budget | `<=25` 濾到 8 件；`<=10` 觸發 `budget:x1.2` → `budget:drop` |

> 測試產物留在 `data/catalog/amz_smoke/`（616 KB，15 件），可直接刪除。
