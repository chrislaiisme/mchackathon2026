# data/

**大部分不進版控**：商品圖片與 `items.parquet` 體積大，而且都能從公開來源重建。
**例外是重建不出來的證據檔**——那些刻意附在 repo 裡（見下表），`.gitignore` 對它們逐一放行。

**跑系統需要的東西都可以從公開來源重建**，不需要 Hugging Face 帳號、不需要 GPU
（`Marqo/KAGL` 與 `Marqo/polyvore` 經 HF API 確認 `gated: false`、`private: false`）。

**重建不出來的東西已經直接附在 repo 裡**（約 4 MB），
不用跟任何人要，`git clone` 就有：

| 重建不出來的 | 為什麼 | 影響 |
|---|---|---|
| `labels/**` ✅**已附上** | **人工標註**（210 題 ×2 份，`note` 欄是人寫的，例如「large Puma formstrip on side」） | `eval_human_agreement.py`、`eval_visual_labels.py` 的基準 |
| `catalog/kagl/vlm_attributes_*.parquet` ✅**已附上** | 需要 GPU 跑 Qwen3-VL-8B | `concept_mode=vlm/hybrid` 需要；預設 `antonym` 不需要 |
| `trends/history/**` ✅**已附上** | Pinterest 那半需要 token，別人拿不到 | 預測回測的輸入 |
| `catalog/polyvore/category_cooccurrence.json` ✅**已附上** | 只有 989 bytes，但要掃完整 Polyvore 約 10 分鐘 | **「整套搭配」（complete-the-look，含整套預算）需要它**；少了它相關功能與 2 個測試會失敗 |
| `catalog/kagl_polyvore_filled/` ❌**沒附、也無法照文件重建** | 見下方「需要 GPU 的」一節 | 只影響作者的屬性補值對照實驗。服務**預設用 `data/catalog/kagl`**，組員不需要它 |

換句話說：**demo 與開發只需要下面的步驟 0、1**，其餘都是選用的。
2026-09-19 從 GitHub 全新 clone、只做步驟 0、1 實測：**288 個測試全過**，服務可啟動並回應 `/retrieve`。

以下指令都從 repo 根目錄執行。

## 只拿得到 GitHub 的組員，照這個做

### 0. 先裝環境（一次就好）

```bash
uv venv --python 3.12 .venv                 # 或 python -m venv .venv
uv pip install -e ".[data,dev]"             # 或 .venv/bin/pip install -e ".[data,dev]"
```

**`[data]` 一定要裝**——建商品庫的腳本要從 Hugging Face 串流，需要 `datasets` 與
`huggingface_hub`；只裝核心依賴的話，下面步驟 1 會直接 `ModuleNotFoundError`。
`[dev]` 是跑測試用的。要用真正的 demo 編碼器（Marqo-FashionSigLIP）再加 `[models]`，
並且**先**照 https://pytorch.org/get-started/locally/ 裝對應機器的 torch。

### 1. 主商品庫（必要，約 8 分鐘 / 110 MB）

```bash
python scripts/prepare_catalog.py --source Marqo/KAGL --limit 5000 \
    --out data/catalog/kagl --shuffle-buffer 256 --seed 0
```

來源是 Hugging Face 上的公開資料集 [`Marqo/KAGL`](https://huggingface.co/datasets/Marqo/KAGL)
（MIT，上游是 Kaggle `paramaggarwal/fashion-product-images-dataset`）。**串流讀取，不會整包下載**，
圖片統一縮到最長邊 384 px 存成 JPEG。

`--seed 0 --shuffle-buffer 256 --limit 5000` 三個參數決定抽到哪 5000 件，**照抄就會拿到同一批**。
實測產出：5000 件、失敗 0 張、70.6 MB、496.9 秒。屬性覆蓋率 color 100%、season 99.6%、
occasion 99.9%、gender 100%、**price 0%**（這個來源沒有價格欄位）。

### 2. Polyvore 商品本身（選用；整套搭配**不**需要這步）

```bash
python scripts/prepare_catalog.py --source Marqo/polyvore --limit 3000 \
    --out data/catalog/polyvore --full-cooccurrence
```

整套搭配只需要 `category_cooccurrence.json`，那個檔已經附在 repo 裡，**不跑這步也能用**。
這一步是要 Polyvore 的 3000 件商品與圖片時才需要（例如合併商品庫）；它會重新產生同一份
`category_cooccurrence.json`（掃完整資料集的文字欄位，約 10 分鐘）。

### 3. 有價格的測試樣本（選用，只有要測預算功能才需要）

```bash
python scripts/make_priced_fixture.py --n 500
```

⚠️ **這份的價格是合成的**（依品類帶狀 log-uniform，seed 20260919）。它存在的唯一理由是
「沒有價格的商品庫無法測試預算路徑」。**任何在這上面量到的數字都不可以當成結果引用。**

### 4. 趨勢時間序列（選用，只有要跑預測才需要）

```bash
python scripts/fetch_trend_history.py      # Wikimedia Pageviews，免金鑰、CC0
python scripts/fetch_pinterest_trends.py   # 需要 PINTEREST_ACCESS_TOKEN
```

Pinterest 那支要 token，放在 repo 根目錄的 `.env`（已被 gitignore），**絕對不要 commit**。
沒有 token 就只跑 Wikimedia 那支，預測功能一樣可用。

### 5. H&M 現代商品庫（demo 建議用這個；選用）

`data/catalog/hm_filled/` **已附在 repo 裡**：9,870 件 H&M（2018–2020）商品（一萬件裡 130 件被
視覺模型判定是多件組、尺寸表或非服飾而剔除）。品類、顏色、性別是 H&M 的人工標註；季節、場合、
版型、大膽度、風格是 GPU 上的 Qwen3-VL-8B 補的，`attr_source` 逐格寫明哪個欄位是誰填的
（模型補的不可以拿來當評估標準答案）。模型和 H&M 人工標註的一致率：品類 94%、色系 81%。
圖片向量 `index/img_marqo-fashionSigLIP.npy` 也附上（GPU 算好的，CPU 不用再算 15 分鐘）。
圖片不附（第三方、體積大），用 `image_url` 一行重建，不需要帳號：

```bash
python scripts/fetch_catalog_images.py --catalog data/catalog/hm_filled
ENGINE02_CATALOG=data/catalog/hm_filled ENGINE02_ENCODER=marqo-fashionSigLIP ENGINE02_DEMO=1 \
  python -m uvicorn mcp_servers.catalog.main:app --port 8002
```

授權：H&M Kaggle 競賽條款「Non-Commercial Purposes & Academic Research」——黑客松 demo 可以，
贊助商商用不行。重建整個流程（要 GPU）：`prepare_catalog_hm.py` → `vlm_fill_catalog.py` →
`apply_vlm_fill.py`。細節：`data/catalog/hm_filled/README.md`。

### 6. 爬蟲抓的台灣／國際電商商品（有真實價格；選用）

`data/catalog/crawl_tw/` **已附在 repo 裡**：166 件，從 PChome 24h、SSENSE、iROO、Taiwanize、
Cheesebeign、Plain-me、JKS、Whiterock 等 13 家店的商品頁抓的。標題、價格（多為新台幣；SSENSE 標美金，預算比較前自動換算）、品牌
**只取頁面結構化資料寫的**，沒寫就留空；季節、場合、大膽度、風格同樣由 Qwen3-VL-8B 補。
**每件都有價格**，所以預算篩選、租還是買在這個商品庫上才有意義。圖片同樣用
`fetch_catalog_images.py --catalog data/catalog/crawl_tw` 重建。

有 `boldness` 的商品庫（hm_filled、crawl_tw）「驚喜款」才會生效。

### 7. 爬蟲原始資料集與靈感圖庫（已附，不用建）

- `data/crawl_dataset/`：2026-09-19 一次完整爬取的 1,911 筆（38 個來源：電商商品頁 242、時尚媒體
  文章 422、Wikimedia Commons 伸展台／街拍／cosplay 照片 800、Mastodon #ootd 貼文 447），
  JSON + CSV，每個來源的狀態與停止原因在 `sources.json`。網頁會變，所以直接附上。
- `data/inspiration/`：381 張伸展台／街拍／cosplay 照片（CC 授權，含作者與授權欄位，顯示時要標註），
  已自動剔除海報、人群、演講、臉部特寫、泳裝內衣等。給「我想要這種感覺」用，**不會混進商品庫**。

## 價格：每件商品都有，但估計價會標示

公開商品庫（KAGL、Polyvore、H&M）本來沒有價格。服務載入商品庫時（`Catalog.load`），沒標價的
商品由 `engine02/price_estimate.py` 給一個**估計價**：依品類／子品類的台灣平價行情基準
（例如 T 恤 399、洋裝 1,190、大衣 2,990 元），乘上正式場合、設計感、高級材質、商品庫定位等倍率，
再加上依商品 ID 固定的 ±15% 差異，四捨五入成常見售價（399、1,190）。**不用 GPU、不用金鑰，
每台電腦算出來都一樣**，clone 下來就有。

- 每件都有 `price`、`currency`、`price_twd`（換算成新台幣，給預算比較用）；
- 估計的那些 `price_estimated = true`，`price_basis` 寫怎麼算的（「估計價（非實際標價）：洋裝類基準
  1,190 元 × 正式場合 1.2」），`attr_source.price = "estimated:price-estimate-v1"`；
- 卡片、ENGINE 01 的商品屬性、租還是買、旅行膠囊都會標「估計價」；預算過濾用到估計價時，
  回應的 `input_warnings` 會說用了幾件；
- 真實標價只有 `crawl_tw`（新台幣與美金混合，預算比較前先換算）；
- 估計價**不能**拿來當評估標準答案；要關掉就設 `ENGINE02_ESTIMATE_PRICES=0`；
- 直接讀 parquet 的人：`hm_filled` 已寫入估計價；其他商品庫跑
  `python scripts/estimate_prices.py --catalog data/catalog/<name>`。

## 不用自己建的東西

`data/catalog/<name>/index/` 底下的 `.npy`（圖片向量、設計要素矩陣）**第一次啟動服務時會自動算好並快取**
（`engine02/encoders.py`：檔案在就讀、不在就算完存檔）。

- 有 GPU：幾分鐘
- 只有 CPU：慢很多但會完成，**不會失敗**

所以組員不需要另外跑索引指令，也不需要 GPU。

## 需要 GPU 或無法重建的兩個（都是選用的）

`data/catalog/kagl/vlm_attributes_Qwen3-VL-8B-Instruct.parquet`（692 KB）是用 Qwen3-VL-8B
從圖片標的。少了它系統照常運作，只是 `concept_mode=vlm/hybrid` 走不了；**預設的 `antonym`
模式不需要它**。

`data/catalog/kagl_polyvore_filled/`（17,783 件）**組員無法照文件重建**，說清楚原因：

- 它由 `scripts/eval_classify.py fill` 產生，但那是作者的研究工具，不是給人照做的流程：
  工作目錄預設是作者 GPU 伺服器上的個人路徑（`/tmp2/...`，可用 `CLASSIFY_WORK` 覆寫）；
- `fill` 需要前面 `prep → embed → zeroshot → vlm → linear → eval` 六個階段的產物，
  其中多個階段需要 GPU，也需要文件裡沒有步驟能建的 `kagl_full`／`polyvore_big` 商品庫；
- 它寫到工作目錄底下，**不是** `data/catalog/kagl_polyvore_filled/`。

**服務預設不用這個商品庫**，它只出現在作者的屬性補值對照實驗裡。組員用 `data/catalog/kagl`
就能跑完整流程。真的需要的話跟 ENGINE 02 負責人要，或請負責人掛到 GitHub Release（見下）。

## 如果真的只能從 GitHub 拿現成檔案

上面「從公開來源重建」是首選：可重現、可驗證、不佔 repo 空間。

真的要直接拿檔案的話，把 `data/catalog/kagl/`（含 `images/` 與 `index/`，約 275 MB）打包成
`tar.gz` 掛在 **GitHub Release** 當附件（單檔上限 2 GB，不進 git 歷史）。

**不要把它 commit 進 repo**——二進位檔一旦進了 git 歷史就拿不掉，之後每個人 clone 都要付一次代價。

## 目前的內容

| 路徑 | 內容 | 怎麼來的 |
|---|---|---|
| `catalog/kagl/` | 主商品庫 5000 件 | 步驟 1 |
| `catalog/polyvore/category_cooccurrence.json` | 品類共現矩陣（整套搭配用） | ✅ 已附在 repo |
| `catalog/polyvore/`（其餘） | Polyvore 商品 3000 件與圖片 | 步驟 2（選用） |
| `catalog/kagl_priced_fixture/` | 500 件 + **合成價格** | 步驟 3 |
| `catalog/kagl_polyvore/` | 兩者合併 | `scripts/merge_catalogs.py` |
| `catalog/amz_smoke/` | 15 件**真實**價格樣本（太小，不足以評估） | `scripts/prepare_catalog_priced.py`（Amazon Reviews 2023，公開；**但該資料集未宣告授權**，僅供研究）|
| `catalog/hm_filled/` | H&M 9,870 件 + 視覺模型補欄位 + 圖片向量 | ✅ 已附（步驟 5）|
| `catalog/crawl_tw/` | 爬蟲電商商品 166 件（真實價格）+ 視覺模型補欄位 | ✅ 已附（步驟 6）|
| `crawl_dataset/` | 爬蟲原始紀錄 1,911 筆 | ✅ 已附（步驟 7）|
| `inspiration/` | 靈感照片 381 張（CC 授權）+ 向量 | ✅ 已附（步驟 7）|
| `trends/` | 趨勢時間序列 | 步驟 4 |
| `context/weather.json` | 天氣情境 | `scripts/fetch_context.py` |
| `verify_sample/` | Polyvore 前 48 筆抽樣 | 可重建（`meta.json` 記錄了來源與切片）|
| `labels/` | **人工標註**，評測基準 | ⚠️ **不可重建**，見上表 |

每個商品庫底下都有自己的 `README.md` 與 `stats.json`，記錄來源、授權、建置參數與屬性覆蓋率。
`items.parquet` 的 `attr_source` 欄位**逐商品**記錄每個屬性是資料集原生還是後製補的——
補過的欄位不可以拿來當評估的標準答案。

---

demo 當天使用的電腦需要事先把 demo 用的商品庫與 `index/` 複製過去，不要現場重算。

---

## 哪個數字出自哪個檔案

見 [`reports/README.md`](../reports/README.md)——每個宣稱對到一個可以打開來看的檔案，
並且誠實列出目前**還沒有**證據檔的宣稱。
