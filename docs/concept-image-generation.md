# 概念圖與選項圖生成 — 做法與實測

負責線：線 3｜概念圖與選項圖
對應功能：FR-004 Choice Image Generation and Check；FR-007 Concept Image Generation
對應 skill：[`agent/skills/concept-image-director/SKILL.md`](../agent/skills/concept-image-director/SKILL.md)

這份記錄**為什麼** skill 的規則長那樣。skill 只寫要執行什麼；理由、數字、失敗案例、還沒解決的事都在這裡。
素材（圖、prompt、來源圖）在 `evals/choice_images/`。所有實測日期都是 2026-09-19，除非另外註明。

## 一張六宮格，不是六張單品

單件生圖 26 秒，一輪六件逐一生成要三分鐘——現場 demo 撐不住，驗證迴圈那 60–200 次也會啃掉
共用的 Codex 額度。改成一次生一張 3×2 的六宮格再切開：

| 測試 | 耗時 | 每件攤提 |
|---|---:|---:|
| 六宮格（純文字，`gpt-image-2-low`） | 34–48 秒 | 5.7–8.1 秒 |
| 六宮格（吃參考圖，`gpt-image-2-medium`） | 58–86 秒 | 9.7–14.3 秒 |
| 對照：單件商品照（`gpt-image-2-low`） | 26 秒 | 26 秒 |

純文字那組是 **3.2–4.6 倍**。吃參考圖的那組慢一些（模型檔位也從 low 換成 medium），但仍有 2–3 倍。

## 生圖走 Hermes 的 `image_generate`，不走腳本

早期版本是 `agent/scripts/hermes_image.py` 從 Hermes 的 venv `import` 私有函式
`_dispatch_to_plugin_provider`。那是最脆的一塊：私有 API 沒有相容性承諾，而
`agent/distribution.yaml` 只寫 `hermes_requires: ">=0.21.2"` 沒有上界，Hermes 一升版就可能斷掉。

Hermes 本來就開了 `image_generate` 工具給 agent 用，走正門不用碰 venv、不用子行程。
`openai-codex` provider 宣告 `modalities: ["text", "image"]`、`max_reference_images: 16`，
`image_url` 與 `reference_image_urls` 都吃 URL **或絕對本機路徑**。

兩個限制要知道：

- **`aspect_ratio` 只是表態不是保證。** gpt-image-2 走 OpenAI namespace 時尺寸由模型自己推，
  要 `portrait` 實際拿回 1312×1199 或 1536×1024。
- **畫質檔位不是工具參數。** `gpt-image-2-low`／`-medium`／`-high` 讀的是
  `~/.hermes/config.yaml` 的 `image_gen` 設定，skill 改不動。`agent/config.yaml` 依線 4 的慣例
  不寫死 provider 與 model，所以安裝者要自己設；上表的數字是在哪個檔位量的都已標註。

## 基準圖：吃 ENGINE02 的 top-1 商品照

> **現況：skill 已經不吃參考圖了。** 生成模組改成只接 ENGINE01 的 `intent`，
> `image_generate` 不帶 `image_url` 也不帶 `reference_image_urls`，衣服長什麼樣完全由文字決定。
> 下面兩節（本節與「圖會贏過字」）是參考圖那條路的完整實測紀錄，保留下來的理由有三個：
> 它證明了 on-model 目錄照可以轉成乾淨平拍、印花拿得掉；它量出了參考圖與版型自由度的取捨；
> 之後若要把 ENGINE02 接回來，這些數字不用重測。

純文字生出來的衣服會假。改成以 ENGINE02 這一輪 top-1 的真實商品照當 `image_url`，質感直接拉上來。

### 目錄的實際樣子

建好的 catalog 是 **Marqo/KAGL（上游 Kaggle，圖來自 Myntra）**，不是 CLAUDE.md 寫的 Polyvore
（`data/polyvore/` 是空的）。5000 筆，**圖在建 catalog 時被縮到最長邊 384px**。
抽樣檢查四件：**全部是穿在真人身上的目錄照**，有臉、有身體、有鞋；上衣**大多帶印花或可讀的
品牌字樣**（四件裡三件）。

這兩件事本來看起來會擋住整個做法——house style 明文禁止 bodies/people/skin，規則 6 禁止輸出文字。
實測結果是兩個都不成立：

| 測試 | 結果 |
|---|---|
| on-model 384px 目錄照 → 乾淨平拍（`ref2flat_jeans_single.png`） | 人體、腿、手、鞋全消；藍色水洗、臀腿鬚痕、五口袋、零錢袋、銅釦、車線顏色、窄管低腰全部對得上來源 |
| 胸前整塊「MARINA」印花的灰 T → 素面（`korean_top_with_reference.png`） | 印花與所有字樣完全消失 |

所以目錄照可以直接用，但基準句裡必須明講要把印花拿掉——kagl 的上衣大多有印花，這句基本上每次都要寫。

### 一張參考圖管得住什麼

六宮格配一張全域參考圖，版面沒有被毀（原本擔心單一商品照會把版面拉回「一件衣服」，沒發生），
六種水洗全部分得開，色距 43–232（門檻 12）。單變因守得住：`ref2flat_jeans_grid_white.png`
對齊後剪影差 0.011 級，bbox 高 spread 0.3%、寬 spread 0.9%。

## 圖會贏過字：參考圖與版型自由度的取捨

**這一節的標題原本是「版型變因要第二張參考圖」，結論下錯了。** 早期只測了「有參考圖」的情形，
就把現象寫成「版型由圖決定，不由字決定」。後來實測純文字（不給任何參考圖）生同一句意圖，
版型不但出得來，還比有參考圖時更貼近意圖。正確的說法是：**一旦給了參考圖，它的結構會蓋過文字。**

以「我想要一件寬鬆的牛仔褲」量膝/腰比值（越大越寬鬆）：

| 做法 | 膝/腰 平均 | 六格版型發散 |
|---|---|---|
| 參考圖是直筒牛仔褲 | 1.52 | 無 |
| 參考圖 ＋ 寬管版型參考圖 | 1.56 | 無，六格同一條輪廓 |
| **不給參考圖，只吃 ENGINE01 的 intent** | **1.67** | **有**，第 6 格 barrel 達 1.91 |

所以參考圖是一筆交易：**買到布料質感與六格一致性，賣掉版型自由度。**
沒有參考圖時六格可以各自是不同輪廓；有參考圖時每種輪廓都要有自己的一張圖。

純文字這條路在模型熟悉的品項（牛仔褲、T 恤、襯衫、連身裙）上表現很好；
冷門品項或特殊工法（華夫格那次）還沒有在修好的 skill 底下重測過，不要直接外推。

### 有參考圖時的原始觀察

一張參考圖只管得住**表面屬性**（顏色、水洗、材質）。變因一旦是**結構**（袖長、袖襱、領型），
主參考圖幫不上忙，模型退回自己的先驗。拿同一個韓系華夫格上衣的案例（三色 × 無袖／長袖）量無袖那三格：

| 做法 | 無袖三格的肩/胸比 | 三格離散 |
|---|---|---|
| 無參考圖，且中文漏進 prompt（`data/generated/korean-top-flat/`） | 0.848 / 0.880 / 0.893 | 5.3% |
| 一張參考圖（短袖印花 T，`korean_top_with_reference.png`） | 0.889 / 0.886 / 0.879 | 1.1% |
| ＋ 一張真無袖背心當第二參考（`korean_top_multiref.png`） | **0.795 / 0.785 / 0.789** | 1.3% |

肩線窄了約 10%，袖襱從肩線挖出弧度，邊緣有滾邊。**寫再具體的縫製語言都救不了**——
`sleeveless, with a properly curved armscye, a narrower shoulder, and the armhole finished with
a flat rib binding` 試過，比例一動也沒動，必須真的給圖。

第二張參考圖不會洩漏，前提是 prompt 裡明確切割兩張的職責。實測第二張是白色羅紋細肩帶大圓領背心，
輸出的顏色、領型、肩帶比例全部沒被帶走，長袖那三格也完全沒受影響。

一張參考圖也讓六格更一致：無袖胸寬 spread 從 3.7% 降到 0.7%，長袖從 1.0% 降到 0.3%。

## 攝影規格：白底、中灰 gutter、接觸陰影、逐項指名的不對稱

> **「零陰影」那一版已經被推翻了**，原因與數字在本節末的「對稱是自己加進去的」。
> 下面先記早期為什麼會選白底與零陰影。

規格幾經更動，現在這版是對照使用者指定的目標質感
（`house_style_target_reference.png`）調出來的，每一項都有量：

| | 目標那張 | 現行規格生出來的 |
|---|---|---|
| 背景亮度 | 253.9 | 254.0–254.1 |
| 背景平整度（標準差） | 0.56 | 0.55–0.59 |
| 接觸陰影深度 | −0.0 | −0.4 ～ 6.5 |

三個選擇各自有操作上的理由，不是美術偏好：

1. **白底 ＋ 中灰 gutter。** 背景是白的，gutter 就必須是深色才切得動。實測 gutter 偵測誤差
   **0.01–0.09%**，比「中灰底 ＋ 純白 gutter」那版的 0.27–0.54% 更準。
2. **零陰影。** 陰影會隨剪影變動，污染 `check_cells.py` 的色距。拿掉之後六格的擺放一致性從
   bbox 寬 spread 26.1% 降到 0.9%，剪影差降到 0.011 級。
3. **禁止文字。** 模型很愛自己加標號或標籤，一旦加了，切出來的卡片就毀了。

### 規格的版本歷史（避免再踩一次）

- **假人懸浮版（中灰底、正面直視）** 是最早通過驗證的一版，gutter 誤差 0.02–0.21%。
  它不是平拍，跟商品圖的目標不符。
- **平拍 ＋ off-white 背景**那版曾經寫進 `agent/scripts/grid_common.py`，但**從來沒有生過圖**
  （檔案 mtime 晚於最後一次生成）。它有一個不會自己浮現的致命傷：off-white 背景配純白 gutter，
  對比幾乎為零，`slice_grid.py` 的投影法直接瞎掉。它的 FORBIDDEN 清單裡還寫著
  `flat even lighting`，跟現在要的均勻柔光自相矛盾。
- 任何時候改這段規格，要記得它的指紋會變，跟前幾輪的圖就不該再拿來比。

### 對稱是自己加進去的

零陰影是為了讓 `check_cells.py` 好量而加的：拿掉陰影後六格 bbox 寬 spread 從 26.1% 降到 0.9%，
當時當成「一致性提升」。**那個 0.9% 就是使用者後來看到的「一眼就知道是 AI」。**
為了像素檢查好量，把圖做成了塑膠感。而且取捨的權重下錯了——色距實測 43–232、門檻只有 12，
至少四倍餘裕，柔和的接觸陰影根本吃不掉它。

HOUSE_STYLE 原本有四句話在推對稱（`shadowless` 在句中一次、FORBIDDEN 再列三次；
`arranged straight`；`directly above` ＋ `same framing/distance/scale`；FORBIDDEN 裡的
`perfect mirror symmetry` 是負面詞，對生圖模型本來就弱），推不對稱的只有埋在句中的
`slight natural creasing ... and gentle asymmetry` 兩個形容詞。

改了四件事：**接觸陰影放回來**、**逐項指名具體的不對稱**（形容詞沒用，要寫看得見的狀況：
一邊袖管翻轉露出內縫、下襬一側較低、腰頭一側翻折、身片上一道包裝摺痕、整件偏 3–5 度）、
**描述布料的行為而不只是表面**（重量、垂墜、堆疊）、**明說六件是分別擺放的**。

同一組六格內容、只換攝影規格的對照（`data/generated/loose-jeans-noref/r1` 對 `r2`）：

| | 舊規格 | 新規格 |
|---|---|---|
| 左右不對稱度（與自身鏡像的 XOR／聯集） | 0.017 | **0.093** |
| 左右下襬高低差 | 0.000 | 0.008 |
| 六格寬度 spread | 4.2% | 12.8% |
| 輪廓外圈壓暗量（接觸陰影） | 1.6 | 2.1 |

不對稱度 5.5 倍是主力；陰影只回來 31%，比視覺印象弱。gutter 偵測不受影響（誤差 0.08–0.38%）。

**天花板要知道**：gpt-image-2 的平拍有個乾淨度下限，調 prompt 逼近得了、越不過。
真要讓人相信「這件買得到」，產品層的答案是讓 ENGINE02 的真實商品照負責那件事，
生圖負責「還可以是什麼樣子」。

## 給 `slice_grid.py`：偵測方法要跟著改

白底版**不能用「平均亮度找暗帶」**——黑色牛仔褲那一格的欄平均會比中灰 gutter 還暗，把偵測騙走。
實測有效的判準是**「整條都沒有白點」**（衣服那一欄一定含得到白底，gutter 不會），
或等價的**「整條變異極低」**。兩者都準到 0.01–0.09%。

## 給 `check_cells.py`：前景遮罩的兩個陷阱

1. **中位數不能當背景。** 深色衣服占超過一半時，中位數會落在衣服上，遮罩整個壞掉
   （黑色那格前景占比量到 0.995）。白底要直接取高百分位當背景。
2. **淺色衣服會跟背景撞。** 白底上的 ecru 前景占比掉到 0.409（其他格 0.49–0.51），bbox 仍然正確，
   只是內部破。這是固定背景亮度無法避免的：中灰底時撞的是淺藍（衣服亮度 152.6 對背景 150.7，
   只差 2.0），白底時換成撞 ecru。遮罩不能只靠亮度。

色距的既有結論仍然成立：**「該變的有沒有變」取受光面與中間調的較大值，「不該變的有沒有被偷改」
取較小值**，理由見 `evals/choice_images/README.md`。

## 中文要進 prompt，不要翻成英文

**這一節原本的結論是「中文不能漏進 prompt」，錯了。** 當時看到
`data/generated/korean-top-flat/` 生出結構不成立的袖襱，而它的基準句是

```
BASELINE GARMENT: a 華夫格 top, styled 韓系, 男生, 質感, cleanfit.
```

（舊的查表流程 `PATTERN_EN`／`MATERIAL_EN`／`BASIC_COLOR_EN` 查不到的詞會原樣穿過去，
manifest 的 `unresolved` 記了那四筆），就把爛版型歸因給中文，寫成「模型收到中文等於收到亂碼」。
那一次同時改了兩個變數還下了單一結論。

真正的對照組就在同一批資料裡。`korean-top-zh` 與 `korean-top-v3` 兩份 prompt **只差基準句一行**，
相隔十分鐘生成：

| | 基準句 | 結果 |
|---|---|---|
| `korean-top-zh` | `a 華夫格 top, styled 韓系, 男生, 質感, cleanfit` | 六件結構全部正常：袖襱、羅紋、連帽、下襬都成立 |
| `korean-top-v3` | `a waffle knit top, styled Korean minimalist, men's, refined and premium, clean minimal` | 同樣正常，但版型偏向一般西式合身 |

所以：**gpt-image-2 讀得懂中文服裝詞彙**，中文不是亂碼。`korean-top-flat` 的問題是那一版的
house style（平拍），不是語言——`korean-top-zh` 同樣是中文、走假人懸浮，就沒事。

而且翻譯是有損的：「韓系」「質感」「cleanfit」翻成 `Korean minimalist`／`refined and premium`／
`clean minimal` 之後，剩下的是泛泛的形容詞，具體的版型與調性含義流失了。現行規則因此改成
**句子骨架用英文、值用 `intent` 的原文**，而且**完整的 intent 都要進 prompt，不預先篩掉欄位**
（`budget` 決定模型畫出的價位帶做工，`notes` 常常是使用者最具體的那句話）。

（附帶一提：當初想用身長/胸寬去量中英兩版的差異，但遮罩把假人也算進去了，
2.03 對 2.06 這組數字不能用。這裡只能確定中文不比英文差，「中文更好」沒有獨立量化佐證。）


## 架構後果：目前仍然是並行

`docs/system-architecture.svg` 畫的是 ENGINE02 檢索與生成模組**同時並行**，兩者吃同一組意圖。
生成模組現在只吃 ENGINE01 的 `intent`，所以**這條線仍然成立，架構圖不用改**。

但要記得這是個活的取捨：一旦把 ENGINE02 的 top-1 接回來當基準圖，生成就得等檢索，
整輪延遲變成兩者相加，那張圖就要跟著改。

## 還沒做的

- **`agent/scripts/` 的六支 Python 還沒收掉。** `hermes_image.py`（65 行）、`generate_grid.py`
  （332 行）、`grid_common.py`（480 行）都還在，而 `grid_common.py` 裡是那份沒生過圖、
  背景與 gutter 撞色的舊 HOUSE_STYLE，**現在跟 skill 互相牴觸**。跑舊腳本會生出跟 skill
  規格不同的圖，而且不會有人發現。`slice_grid.py`（151）與 `check_cells.py`（284）是量測，
  要留，但依上面兩節調整判準。
- `agent/scripts/README.md`、`bff/images/README.md` 仍在描述舊的腳本流程。
- `evals/choice_images/README.md` 還沒收錄這一輪的數字。
- 語意層檢查（FashionCLIP 圖文指派）需要 torch 與 open_clip，本機沒裝，仍未跑過。
- 重生流程尚未自動化；已生成圖的快取與固定保存尚未實作；`bff/` 的 HTTP 端點包裝尚未實作。

## 素材

`evals/choice_images/` 下，每張圖都配一份逐字 prompt 與來源圖：

| 檔案 | 內容 |
|---|---|
| `house_style_target_reference.png` | 使用者指定的目標質感（單張寬版丹寧） |
| `ref2flat_jeans_source_29178.jpg` → `ref2flat_jeans_single.png` | on-model 目錄照轉乾淨平拍 |
| `ref2flat_jeans_grid.png` | 六宮格＋參考圖，中灰底版 |
| `ref2flat_jeans_grid_white.png` | 六宮格＋參考圖，白底零陰影版（現行規格） |
| `korean_top_source_8557.jpg` → `korean_top_with_reference.png` | 一張參考圖；印花消失，但版型沒改善 |
| `korean_top_armhole_ref_45659.jpg` → `korean_top_multiref.png` | 加第二張參考圖；版型改善 |
