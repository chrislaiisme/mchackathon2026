---
name: concept-image-director
description: "Turn one structured intent into a single six-cell flat-lay contact sheet that shows the user possibilities they had not thought of, and record in Chinese what each cell varies."
version: 0.1.0
---

# concept-image-director

把一組意圖變成**一張**六格平拍商品圖，並記下每一格變動了什麼。

只生一張。不要一件一件生、不要切圖、不要做像素層檢查、不要決定要問使用者哪個欄位、不要檢索排序。

## 輸入

- `intent`：結構化意圖。第 2 輪起吃 `updated_intent`，型別相同。
- `cells`：六格差異表，一格一列，每列是 `{ 欄位: 中文值 }`。沒給就自己挑。
- `question`：選配。差異值來自 `ClarifyingQuestion` 時一起給，用來填每格的 `option_id`。

只吃意圖，不吃檢索結果，也不吃參考圖。衣服長什麼樣完全由文字決定。

## 步驟

1. 讀完整的 `intent`，定出六格共用的鎖死條件。
2. 定六格：`cells` 有給就用，沒給就自己挑。
3. 組 prompt。
4. 呼叫 `image_generate`。
5. 看圖自檢，不過就用同一份 prompt 重生一次。
6. 輸出 manifest。

## 意圖怎麼進 prompt

**完整的 `intent` 都要進去，不要先篩掉欄位。** 每個欄位都是使用者給的資訊，丟掉一個就少一分
貼近他要的東西。

**中文值照原文放，不要翻成英文。** 服裝詞彙的文化語義翻譯會流失——「韓系」「質感」「cleanfit」
翻成英文之後剩下的是泛泛的形容詞。生圖模型讀得懂這些中文詞。句子的骨架維持英文，
值直接嵌進去：`a 華夫格 top, styled 韓系， 男生， 質感， cleanfit`。

只有一種情況要自己補英文：**中文詞指的是一個具體的做法，而那個做法需要講清楚才畫得出來**
（例如某種接縫或收邊）。那時候中文原詞留著，後面補一句英文的視覺描述，不要拿英文取代中文。

`inferred_fields` 列到的欄位**一樣鎖死**：生圖沒有軟條件，一張圖要嘛畫了要嘛沒畫。
只在 manifest 的來源標記成 `intent_inferred`，讓前端能跟使用者親口講的區分顯示。

## 自己挑六格

先決定要發散還是要問：

- 有 `question` → **`variants`**：六格是那一題的選項，只差那一個欄位。單變因是它存在的理由。
- 沒有 `question` → **`concepts`**：意圖是開放的，六格要讓使用者**看見他沒想到的可能**。

只挑 `intent` 裡**沒講**的東西，講過的是鎖死條件，拿來當變因會自打嘴巴。
`concepts` 模式**六格不准都在同一個軸上**——六種顏色不是六個概念，那是一題色票。

### 三類變因，依這個比重分配

**1. 設計細節與加工 — 給四格，這是整支 skill 的重點。**

使用者自己想得到的東西，他不需要我們。這一類的價值全部來自他沒想到的那幾格。
不要背清單，用下面五條路現場想，每條路都問同一件事：**這個品項還能從哪裡借東西？**

| 路 | 問法 |
|---|---|
| 借別的品類 | 把工裝／軍裝／運動／正裝／內衣／戶外裝的做法搬過來 |
| 掛上硬件與配件 | 這件衣服上可以多出什麼會反光、會晃、會扣的東西 |
| 材質衝突 | 拿一塊性質完全不同的布接上去 |
| 把結構翻出來 | 本來藏起來的做法，故意露在外面或擺到錯位 |
| 表面工藝 | 在布面上做加工，而不是換顏色 |

三個約束：

- **欄位名固定寫 `design_detail`，位置寫 `detail_placement`。** 不要自己另外取名。
  表面工藝（漂白、噴漆、塗層、刺繡）也算這一類，一樣用 `design_detail`，不要另開欄位。
- **一格只加一個主要細節。** 疊兩三個就看不出是哪一個被喜歡，ENGINE03 也解讀不了。
- **細節要放得不對稱。** 刷破只在一邊膝蓋、補丁只在一條褲管、褲鏈只掛一側、拼接只做單邊、
  口袋左右不同大小。左右對稱地複製同一個細節，整件看起來就像樣板而不是設計過的衣服。
  **不對稱只發生在細節上**——衣服本身要平整、正面、對稱地擺好，那是商品照該有的樣子。
- **要在一格的大小裡看得見。** 一格只有三分之一寬、一半高，縮成卡片更小。車線顏色、鈕釦材質、
  標籤、內裡在那個尺寸下等於不存在，選了就浪費一格。選會改變輪廓或造成大面積對比的。
- **要是這間公司做得出來的成衣，不是舞台裝。** 天馬行空是指做法出人意料，不是指它不能量產。
  一格如果要加吊牌級的說明才看得懂，那是概念藝術不是商品。

**2. 版型與結構 — 給一到兩格。**

taxonomy 有對應軸的就用那個軸名：`fit`、`length`、`neckline`、`sleeve_length`。
品項自己的輪廓（桶褲、喇叭、A 字裙、落肩箱型）taxonomy 沒有，一律寫 `silhouette`，不要自己取名。
值取自 `engine02/resources/taxonomy_v1.json` 的 `attribute_defs`，那份是英文鍵＝中文值，
`fit`／`length`／`neckline`／`sleeve_length` 四軸可用；`construction` 不要用（像素層看不出來），
`heel_height`／`carry` 是鞋包的軸。品項合不合理自己判斷：裙子沒有 `sleeve_length`，褲子沒有 `neckline`。

鎖死條件劃出的範圍不等於只有一個樣子——意圖說「寬鬆」，寬直筒、寬錐形、balloon 都還在範圍內。

版型完全由文字決定，所以六格可以各自是不同的輪廓。**品項越冷門、工法越特殊，越要逐格確認
結構真的做得出來**——一格說不出哪裡怪的時候，先查它的接縫、開口與收邊在實物上成不成立。

**3. 表面屬性 — 最多一格，不要當主軸。**

`colors`、`pattern`、`material`。最安全但資訊量最低，用掉一格當基準色就夠了。
這跟「六格底色要有分別」不衝突：設計細節那幾格**本來就該順手帶著自己的顏色**，
顏色是細節的一部分，不是另外一個變因軸。

**不要留空格。** 湊不滿六格就請呼叫端補值或改用文字選項，空白格子模型會自己填東西進去。

## 組 prompt

五段，順序不要換：

```
<HOUSE_STYLE 逐字貼上>

BASELINE GARMENT, identical in every cell except where stated: <基準句>.

<差異開場白>
Cell 1: <第 1 格>
...
Cell 6: <第 6 格>

Anything not named as that cell's exception must stay exactly consistent with the baseline
across every cell: <這輪真的鎖死的屬性，逐項列>, same lighting, same framing, same scale.
```

### HOUSE_STYLE — 逐字貼上，一個字都不要改寫

```text
A studio product contact sheet: exactly 6 photographs arranged in a strict grid of 3 columns and 2 rows.

GRID: 6 equal-sized cells separated by uniform mid-grey gutters of even width, clearly darker than the white background inside the cells. Every cell uses the same camera, the same lens, the same distance and the same garment scale, and every garment is laid out the same way, so the 6 garments can be compared side by side. No garment or background tone crosses a gutter.

IN EVERY CELL: clean e-commerce product photography of one real sample garment on its own, laid flat and shot straight from directly above - no mannequin, no dress form, no body, no head, no hands, no skin, no hanger, no rail. The garment is freshly pressed and laid out neatly and squarely to the frame: front facing up, centred, shoulders level, hem level, both sleeves or legs straight and evenly placed, the fabric smoothed completely flat. No rumpling, no twisting, no bunching, no crumpled folds, no stray wrinkles anywhere - a clean pressed sample prepared for a catalogue shoot.

THE CLOTH IS REAL CLOTH: it has weight and body. Fine visible weave texture, subtle yarn variation, crisp topstitching, clean seams, and the soft natural thickness of the material at collars, cuffs, waistbands and hems. The piece is softly filled so it reads as a three-dimensional object with depth, never pressed into a flat graphic and never a papery cut-out.

LIGHT: soft even studio light, with a gentle soft contact shadow directly beneath the garment where it meets the surface, grounding it as a physical object with weight. No hard cast shadow, no long directional shadow, no shadow reaching the gutters. Seamless pure white background inside every cell, flat and even, with no gradient and no vignette. The whole garment visible with a small even margin.

FORBIDDEN anywhere in the image: wrinkles, creases, rumpled or twisted or bunched fabric, mannequins, dress forms, bodies, hangers, clothing rails, 3D renders, CGI, mockup templates, vector illustration, plastic or glossy artificial surfaces, flat lifeless fabric, text, letters, numbers, captions, labels, logos, watermarks, price tags, props, people, reflections.
```

衣服要**平整、正面、對稱地擺好**，不對稱只發生在各格自己加的設計細節上（見「自己挑六格」）。
下面三件為了「切得動、比得動」而存在，不准改：**白底配中灰 gutter**（背景是白的，gutter 就必須是
深色才切得動）、**陰影不准碰到 gutter**（碰到就切壞）、**禁止文字**（模型很愛自己加標號，
加了切出來的卡片就毀了）。

版面真的只能降時，整段裡只有 `6`／`3 columns`／`2 rows` 這三個數字可以動；但那會改掉這段的
指紋，跟前幾輪的圖就不該再拿來比。

### 基準句

直接從 `intent` 描述那件衣服，句子的骨架用英文、值用 `intent` 的原文。不要用逗號硬串成
一串字——生圖模型對完整句子的遵循度比清單高。顏色、花色、材質當形容詞放在品項名前面；
其餘接成子句：`in <fit> fit`、`with <collar> neckline`、`at <length> length`、
`for <occasion> occasions`、`for the <season> season`、`styled <style_keywords>`。

`notes`、預算這些不屬於基準句的欄位，另起一句接在基準句後面，一樣用原文。

永遠複數的品項（jeans、trousers、shorts、leggings、tights、overalls…）要寫 `a pair of`；其餘照 a／an。

**不要寫 `COMPLETELY PLAIN` 之類的全面禁令**——那會把每一格自己要加的設計細節一起壓掉。
基準是素的，細節由各格的例外句加上去。

### 差異開場白

- 六格只差同一個欄位：
  `Each cell differs from the baseline in exactly ONE attribute, in this reading order (left to right, top row first):`
- 六格差好幾個軸：
  `Each cell is a different variation of the same garment, in this reading order (left to right, top row first). They differ from the baseline ONLY in the attributes named below:`

### 每一格與收尾句

每格一行。第 1 格放 `intent` 裡目前的值——變因欄位被排除在鎖死條件外，基準句裡沒有它，
第 1 格必須自己講回來，否則模型會亂挑一個值。`intent` 裡本來就沒值時才留白。

```
Cell 1: the current choice: medium blue wash.
Cell 2: identical to the baseline, EXCEPT dark navy wash.
```

收尾句**只列這一輪真的鎖死的屬性**。寫死 `same fit, same length` 會在剛好變動這兩軸時
讓 prompt 自己跟自己打架。`same lighting, same framing, same scale` 三項永遠都在。

## 呼叫 image_generate

`prompt` 給組好的整份，`aspect_ratio` 給 `portrait`。不要給 `image_url`，也不要給
`reference_image_urls`。

`aspect_ratio` 只是表態不是保證，尺寸由模型自己推。畫質檔位讀的是 `~/.hermes/config.yaml` 的
`image_gen` 設定，不是這個工具的參數，不要嘗試指定。

## 送出前的三關

**一、挑完六格，還沒組 prompt：**

1. 六格的差異各用一句話講出來，六句話長得不一樣嗎？只有一個詞不同（藍的／黑的／灰的）就是沒發散。
2. 每一格縮到卡片大小，還看得出它跟基準不一樣嗎？
3. 整張掃過去像六件不同的衣服，還是同一件拍了六次？六格裡不要超過三格共用同一個底色。
4. 至少兩格是使用者自己不會想到的嗎？六格全是這個品項的常見做法，他看完只會覺得「就這樣啊」。

**二、prompt 組好，還沒送出：**

5. HOUSE_STYLE 跟上面那段逐字相同。
6. `intent` 的每個非空欄位都在 prompt 裡出現過，沒有整個被漏掉的。
   `keywords` 的欄位名全部出自上面那張表，`design_detail` 的值是名詞短語不是句子。
7. 每個變因欄位都不在收尾句的鎖死清單裡。
8. prompt 裡沒有殘留 `the reference image` 之類指涉外部圖片的字樣。

**三、圖生出來之後：**

9. 六格都在，3 欄 2 列，沒有空格；gutter 是中灰的、貫穿整張，陰影沒有碰到 gutter。
10. 沒有任何文字、標號、標籤、浮水印；沒有人體、假人、衣架。
11. 每格都看得出它自己的變因；沒有一格是真實世界做不出來的結構。
12. 六件都平整、正面、對稱地攤好，沒有皺褶、扭曲或亂折；不對稱只出現在設計細節上。

不過就**用同一份 prompt 重生一次**。不要改 prompt——改了就分不清是 prompt 的問題還是模型的
隨機性。第二次還不過就回報失敗、兩張都留著，交給呼叫端決定要不要改用文字選項。
像素層的事（gutter 位置誤差、色距、剪影差）不在這裡判。

## 輸出

```json
{
  "session_id": "demo-jeans",
  "round": 1,
  "image_path": "data/generated/demo-jeans/r1/grid.png",
  "grid": { "cols": 3, "rows": 2 },
  "mode_hint": "concepts",
  "locked_zh": { "item_type": "牛仔褲", "material": "丹寧", "fit": "寬鬆" },
  "cells": [
    {
      "index": 1,
      "keywords": { "item_type": "牛仔褲", "material": "丹寧", "fit": "寬鬆",
                     "colors": "灰藍丹寧", "design_detail": "單側金屬褲鏈",
                     "detail_placement": "右腰與右前皮帶耳" },
      "keyword_sources": { "item_type": "intent", "material": "intent_inferred",
                           "fit": "intent", "colors": "axis",
                           "design_detail": "axis", "detail_placement": "axis" },
      "prompt_fragment": "identical to the baseline, EXCEPT grey-blue denim with one detachable metal chain clipped only on the wearer's right waist and right front belt loop, the left side clean.",
      "option_id": null
    }
  ]
}
```

- `keywords`：結構化的**欄位 → 中文值**，完整描述（鎖死的 ＋ 這格變動的）。不要只存描述句，
  下游要的是欄位層級的東西。中文值跟 `intent` 同一套詞彙——英文只活在 prompt 裡，不是介面契約。

  **欄位名只能用下面這些，不准自己發明。** 每格自己取名字的話，ENGINE03 沒辦法聚合
  「使用者喜歡哪一類東西」，`WeightAdjustment.field` 也對不上：

  | 欄位 | 用在哪一類 | 值的例子 |
  |---|---|---|
  | `intent` 原有的欄位（`item_type`、`colors`、`pattern`、`material`、`occasion`、`season`、`style_keywords`） | 鎖死條件與表面屬性變因 | 牛仔褲、水洗黑、丹寧 |
  | `fit`／`length`／`neckline`／`sleeve_length` | 版型變因，taxonomy 有對應軸時 | 寬鬆、長版、圓領 |
  | `silhouette` | 版型變因，taxonomy 沒有的品項輪廓 | 寬鬆弧形桶褲、落肩箱型 |
  | `design_detail` | 設計細節與加工（含表面工藝） | 單側金屬褲鏈、單側淺色補丁、單側大面積漂白 |
  | `detail_placement` | 那個細節放在哪 | 右腰與右前皮帶耳、右膝 |

  **`design_detail` 的值要是一個可以被重複指名的名詞短語**，不是句子。「單側金屬褲鏈」可以，
  因為使用者點了這格之後，下游就能記下「這個人喜歡單側金屬褲鏈」並在往後的輪次沿用；
  「在右腰掛一條可拆的金屬鏈子垂在側邊」不行，那是描述，收集不起來。
  位置寫在 `detail_placement`，不要混進 `design_detail` 的值裡。
- `keyword_sources`：`intent`（使用者明說）／`intent_inferred`（ENGINE01 推論）／
  `question`（來自選擇題）／`axis`（這支 skill 自己挑的）。下游必須分得出使用者否決的是
  **他自己講過的條件**還是**我們替他補的值**——前者要回頭改意圖，後者換個值再生一次就好。
- `prompt_fragment`：這格在 prompt 裡**逐字**的那一句。事後重寫的說明不算。
- `option_id`：值來自 `ClarifyingQuestion` 時填那個選項的 id，直接對上
  `FeedbackInput.selected_option_id`；其餘填 `null`。
- `mode_hint`：`variants` 或 `concepts`。這支 skill 的流程不看它。

變因軸不一定是 `intent` 的欄位（例如裙子的 `length` 在 taxonomy 裡而不在 `intent` 裡），
下游收到這種屬性名要能認得或安全忽略。

## 不要做的事

- 不要一件一件生。一次一張六格。
- 不要為了「乾淨」而篩掉 `intent` 的欄位，也不要把中文值翻成英文再放進去。
- 不要自己發明 `keywords` 的欄位名。固定那幾個，值才聚合得起來。
- 不要把變因欄位同時寫進鎖死條件——同一個屬性講兩次會互相打架。
- 不要改寫 HOUSE_STYLE，也不要「照這個風格」重寫一遍。逐字貼上。
- 不要留空格。
- 不要點名真實品牌或設計師。文字描述維持抽象：顏色、剪裁、場合、材質。
- Pinterest 原圖不進 prompt、不進畫面，它只在內部算趨勢相似度。
- 不要無限重試。同一份 prompt 最多重生一次。
