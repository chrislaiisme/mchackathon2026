# ENGINE 02 候選模型實測報告（CPU）

> 產生方式：`scripts/verify_models.py`，原始數據在 `reports/model_verification_cpu.json`。
> 測試日期 2026-09-17；機器 Ryzen 7 7735U（8C/16T）、16 GB RAM、無 CUDA；Python 3.12.6、torch 2.14.0+cpu、transformers 5.17.0、open_clip 3.3.0、sentence-transformers 6.0.1。
> 測試時另一個 agent 同時在跑資料串流，**CPU 與 RAM 是共用的**（可用 RAM 常只剩 2–4 GB），延遲數字請視為偏保守的上限。

## 0. 測試方法（先讀這段，數字才不會誤讀）

- **資料**：`Marqo/polyvore`（split `data`，欄位 `image / category / text / item_ID`）串流前 48 列，存到 `data/verify_sample/`（圖檔＋`meta.json`），重跑時離線。48 列屬於 10 套穿搭（`item_ID` = `套裝ID_序號`），5 張是 Day Dresses，也混了 Makeup、Dining Chairs 這種非服飾品項。
- **每個模型各開一個子行程**：同一時間只有一個模型在記憶體裡，峰值 RSS 也只算這個模型（含 Python＋torch 基底約 200–450 MB）。
- **load**＝從本機快取載入到可推論的時間（不含下載，下載時間另記在 JSON 的 `download_s`）。
- **延遲**：batch 8，先暖機一批不計時；embedding 是每件 ms（含前處理），reranker 是每個 (query, doc) pair 的 ms。
- **Embedding sanity**：48 組 text→image 檢索的 R@1 / R@5 / MRR（隨機基準 R@1 = 0.021、R@5 = 0.104）。**48 張的圖庫太小，所有模型都 R@1 ≈ 0.8，差 1 件就是 0.021，模型之間的排名沒有統計意義**，只能證明「有正常運作」。要選模型請看 Marqo 在完整 Polyvore 上的 leaderboard（見文獻回顧）。
- **否定探針**：在 5 張洋裝圖上比較 cos("a dress", img) 和 cos("not a dress", img)，只列數字。
- **Reranker sanity**：從配對標題去掉第一個字（多半是品牌）當 8 個 query（例如 `knit long sleeve dress`、`pocket blazer`），算真實商品的 MRR。文字 reranker 排的是「標題 (類別)」字串，和 query 有大量字面重疊，**MRR 1.0 只代表能跑，不代表夠強**。若在 CPU 上推估 8×48 pair 會超過 900 秒，自動改成每個 query 只排 8 份文件（真實品項＋7 個固定種子的干擾項），此時隨機 MRR = 0.340。
- **LLM**：固定的 JSON 推薦理由 → 一句繁中改寫，Qwen3 關閉 thinking，取樣參數照模型卡的 non-thinking 建議值（T=0.7、top_p=0.8、top_k=20，seed 0）。

## 1. Embedding 模型

| 模型 | 狀態 | 授權 | 載入 | 峰值 RAM | 參數 / 維度 | 圖 ms/件 | 文 ms/件 | R@1 / R@5 / MRR | 否定探針（洋裝圖）cos 正句 vs 否定句 |
|---|---|---|---|---|---|---|---|---|---|
| patrickjohncyh/fashion-clip | ✅ ok（transformers CLIPModel） | MIT | 9.0 s | 1115 MB | 151M / 512 | **33.3** | **5.2** | 0.833 / 0.979 / 0.898 | 0.287 vs 0.254（否定句 ≥ 正句 0/5 張） |
| Marqo/marqo-fashionCLIP | ✅ ok（open_clip） | Apache-2.0 | 11.4 s | 1654 MB | 150M / 512 | 133.6 | 23.9 | 0.833 / 0.958 / 0.890 | 0.195 vs 0.172（0/5） |
| **Marqo/marqo-fashionSigLIP** | ✅ ok（open_clip） | Apache-2.0 | 15.9 s | 1969 MB | 203M / 768 | 125.3 | 42.8 | **0.854 / 0.979 / 0.911** | 0.058 vs 0.053（1/5） |
| srpone/zooclaw-fashionsiglip2 | ✅ ok（AutoModel，SiglipModel 384px） | Apache-2.0 | 15.3 s | 2243 MB | 375M / 768 | 459.3 | 42.0 | 0.792 / 0.979 / 0.879 | 0.084 vs 0.081（1/5） |
| google/siglip2-base-patch16-224 | ✅ ok（AutoModel） | Apache-2.0 | 18.7 s | 1834 MB | 375M / 768 | 139.6 | 38.0 | 0.833 / 0.979 / 0.910 | 0.103 vs 0.103（2/5） |
| openai/clip-vit-base-patch32（通用基準） | ✅ ok（transformers） | MIT（HF 卡無授權標籤；卡片寫部署用途不在預期範圍內） | 10.2 s | 1035 MB | 151M / 512 | 32.4 | 5.1 | 0.792 / 0.917 / 0.858 | 0.262 vs 0.251（0/5） |
| laion/CLIP-ViT-B-16-laion2B-s34B-b88K | ✅ ok（open_clip） | MIT（卡片寫任何部署用途都不在範圍內） | 9.8 s | 1654 MB | 150M / 512 | 123.6 | 21.8 | 0.813 / 0.938 / 0.875 | 0.212 vs 0.184（0/5） |

觀察：
- 7 個都能在 CPU 上正常跑，R@1 都在隨機的 38–41 倍，沒有哪個是壞掉的。
- **否定句幾乎分不開**：正句和否定句的 cos 差距最多 0.03；SigLIP 系列還有 20–40% 的洋裝圖是否定句分數比較高（siglip2 兩者平均相同）。這證實 query 裡的否定詞不能丟進 dense encoder，必須先拆成硬性篩選條件。
- zooclaw 用 384px 輸入，圖片編碼比 Marqo-FashionSigLIP 慢 3.7 倍，在這份樣本上也沒有比較好（它的優勢是作者自己報告的數字）。
- 載入注意事項：transformers v5 的 `get_image_features / get_text_features` 回傳的是 `BaseModelOutputWithPooling`，要取 `.pooler_output`（腳本已處理）；SigLIP 系列文字要用 `padding="max_length", max_length=64`。

## 2. Reranker

| 模型 | 狀態 | 授權 | 精度 | 載入 | 峰值 RAM | 參數 | ms/pair | Sanity（MRR；隨機基準） |
|---|---|---|---|---|---|---|---|---|
| Qwen/Qwen3-VL-Reranker-2B（圖文） | ✅ ok，但 CPU 慢到不能用 | Apache-2.0 | bf16 | 17.1 s | 4846 MB | 2.13B | **21,641** | 每個 query 8 張圖：MRR 0.938（有平手時從嚴計 0.875），R@1 0.875；隨機 0.340 |
| jinaai/jina-reranker-m0（圖文） | ❌ **failed**（權重沒載進去） | **CC BY-NC 4.0（禁止商用）** | bf16 | 37.5 s | 4699 MB | 2.21B | 34,240 | 8 張圖：MRR **0.221，低於隨機 0.340** |
| BAAI/bge-reranker-v2-m3（純文字） | ✅ ok | Apache-2.0 | fp32（預設） | 13.6 s | 3027 MB | 568M | **58.9** | 48 份標題：MRR 1.0（字面重疊，太簡單） |
| Qwen/Qwen3-Reranker-0.6B（純文字） | ✅ ok | Apache-2.0 | bf16 | 14.9 s | 1870 MB | 596M | 2,442 | 8 份：MRR 1.0 |
| 〃 `-fp32` 變體 | ✅ ok | Apache-2.0 | fp32 | 13.3 s | 3152 MB | 596M | **333** | 48 份：MRR 1.0 |
| Qwen/Qwen3-VL-Reranker-8B | ⏸ **gpu_only_untested** | Apache-2.0 | — | — | — | 8B（卡片：36 層、32k context） | — | 權重 17.5 GB；bf16 估計約 20 GB VRAM（4090 的 24 GB 放得下，但 batch 要小） |

重點：
- **這顆 CPU 跑 bf16 非常慢**：同一個 Qwen3-Reranker-0.6B，fp32 是 333 ms/pair，bf16 是 2,442 ms/pair（慢 7.3 倍）。7735U 沒有原生 bf16 指令集，所以 CPU 上請一律用 fp32。Qwen3-VL-Reranker-2B 改用 fp32 需要約 8.5 GB RAM，和另一個 agent 共用機器時放不下，**沒有測**。
- **Qwen3-VL-Reranker-2B 功能正確**（依模型卡用 sentence-transformers `CrossEncoder`，prompt 是 "Retrieve images or text relevant to the user's query."），但 bf16 在 CPU 上每個 pair 要 21.6 秒；top-50 重排要 18 分鐘，demo 時只能放 GPU。分數以 1/16 為單位量化（bf16 logit），會出現平手。
- **jina-reranker-m0 是「不報錯但壞掉」**：在 transformers 5.17 下，`model.language_model.layers.{0..27}.*`、`embed_tokens`、`norm` 全部被標為 MISSING（重新隨機初始化），舊的權重名稱被標為 UNEXPECTED——這是 Qwen2-VL 舊 checkpoint 的權重命名和 transformers v5 的模組名稱對不上。依模型卡試了一次 transformers 路徑（`AutoModel(trust_remote_code)` + `compute_score(doc_type="image")`），一樣是 MISSING，分數是隨機初始化模型算出來的（例如 0.527 vs 0.523 幾乎平手），不能算通過。真正的修法是另開一個 transformers<5 的 venv，但為了不動共用的 venv 沒有做。腳本現在會把「分數等於或低於隨機」自動標成 `failed_sanity`。

## 3. 本地 LLM（推薦理由改寫的備援）

| 模型 | 狀態 | 授權 | 精度 | 載入 | 峰值 RAM | 參數 | prompt / 生成 token | prefill | 總生成時間 | 速度 |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen/Qwen3-1.7B（`enable_thinking=False`） | ✅ ok | Apache-2.0 | bf16 | 8.4 s | 3715 MB | 1.72B | 188 / 28 | 14.7 s | 16.3 s | 端到端 1.7 tok/s；扣掉 prefill 約 16 tok/s |

Qwen3-1.7B 在 transformers 5.17 可以直接跑，所以沒有改用 Qwen2.5-1.5B-Instruct（腳本保留它當自動備援）。

輸出：「適合夏天約會的簡約針織洋裝，長袖設計適應盛夏，風格輕鬆休閒。」
- 是繁體中文，也是一句話，但**把注意事項講反了**：JSON 寫的是「長袖，盛夏可能偏熱」，模型卻寫成「長袖設計適應盛夏」。小模型拿來改寫時一定要加事實檢查（例如 caveat 關鍵字必須出現、不能出現相反的說法），或乾脆改用模板。
- CPU bf16 的 prefill 就要 14.7 秒，因為 RAM 不夠，fp32 沒有測。

## 4. 穿搭相容性：owj0421/outfit-transformer

| 項目 | 結果 |
|---|---|
| 狀態 | ✅ ok（CPU 可跑） |
| 授權 | 程式碼 MIT；checkpoint 沒有另外標授權 |
| Checkpoint | 照 README 用 gdown 下載 `1mzNqGBmd8UjVJjKwVa5GdGYHKutZKSSi`（1.15 GB zip），解出 `compatibillity_clip_best.pth`、`complementary_clip_best.pth`（各 806 MB） |
| 模型 | `OutfitCLIPTransformer`，item encoder = fashion-clip（凍結），6 層 transformer；總參數 201.5M；載入 4.4 s；峰值 RAM 2095 MB；state_dict 嚴格比對 missing 0 / unexpected 0 |
| 延遲 | 每套 3–4 件約 235 ms（CPU，直接吃原始圖＋文字） |
| Sanity | 樣本裡 10 套真實穿搭 vs 10 組同件數的隨機混搭：平均分數 0.628 vs 0.239，**AUC 0.77**（樣本很小，只能當「有訊號」的證據）。有一套真實穿搭（洋裝＋手提包＋墨鏡）只拿到 0.004，也有一組隨機混搭拿到 0.93。 |

實際卡住的地方，以及腳本怎麼繞過：
1. 新版 gdown 已經移除 `--id` 參數 → 改成 `gdown 1mzNqGBmd8UjVJjKwVa5GdGYHKutZKSSi -O checkpoints.zip`。
2. `src/models/load.py` 的 `model.to(rank)` 在 rank=0 時會搬到 `cuda:0`，沒有 GPU 的機器直接失敗 → 腳本自己實作載入：`torch.load(map_location=device, weights_only=False)` → `OutfitCLIPTransformer(Config(**ckpt["config"]))` → `load_state_dict`。
3. `outfit_transformer.py` 會 `import cv2` 但沒用到 → 沒裝 opencv 時用空模組代替。
4. README 的環境釘在 torch 2.5 cu121 / transformers 4.48，但實測 torch 2.14 / transformers 5.17 也能跑，不用另開 conda 環境。
5. `model_type='original'`（非 CLIP 版）的 `ItemEncoder` 建構參數名稱不一致（`text_model_name` vs `model_name`、`embedding_size` vs `d_embed`），那條路本身就壞了；我們只用 CLIP 版。

## 5. 在 RTX 4090 上重跑

```bash
# 1) 取得程式碼後，建立含 CUDA 的環境（torch 版本依該機驅動選 cu12x wheel）
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/Scripts/python.exe open_clip_torch transformers sentence-transformers accelerate qwen-vl-utils datasets psutil pillow gdown

# 2) 相容性模型（third_party/ 已在 .gitignore）
git clone https://github.com/owj0421/outfit-transformer third_party/outfit-transformer
cd third_party/outfit-transformer && mkdir -p checkpoints && gdown 1mzNqGBmd8UjVJjKwVa5GdGYHKutZKSSi -O checkpoints.zip && unzip checkpoints.zip -d checkpoints && rm checkpoints.zip && cd ../..

# 3) 全部模型（data/verify_sample/ 不存在時會自動重新串流 48 列；也可以直接從這台複製過去）
python scripts/verify_models.py --models all --device cuda
#   → reports/model_verification_cuda.json；GPU 上不限時間，reranker 會排完整的 8 × 48

# 4) 只重測 GPU 才有意義的幾個
python scripts/verify_models.py --models Qwen3-VL-Reranker-8B,Qwen3-VL-Reranker-2B,Qwen3-1.7B --device cuda

# CPU 上的 fp32 對照（任何模型名稱加上 -fp32 都可以）
python scripts/verify_models.py --models Qwen3-Reranker-0.6B-fp32 --device cpu
```

`--device auto` 會自動選 cuda；每個模型在子行程裡跑，結果會合併寫回同一份 JSON（只更新這次指定的模型）。jina-reranker-m0 在 GPU 上一樣會因為權重名稱對不上而失敗，除非另開 transformers<5 的環境。

## 6. ENGINE 02 建議保留哪些

| 角色 | 建議 | 理由 |
|---|---|---|
| Dense encoder（主力） | **Marqo/marqo-fashionSigLIP**（open_clip） | Apache-2.0；這次的 sanity 最高（跟 siglip2 差距在雜訊內）；Marqo 在完整 Polyvore 上的 R@1 也最高（0.271）；768 維；CPU 上圖片 125 ms/件，離線建索引可以接受 |
| Dense 消融／CPU 快速備援 | **patrickjohncyh/fashion-clip** | MIT；圖片快 3.8 倍（33 ms/件）；outfit-transformer 本來就內建它，可以共用 |
| 淘汰 | zooclaw-fashionsiglip2、siglip2-base、openai CLIP、LAION ViT-B-16 | zooclaw 慢 3.7 倍、沒有看到比較好；siglip2 是通用模型，沒有時尚領域優勢；OpenAI 與 LAION 的模型卡都寫部署用途不在範圍內 |
| 圖文 reranker | **Qwen3-VL-Reranker-2B，只在 GPU 上用**（top-20～50） | Apache-2.0，sanity 通過；CPU 每個 pair 21.6 秒，demo 機沒有 GPU 就關掉這一段 |
| 8B reranker | 等 4090 實測後再決定 | 約 20 GB VRAM，只比 2B 多一些精度，延遲要實測 |
| 純文字 reranker（CPU 備援） | **bge-reranker-v2-m3**（fp32） | 59 ms/pair，top-50 約 3 秒；只能看標題／屬性文字，看不到圖 |
| 淘汰 | jina-reranker-m0；CPU bf16 的 Qwen3-Reranker | jina 禁止商用，而且在 transformers 5 下權重根本沒載入；Qwen3-Reranker-0.6B 只有 fp32 才堪用（333 ms/pair），比 bge 慢 5.6 倍，沒有理由換 |
| 推薦理由 | **模板優先**；Qwen3-1.7B 只當 GPU 上的可選改寫，並加事實檢查 | CPU prefill 要 15 秒；實測會把注意事項講反 |
| 穿搭相容性 | **保留 outfit-transformer（CLIP 版 compatibility checkpoint）** | MIT、CPU 每套 0.24 秒、有訊號（AUC 0.77，樣本很小）；載入要用腳本裡的 CPU 相容寫法 |

尚未驗證（下一步）：4090 上的 8B／2B 完整 48 張重排與延遲；更大的圖庫（例如 Polyvore 1–5k 張）才分得出 encoder 之間的差異；CPU fp32 的 Qwen3-VL-Reranker-2B 與 Qwen3-1.7B（需要約 8 GB 空閒 RAM）。
