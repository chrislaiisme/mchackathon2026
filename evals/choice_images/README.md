# evals/choice_images/

負責線：線 3｜概念圖與選項圖
對應功能：FR-010 中的選項圖檢查通過率

## 內容

- 先前的生圖可行性驗證結果（褲口、腰線）：比賽前由線 3 整理放入
- 每種變化重複生成多次的檢查通過率
- 用已知結果校準選項圖自動檢查（線 1 可支援）

## Hermes OpenAI OAuth 實測（2026-09-16）

使用 Hermes Agent v0.21.2 的 `image_gen/openai-codex` plugin，以 ChatGPT/Codex 訂閱帳戶 OAuth 產圖，不使用 `OPENAI_API_KEY`。

| 測試 | 模型 | 耗時 | 結果 |
|---|---|---:|---|
| text-to-image：Sweet Lolita JSK 商品照 | `gpt-image-2-medium` | 39.0 秒 | 通過；1145 × 1374 PNG |
| image-to-image：只把主布由粉紅改成薰衣草紫 | `gpt-image-2-medium` | 39.2 秒 | 通過；構圖、蕾絲、蝴蝶結、袖型、領型與三層裙結構均保留 |

測試素材：

- `hermes_openai_codex_test_prompt.txt`
- `hermes_openai_codex_edit_prompt.txt`
- `hermes_openai_codex_sweet_lolita.png`
- `hermes_openai_codex_sweet_lolita_lavender.png`

Hermes 的 `openai-codex` provider 只會在收到 `image_source=final` 時保存並回傳成功結果；progressive partial 會被拒絕，不會成為上述成品。

## Pinterest → Hermes 實測（2026-09-17）

Pinterest Trial app 透過 `/v5/boards/{board_id}/pins` 成功讀取公開圖版 [IntentWeave References](https://www.pinterest.com/pinyucs15/intentweave-references/) 的 3 張參考 Pin。下載後的圖片只作為高階輪廓、層次與配色參考，再交給 Hermes `openai-codex` OAuth provider 生成全新人物與場景；沒有使用 `OPENAI_API_KEY`。

| 測試 | 模型 | 耗時 | 結果 |
|---|---|---:|---|
| Pinterest reference-to-image：中性極簡街頭穿搭 | `gpt-image-2-medium` | 44 秒 | 通過；1024 × 1536 PNG；新人物、新姿勢、新場景，無品牌、標誌與可讀文字 |

測試素材：

- `hermes_pinterest_reference_prompt.txt`
- `hermes_pinterest_reference_streetwear.png`

下載的 Pinterest 原始參考圖保存在被 Git 忽略的 `data/pinterest_trends/`，不提交到版本庫。

## 六宮格實測（2026-09-19）

**一張圖生六件、再切成六張卡片**，取代一件一件生。動機是時間與額度：單件生圖 26 秒，
一輪六件逐一生成要三分鐘，現場 demo 撐不住，驗證迴圈那 60–200 次也會啃掉共用的 Codex 額度。

兩張圖都用 `gpt-image-2-low`、Hermes `openai-codex` OAuth，沒有用 `OPENAI_API_KEY`。

| 測試 | 模式 | 產生方式 | 耗時 | 每件攤提 | 結果 |
|---|---|---|---:|---:|---|
| 牛仔褲：基準＋5 個不同屬性 | 手寫探針 | 手寫 prompt | 48.4 秒 | 8.1 秒 | 通過；1312×1199 |
| 裙子：length × fit 交叉 | concepts | 完整流程 | 34.2 秒 | 5.7 秒 | 通過；1312×1199 |
| 牛仔褲：目前水洗＋5 種水洗 | variants | 完整流程 | 37.3 秒 | 6.2 秒 | 通過；1312×1199 |

對照組是同一天 09:37 的單件商品照（`gpt-image-2-low`，1024×1536，兩張間隔 26 秒），
所以六宮格的效率是 **3.2–4.6 倍**。

第一張是寫腳本之前的手寫探針（`HOUSE_STYLE` 的前身），六格各改**不同**屬性——那不是
`variants` 模式的形狀（真正的 variants 是一題一個欄位、六格是它的不同取值），但它證明了
「同一張圖裡守得住單變因」這個前提。後兩張才是流程完整跑出來的。

### 單變因守住了

牛仔褲那張的六格共用同一組基準屬性（中藍水洗、高腰、barrel 褲型、五口袋、銀釦），
每格只有指定的那一項變：低腰、窄直筒、ecru 米白、九分、鬚邊。連最容易連動的
「改褲型卻順便改水洗」都沒發生。這是整個做法成立與否的關鍵。

### 切割可靠

`agent/scripts/slice_grid.py` 用投影法偵測純白 gutter，不寫死等分：

| 切線 | 偵測位置 | 理論位置 | 誤差 |
|---|---|---|---|
| 欄 gutter 1 | 0.3331 | 0.3333 | 0.02% |
| 欄 gutter 2 | 0.6662 | 0.6667 | 0.05% |
| 列 gutter 1 | 0.4979 | 0.5000 | 0.21% |

六格 auto-trim 之後尺寸全等（414×581）。裙子那張的尺寸 spread 是 5.8%。

### 色距要用兩個統計量，不能只用一個

判斷「這格的顏色有沒有真的變」不能只看一個統計量，兩個候選各有盲區，而且盲區不重疊：

| 資料組 | 期望 | 受光面（最亮 25%） | 中間調（40–70%） |
|---|---|---|---|
| 裙子六格（同一塊米白布，剪影差很多） | 低 | 1.1–3.3 ✓ | 17–30 ✗ |
| 牛仔褲六水洗（藍／深藍／黑／米白／淺藍／灰） | 高 | 1.0–142 ✗ | 42–153 ✓ |
| 舊探針（只有一格改色） | 只有那格高 | ✓ | ✓ |

受光面對剪影面積與陰影量免疫，但**深色系會塌在一起**——深藍、黑、灰的高光都是差不多的淺灰，
第一版只用受光面時，六種水洗有三種被誤判成「沒變」。中間調分得開深淺，卻會被陰影比例帶著跑，
同色不同剪影就誤判。

所以拆成兩個問題各用一個：**「該變的有沒有變」取兩者較大值**（任一個看到變化就算數），
**「不該變的有沒有被偷改」取兩者較小值**（兩個都同意才判定）。三組資料在這個規則下全部零誤判。

### 其餘門檻是從這些圖量出來的

`agent/scripts/check_cells.py` 的門檻不是憑感覺定的。牛仔褲那張的五個單變因量出來：

| 格 | 變因 | 色距 | 剪影差 |
|---|---|---:|---:|
| 2 | fit（低腰） | 4.97 | 0.0620 |
| 3 | fit（窄直筒） | 3.99 | 0.1044 |
| 4 | colors（ecru 米白） | **133.56** | 0.0839 |
| 5 | length（九分） | 4.68 | 0.0773 |
| 6 | construction（鬚邊） | 1.92 | **0.0344** |

兩個結論直接從表裡讀出來：

1. 顏色改動的辨識度極高（133.56 對上其他格的 ≤4.97），門檻放 12 兩邊都很安全；
   水洗那組全部落在 42–153，也都判定正確。
2. 鬚邊那格的剪影只差 0.0344，比任何真正的版型改動都小。局部工藝細節（下襬做法、車線、
   口袋）本來就不改變整體剪影，**像素層看不到這種東西**。所以這類屬性回報「無法判定」，
   不給假的通過率；要驗證得靠語意層或人眼。

### 還沒做的

語意層（FashionCLIP 圖文指派檢查）需要 torch 與 open_clip，本機沒裝，**目前沒有跑過**。
有 encoder 的機器上跑 `check_cells.py --encoder marqo-fashionSigLIP` 之後，把通過率填在這裡，
那就是 FR-010 要的「選項圖檢查通過率」。

### 素材

- `grid_variants_jeans.png` / `grid_variants_jeans_prompt.txt` — 選項圖那張。
  這張的 prompt 是手寫的原型（`HOUSE_STYLE` 的前身），不是流程跑出來的。
- `grid_variants_jeans_cell6.png` — 切出來的單格長什麼樣（鬚邊那格，414×581）。
- `grid_concepts_skirt.png` / `_prompt.txt` / `_manifest.json` — 概念圖那張，
  由 `agent/scripts/generate_grid.py` 完整流程產出，manifest 是每格關鍵字的實例。
- `grid_variants_jeans_wash.png` / `_prompt.txt` / `_manifest.json` — 選項圖那張，
  同樣是完整流程產出。第 1 格是意圖裡目前的水洗（中藍），2–6 格是那題的五個選項，
  每格的 `option_id` 直接對上 `FeedbackInput.selected_option_id`。

重現：

```bash
python agent/scripts/generate_grid.py --intent <intent.json> --mode concepts --session demo-skirt --round 1
python agent/scripts/slice_grid.py  --manifest data/generated/demo-skirt/r1/manifest.json
python agent/scripts/check_cells.py --manifest data/generated/demo-skirt/r1/manifest.json
```
