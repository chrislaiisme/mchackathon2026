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
| `catalog/kagl_polyvore_filled/` ❌**沒附**（太大） | 要 `merge_catalogs.py` + `eval_classify.py fill` 訓練分類器，且未在無 GPU 環境驗證 | 只影響屬性補值對照實驗。服務**預設用 `data/catalog/kagl`** |

換句話說：**demo 與開發只需要下面的步驟 1**，其餘都是選用的。

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

### 2. 搭配關係（選用，整套搭配功能需要）

```bash
python scripts/prepare_catalog.py --source Marqo/polyvore --limit 3000 \
    --out data/catalog/polyvore --full-cooccurrence
```

Polyvore 沒有屬性標籤，它的價值在 `outfit_ids`（哪些單品曾被搭在一起）。
`--full-cooccurrence` 會掃完整資料集的文字欄位算共現，約 10 分鐘。

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

## 不用自己建的東西

`data/catalog/<name>/index/` 底下的 `.npy`（圖片向量、設計要素矩陣）**第一次啟動服務時會自動算好並快取**
（`engine02/encoders.py`：檔案在就讀、不在就算完存檔）。

- 有 GPU：幾分鐘
- 只有 CPU：慢很多但會完成，**不會失敗**

所以組員不需要另外跑索引指令，也不需要 GPU。

## 需要 GPU 的那兩個（都是選用的）

`data/catalog/kagl/vlm_attributes_Qwen3-VL-8B-Instruct.parquet`（692 KB）是用 Qwen3-VL-8B
從圖片標的。少了它系統照常運作，只是 `concept_mode=vlm/hybrid` 走不了；**預設的 `antonym`
模式不需要它**。

`data/catalog/kagl_polyvore_filled/` 要先 `scripts/merge_catalogs.py` 合併，再跑
`scripts/eval_classify.py fill` 訓練屬性分類器。**服務預設不用這個商品庫**，它只出現在屬性補值的
對照實驗裡。

兩個都可以跟 ENGINE 02 負責人要，或從 GitHub Release 下載（見下）。

## 如果真的只能從 GitHub 拿現成檔案

上面「從公開來源重建」是首選：可重現、可驗證、不佔 repo 空間。

真的要直接拿檔案的話，把 `data/catalog/kagl/`（含 `images/` 與 `index/`，約 275 MB）打包成
`tar.gz` 掛在 **GitHub Release** 當附件（單檔上限 2 GB，不進 git 歷史）。

**不要把它 commit 進 repo**——二進位檔一旦進了 git 歷史就拿不掉，之後每個人 clone 都要付一次代價。

## 目前的內容

| 路徑 | 內容 | 怎麼來的 |
|---|---|---|
| `catalog/kagl/` | 主商品庫 5000 件 | 步驟 1 |
| `catalog/polyvore/` | 搭配關係 3000 件 | 步驟 2 |
| `catalog/kagl_priced_fixture/` | 500 件 + **合成價格** | 步驟 3 |
| `catalog/kagl_polyvore/` | 兩者合併 | `scripts/merge_catalogs.py` |
| `catalog/amz_smoke/` | 15 件**真實**價格樣本（太小，不足以評估） | `scripts/prepare_catalog_priced.py`（Amazon Reviews 2023，公開；**但該資料集未宣告授權**，僅供研究）|
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
