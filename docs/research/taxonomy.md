# ENGINE 02 類別分類法（taxonomy_v1）：來源、設計決策、覆蓋率與整合方式

> 日期：2026-09-17｜作者：taxonomy agent｜分支：`engine02-research`
> 產出：`engine02/resources/taxonomy_v1.json`、`taxonomy_map_kagl.json`、`taxonomy_map_polyvore.json`、`engine02/taxonomy.py`、`tests/test_taxonomy.py`（70 passed）、`scripts/build_taxonomy_v1.py`（可重建上述 JSON）。
> 原始統計（不進 git）：`reports/agents/taxonomy/{subcategory_counts,build_report,audit}.json`、GPT 原始檔 `gpt_en-US.txt`、`gpt_zh-CN.txt`。

## 0. 摘要

- **結構**：12 個 L1（服裝部位/商品大類）→ 89 個 L2（服裝種類），另有 2 個**橫切集合**（`coll.activewear`、`coll.ethnic`）。每個節點有穩定 id、英文與繁中標籤、中文口語同義詞、GPT id 對照、針織/梭織先驗與 HS 61/62 章節、該部位適用的屬性。
- **覆蓋率**（映射到服飾節點的商品比例；L2＝細到服裝種類）：

| 目錄 | 件數 | 映射到 L2 | 映射到任一節點（L2+L1+集合） | 非服飾 | 無法歸類 |
|---|---|---|---|---|---|
| kagl（本地） | 5,000 | 96.9% | 99.5% | 6 | 20 |
| polyvore（本地） | 3,000 | 84.4% | 90.1% | 244 | 53 |
| kagl_full（nycu） | 44,434 | 95.3% | 99.7% | 34 | 115 |
| polyvore_big（nycu） | 25,000 | 85.9% | 91.5% | 1,686 | 435 |
| kagl_polyvore（nycu） | 17,783 | 93.3% | 100% | 0 | 0 |

  所有目錄中出現的每一個 `subcategory` 值（KAGL 148 個、Polyvore 346 個）都有明確決策；建置腳本遇到沒有決策的值會直接失敗（不再有「沒列到就當 other」）。「非服飾」「無法歸類」的比例不是缺漏：它們是居家/家具/3C（Polyvore）與泛用桶（`Clothing`、`Kids`…）。
- **現行 coarse 對照表的驗證結果**：在類別層級，手寫表**大致正確**——跨五個目錄只有 24 列（值×目錄）與新分類法推得的 coarse 不同，主要是 `Wallets`（KAGL 936＋Polyvore 123 件，accessory→bag）與 `Sarees`（427 件，other→dress）。**真正的問題不是 coarse 分錯，而是**：（1）兩套詞彙沒有對齊；（2）沒有層級，所以不能放寬；（3）`other` 同時裝了美妝、內著、套裝和居家用品（見 §4.3）。
- **整合**：`filter_with_category_relaxation()` 可以直接替換 `constraints.filter_with_relaxation()`；ENGINE 01 改為輸出節點 id（封閉詞彙約 6 KB JSON）。

## 1. 來源（V＝本次實際開啟並核對內容；U＝未能開啟或未核對）

| # | 來源 | 用途 | 取得方式 | V/U |
|---|---|---|---|---|
| 1 | Google Product Taxonomy，`taxonomy-with-ids.en-US.txt`（Version 2021-09-21） | 節點 id 對照、L1 切法 | curl 下載全文 5,596 行；Apparel & Accessories 分支逐行讀過；用到的每個 id 都由建置腳本對檔案驗證，並寫入完整路徑 | V |
| 2 | 同上 zh-CN 版 | 中文命名參考 | curl | V |
| 3 | 同上 **zh-TW 版** | — | `zh-TW`、`zh-HK`、`zh-Hant` 均 404：**Google 沒有繁中版** | V（確認不存在） |
| 4 | GS1 GPC（Clothing segment） | 原想做對照 | gs1.org 回 403；gpc-browser 是 SPA，未取得內容 | **U**（不使用） |
| 5 | schema.org `category` | 只接受 Text/CategoryCode/URL，「可用 > 或 / 表示層級」，本身沒有服飾分類 | schema.org/category | V |
| 6 | Fashionpedia（Jia et al., ECCV 2020, arXiv:2004.12276） | 27 主類、19 部件、294 屬性；L2 粒度與屬性值命名 | arXiv PDF 全文；並下載 `instances_attributes_val2020.json`，讀出 46 個 categories 與各群 attributes（silhouette 25、neckline type 25、length 15、nickname 153…） | V |
| 7 | DeepFashion2（arXiv:1901.07973） | 13 類，袖長被編進類別（short/long sleeve top/outwear、vest、sling、shorts、trousers、skirt、4 種 dress） | GitHub README＋arXiv | V |
| 8 | DeepFashion Category & Attribute benchmark | 50 類、1,000 屬性 | CUHK 專案頁（數字已核對）；類別清單在 Google Drive，未開 | 數字 V／清單 U |
| 9 | ModaNet（arXiv:1807.01394） | 13 個 meta 類；**把 cardigan、sweater、jumpsuit 放在 outer** | GitHub README 表格 | V |
| 10 | iMaterialist Fashion Attribute（arXiv:1906.05750） | 8 群、228 屬性，category 群有 105 類 | arXiv＋GitHub README（清單在 Drive，未開） | 結構 V／清單 U |
| 11 | iMaterialist-Fashion 2019/2020（Kaggle FGVC） | 採用 Fashionpedia 本體 | Fashionpedia 首頁 | V |
| 12 | Fashion IQ（arXiv:1905.12794） | 3 類：Dresses、Shirts、Tops & Tees | arXiv PDF | V |
| 13 | Polyvore Outfits（Vasileva et al., ECCV 2018, arXiv:1803.09196） | 論文提到 fine-grained semantic categories；類別清單在 HF gated repo（回 401） | arXiv PDF | 論文 V／清單 U |
| 14 | WCO HS 2022 第 61 章（針織或鉤編）/第 62 章（非針織） | 針織/梭織先驗與 heading | wcoomd.org 官方 PDF，pdftotext 後逐條核對 heading 文字 | V |
| 15 | 聚陽 2026 法說簡報 | 產品線：Active & Sportswear（Performance/Outdoor、Athleisure）；Fashion Apparel（Ready to Wear、Sleepwear/Loungewear、Underwear）；Others（Swimwear、Medical）。2025 營收 Functional Sportswear 52%。1990 年梭織起家，1994 年投入針織 | PDF p.5、p.8、附錄 | V |
| 16 | 蝦皮台灣分類樹 `shopee.tw/api/v4/pages/get_category_tree` | 使用者用語：T恤、長褲、內睡衣、外套、針織/毛衣、多件式套裝、小可愛/背心、帽T/大學T、泳裝/比基尼、短褲、洋裝、裙子、上衣類、襯衫；男裝有 Polo衫、丹寧牛仔；包包下有皮夾 | curl JSON | V |
| 17 | Yahoo 購物中心分類選單 | 襯衫/雪紡、針織衫/毛衣、機能服、洋裝/套裝、T恤/帽T、POLO衫；運動女服＝背心/運動內衣、短褲/裙、瑜珈服飾；包包/皮夾；拖鞋、洞洞鞋、樂福鞋、德訓鞋 | curl HTML | V |
| 18 | UNIQLO 台灣 | 首頁 meta 描述有「T恤、質感襯衫、潮流褲裝以及機能外套」；分類頁與 API 被反爬蟲擋住 | curl | 部分 V |
| 19 | momo、PChome 24h | momo 只取得 keywords；PChome 回 429 | curl | U |
| 20 | Zalando / ASOS / Gap 導覽 | Zalando 403；ASOS 無回應；Gap 只露出頂層選單 | curl | U（不作為證據） |

本機可用記憶體約 570 MB，所以沒有開 Chromium 爬 JS 渲染的電商頁；台灣用語以 #16、#17 兩個 V 來源為準。

## 2. 設計決策

### 2.1 L1 是「搭配槽位」，L2 是「服裝種類」

| L1 | 繁中 | 現行 coarse | GPT | L2 |
|---|---|---|---|---|
| tops | 上衣 | top | 212 | tshirts, polos, shirts, blouses, tanks_camis, sweaters, cardigans, sweatshirts_hoodies, tunics, kurtas, active_tops |
| bottoms | 下身（褲/裙） | bottom | — | jeans, trousers, track_pants, leggings, shorts, skirts, capris, ethnic_bottoms |
| dresses | 洋裝/連身 | dress | 2271 | dresses, party_dresses, gowns, jumpsuits_rompers, sarees_lehengas |
| outerwear | 外套 | outerwear | 203 | jackets, coats, blazers, vests, rainwear |
| sets | 套裝 | other | 7313 | suits, tracksuits, ethnic_sets, clothing_sets |
| intimates | 內著/睡衣 | other | 213 | bras, sports_bras, underwear, undershirts, shapewear, sleepwear, loungewear, robes |
| swimwear | 泳裝 | other | 211 | bikinis, one_piece, cover_ups |
| shoes | 鞋子 | shoes | 187 | athletic, sneakers, dress_shoes, loafers, flats, heels, sandals, slippers, boots |
| bags | 包包/皮夾 | bag | 6551 | handbags, shoulder_crossbody, totes, clutches, backpacks, travel, work_laptop, waist_pouches, wallets |
| accessories | 配件 | accessory | 167 | watches, eyewear, belts, hats, scarves, gloves, ties, hair, socks, hosiery, tech, umbrellas, keychains |
| jewelry | 飾品 | jewelry | 188 | earrings, necklaces, bracelets, rings, brooches, cufflinks, sets |
| beauty | 美妝保養（非服飾） | other | 2915 | makeup, nails, skincare, fragrance, haircare, bath_body, tools |

- **放寬到 L1 時仍是同一個槽位**：「西裝外套」找不到時放寬成「外套」仍然合理；若放寬到 GPT 的 `Clothing` 就沒有意義。
- 每個節點帶 `legacy_coarse`，所以 Kansei 適用遮罩（`applies_to` 用 coarse）與 Polyvore 共現表**不用改也能繼續用**。
- L2 的粒度介於 Fashionpedia 27 主類與 Polyvore 站內細類之間。Polyvore 的 skinny/boyfriend jeans、mini/long skirts、ankle/knee-high boots 當作**版型/長度屬性**處理（Fashionpedia 也把 skinny、mini 歸在 silhouette/length 屬性）。唯一例外是洋裝分成日常、小禮服、晚禮服/婚紗：Polyvore 沒有 occasion 欄位，場合資訊只存在細類裡。
- `cardigans` 放在上衣（Fashionpedia、Polyvore、現行 coarse 都這樣放），不跟 ModaNet 放外套。`watches` 放在配件（GPT 放 Jewelry，但 Fashionpedia、蝦皮、現行 coarse 都放配件）。`cufflinks` 放在飾品。
- `wallets` 移到包包之下：GPT「Handbags, Wallets & Cases」、蝦皮「包包>皮夾」、Yahoo「包包/皮夾」三者一致。這是對現行 coarse 最大的改動（§4.2）。

### 2.2 activewear 做成橫切集合，不做成 L1

- **不做 L1 的理由**：「運動」橫跨各部位。若做成 L1：(a)「黑色短褲」放寬到 `bottoms` 時會漏掉運動短褲；(b) 運動上衣會失去 tops 的 Kansei 遮罩與 top–bottom 共現；(c) GPT 的 Activewear（5322）裡只有自行車、打獵、機車防護等專項服，一般運動 T 恤仍放在 Shirts & Tops。
- **但聚陽 52% 營收是 Functional Sportswear**，所以運動不能只是隱藏屬性：
  - 運動專屬的服裝種類獨立成 L2：`tops.active_tops`、`bottoms.track_pants`、`bottoms.leggings`、`intimates.sports_bras`、`sets.tracksuits`、`shoes.athletic`。
  - 另設 `coll.activewear`（同義詞：運動服、機能、瑜珈、健身、慢跑、athleisure…），和部位 id 一起放進 `category.values`，語意是**交集**。例如「運動短褲」→ `bottoms.shorts ∩ coll.activewear`（Polyvore `Activewear Shorts`）。放寬時先移除集合，再往上放寬部位。
- 限制：KAGL 沒有「運動 T 恤」細類（Nike T-shirts 放在 `Tshirts`），所以集合對 KAGL 上衣的召回偏低，要靠文字/影像檢索補。

### 2.3 民族服飾與美妝

- 民族服飾**依部位掛**：`Kurtas/Kurtis → tops.kurtas`；`Salwar/Patiala/Churidar → bottoms.ethnic_bottoms`；`Sarees/Lehenga Choli → dresses.sarees_lehengas`（GPT 8248）；`Kurta Sets / Salwar and Dupatta → sets.ethnic_sets`；`Dupatta → accessories.scarves`；`Nehru Jackets → outerwear.jackets`（Fashionpedia 把 nehru 列為 jacket 的 nickname）。另設 `coll.ethnic`，讓這些商品可以一起排除；建議台灣 demo 預設排除。
- **美妝**是 L1 `beauty`（`apparel: false`），保留它是為了能明確**排除**；封閉詞彙預設不提供給 GPT。
- 居家、家具、3C、食品、玩具、文具 → `non_apparel`。泛用或年齡層的桶（Polyvore `Clothing`、`Men's Clothing`、`Kids`、`Girls`、`Baby`、`Juniors`、`Maternity`、`Costumes`；KAGL `Free Gifts`，以及標題全是嬰兒商品的 `Booties`/`Rompers`）→ `unmapped`，並在 map 的 `reason` 欄寫明理由與抽樣標題。

### 2.4 針織/梭織（OEM 視角）

每個 L2 帶 `construction`（knit/woven/mixed/non_textile）與 `hs_headings`。例如：T恤 knit 61.09；毛衣/大學T/開襟衫 knit 61.10；襯衫 woven 62.05/62.06（針織款 61.05/61.06）；牛仔褲 62.03/62.04；運動套裝與泳裝 61.12/62.11；胸罩與塑身衣 62.12（不分針織與否）；襪與褲襪 61.15；內褲與睡衣 61.07/61.08 對 62.07/62.08。
**這只是節點先驗，不是商品屬性**（目錄沒有布料欄位）。用途有二：一是讓 Kansei 的 `soft_knit` 有結構依據，二是讓需求缺口可以依 61/62 章彙整給聚陽業務。鞋、包、帽不屬於 61/62 章，本次未核對所屬章節，留空。

### 2.5 中文同義詞與比對規則

- 以蝦皮、Yahoo 的分類名稱為主，再補口語用詞（短T、長T、帽T、大學T、西外、小可愛、細肩帶、瑜珈/瑜伽褲、內搭褲、棉褲、束口褲、連身裙、小禮服、白紗、夾腳拖、洞洞鞋…）。
- 比對流程：先 NFKC（全形轉半形）並轉小寫。整串完全相符就直接回傳；否則取所有同義詞出現的位置，**長詞優先、位置不重疊**（「西裝外套」優先於「外套」；「運動短褲」→ 短褲＋運動）。英文要求字邊界（`cap` 不會命中 `capris`）。以 `=` 開頭的同義詞只接受完全相符（「包」「帽」「襪」，避免「麵包」「帽T」誤中）。
- 刻意保留多義：「背心」→ 上衣背心＋背心外套；「西裝」→ 西裝外套＋西裝套裝；「運動鞋」→ 運動鞋＋休閒球鞋；「洋裝」→ 日常洋裝＋小禮服；「長褲」→ 休閒/西裝褲＋牛仔褲＋運動褲。多個部位在過濾時取聯集。
- 否定（「不要洋裝」）不處理，屬於 ENGINE 01 的 `excluded_values`。「衣服」「穿搭」回傳 `[]`。

## 3. 檔案格式

- `taxonomy_v1.json`：
  - `nodes[]`：`id, level, parent, label_en, label_zh, synonyms_zh, synonyms_en, gpt{id, match, path_en, path_zh_cn}, construction, hs_headings, attributes(L1), legacy_coarse, apparel, collections, note`
  - `collections[]`：含 `members`、`extra_source_values`
  - `attribute_defs`：sleeve_length、neckline、fit、length 沿用 Fashionpedia 的屬性名；另有 heel_height、carry、construction
  - `gpt.match`：`exact` / `broader`（GPT 節點較寬，例如 T恤→212 Shirts & Tops）/ `narrower`
- `taxonomy_map_{kagl,polyvore}.json`：`entries[value] = {node, status, reason?, counts{catalog:{legacy_coarse:n}}, implied_coarse}`，`status` ∈ `mapped | mapped_l1 | collection | non_apparel | unmapped`。
- **兩套詞彙撞名但意義不同**：`Camisoles`（KAGL 是內搭 → `intimates.undershirts`；Polyvore 是上衣 → `tops.tanks_camis`）、`Tights`（KAGL 以運動緊身褲為主 → `bottoms.leggings`；Polyvore 是褲襪 → `accessories.hosiery`）、`Rompers`（KAGL 是嬰兒包屁衣 → unmapped）。合併目錄必須看 `source` 欄，`category_mask()` 已經這樣處理。

## 4. 覆蓋率與對現行手寫 coarse 表的驗證

### 4.1 覆蓋率細項（件數）

| 目錄 | mapped (L2) | mapped_l1 | collection | non_apparel | unmapped |
|---|---|---|---|---|---|
| kagl | 4,847 | 127 | 0 | 6 | 20 |
| polyvore | 2,533 | 169 | 1 | 244 | 53 |
| kagl_full | 42,347 | 1,938 | 0 | 34 | 115 |
| polyvore_big | 21,475 | 1,399 | 5 | 1,686 | 435 |
| kagl_polyvore | 16,591 | 1,192 | 0 | 0 | 0 |

`mapped_l1` 幾乎都來自來源本身的泛用標籤：KAGL `Tops`（1,762）；Polyvore `Tops`（723）、`Shoes`、`Bags`、`Accessories`、`Jewelry`、`Outerwear`、`Beauty Products`。這些商品查 L2（例如 T恤）時不會命中，要放寬到 L1 才會出現。這是資料本身的限制。

### 4.2 與 `scripts/prepare_catalog.py` 現行 coarse 不一致的地方

| 來源值 | 目錄 | 現行 | taxonomy 節點 | 推得 coarse | 件數 | 判斷 |
|---|---|---|---|---|---|---|
| Wallets | kagl / kagl_full | accessory | bags.wallets | bag | 110 / 936 | 刻意改動（GPT、蝦皮、Yahoo 一致） |
| Wallets / Men's Wallets / Men's Money Clips | polyvore / polyvore_big | accessory | bags.wallets | bag | 11 / 101+21+1 | 同上 |
| Sarees | kagl / kagl_full | other | dresses.sarees_lehengas | dress | 29 / 427 | 刻意改動：全身單件，槽位等同洋裝 |
| Lehenga Choli | kagl_full | other | dresses.sarees_lehengas | dress | 4 | 同上 |
| Accessory Gift Set | kagl_full | other | accessories | accessory | 111 | 標題是「領帶+袖扣+口袋巾」 |
| Travel Accessory | kagl / kagl_full | accessory | bags | bag | 4 / 16 | 標題實為「Benetton ... Bags」 |
| Rain Trousers | kagl_full | bottom | outerwear.rainwear | outerwear | 2 | GPT：Outerwear > Rain Pants |
| Salwar and Dupatta | kagl_full | bottom | sets.ethnic_sets | other | 7 | 兩件式 |
| Ties and Cufflinks | kagl_full | jewelry | accessories.ties | accessory | 2 | 以主件歸類 |
| Booties、Rompers | kagl_full | accessory、top | unmapped | — | 12、12 | 全是嬰兒商品 |
| Wristbands | kagl / kagl_full | other | accessories | accessory | 1 / 4 | 同一值在 KAGL 被分到兩個 coarse |
| Belts、Tshirts、Shorts、Scarves、Ties（少數列） | kagl_full | top/accessory/other | 各自的 L2 | — | 3、1、2、1、5 | **來源資料異常**（category2 放錯桶）；taxonomy 只看 articleType，所以不受影響 |

結論：現行 coarse 表**沒有系統性錯誤**，不一致處都是小量或刻意改動。

### 4.3 現行 `other` 實際混了哪些東西

| 目錄 | beauty | intimates | dresses（紗麗） | sets | swimwear | accessories | non_apparel | unmapped |
|---|---|---|---|---|---|---|---|---|
| kagl | 467 | 196 | 29 | 9 | 1 | 1 | 6 | 20 |
| kagl_full | 2,400 | 2,276 | 431 | 131 | 17 | 121 | 34 | 91 |
| polyvore_big | 2,272 | 152 | — | 8 | 97 | — | 1,686 | 435 |

`kagl_full` 的 `other` 裡有 2,276 件內著/睡衣，正好對應聚陽 Sleepwear/Loungewear 與 Underwear 產品線；在現行 coarse 下，這些商品既無法被指定，也無法被排除。**這是改用 taxonomy 對聚陽最直接的價值。**

### 4.4 來源標籤可信度（粗略代理指標）

計算本地目錄中「商品標題含該 L1 任一英文同義詞」的比例（`reports/agents/taxonomy/audit.json`）：
- KAGL：上衣 98.9%、下身 91.0%、鞋 91.4%、包 99.5%、配件 99.4%
- Polyvore：上衣 89.4%、下身 86.5%、外套 94.9%、飾品 95.4%、鞋 73.6%、包 77.5%、配件 74.8%

這只是**下界式代理指標**：Polyvore 標題常常只有品牌或型號，沒命中不代表標錯，也不能當成人工標註的正確率。美妝的比例偏低（44–57%），是因為同義詞沒有收品牌與劑型詞。

## 5. 整合方式（交給協調者；未修改任何既有檔案）

### 5.1 ENGINE 01 的封閉詞彙

把 `Taxonomy.closed_vocabulary(max_synonyms=4)` 交給 GPT。壓縮後 JSON 約 6.2 KB，內容是服飾 L1/L2（不含美妝）、collections 和三條規則：

```json
{"version":"taxonomy_v1",
 "category":{"outerwear":{"zh":"外套","syn":["外搭","外衣"],
   "children":{"outerwear.blazers":{"zh":"西裝外套","syn":["西外","休閒西裝","西裝上衣","西裝"]}}}},
 "collections":{"coll.activewear":{"zh":"運動機能服飾","syn":["運動服","運動服飾","運動風","機能服"]}},
 "rules":["category.values 只能填上面的 id；不確定細類時填 L1",
          "「運動/機能/瑜珈」跨部位需求另填 collection id，與部位 id 一起放",
          "使用者只說「衣服」「穿搭」時 category 保持 unmentioned"]}
```

System prompt 要寫明：`constraints.category.values` 只能填這些 id；使用者說出細類就填 L2，只說到部位就填 L1；有多件商品就填多個 id；有運動需求時加上 `coll.activewear`。
**保險機制**：就算 ENGINE 01 仍輸出中文（「西裝外套」）或舊的 catalog 值（「Blazers」「Tshirts」），`resolve_category_values()` 也會轉成節點 id，所以這個 hook 不必等 ENGINE 01 改好就能上線。
`retrieval_text` 仍要用英文 catalog 詞彙（T1 結果顯示 BM25 需要）。當 category 是 id 時，`build_retrieval_text()` 應改呼叫 `Taxonomy.retrieval_terms(node_id, catalog)`，它會回傳英文標籤加上該節點的 catalog 細類值。

### 5.2 階層放寬（取代「category never relaxed」）

`engine02/pipeline.py` 第 162 行：

```python
# 現在
fr = filter_with_relaxation(items, req.constraints, max(arm.min_results, k), excluded)
# 改成
from .taxonomy import filter_with_category_relaxation
fr = filter_with_category_relaxation(items, req.constraints, max(arm.min_results, k), excluded,
                                     catalog=self.catalog.name)
```

行為（已有單元測試）：
1. 把 category 值解析成節點與集合；解析失敗就**完全退回舊行為**。
2. 依序嘗試：(L2 ∩ 集合) → (父節點 ∩ 集合) → … → (L1，不含集合) →〔不限類別，僅在 `allow_drop_category=True` 時才走到〕。
3. 除了最後一級，每一級都只跑**非破壞性**的其他 slot 放寬（allow_unknown、drop season/occasion、budget×1.2），不跑 `color:drop`、`budget:drop`。所以「藍色西裝外套」會先變成「藍色外套」，而不是「任意顏色的西裝外套」。這是一個取捨：顏色通常是使用者明說的，而同一 L1 下的兄弟類別仍在同一個搭配槽位。
4. `fr.relaxed` 會記錄 `category:outerwear.blazers→outerwear（西裝外套→外套）`，`explain.template_reasons` 會自動說明「放寬了 category」，不需要改。
5. 預設**不會丟掉類別**，維持「類別錯了就不算推薦」的原則。

`required_values`（critique）與 `excluded_values` 維持完全比對、不放寬。建議下一步讓 `excluded_values["category"]` 也走 `resolve_category_values`，這樣可以直接排除 `beauty` 或 `coll.ethnic`。

### 5.3 `GET /vocabulary`

在 `api.py` 的 `vocabulary()` 加入以下欄位，原有欄位保留：

```python
from .taxonomy import load_taxonomy
tax = load_taxonomy()
out["taxonomy"] = tax.vocabulary_payload(items, engine().catalog.name)  # nodes[{id,parent,level,label_zh,label_en,apparel,n_items}], collections
out["closed_vocabulary"] = tax.closed_vocabulary(max_synonyms=4)
```

`n_items` 是該節點（含子孫）在目前目錄中的商品數，ENGINE 01 可以用它避免輸出目錄裡根本沒有的節點。

### 5.4 Kansei 適用遮罩與共現

- 短期：不需要改（`legacy_coarse` 與 category 欄一致，只有 §4.2 的 24 列例外）。
- 中期：把 `pipeline.py` 第 125 行的 `cats` 改由 `Taxonomy.item_node_ids(items, catalog)` 產生，並讓 `applies_to` 接受 L1/L2 id。這樣 `crisp_collar` 可以只套用在 shirts/polos/blazers，而不是所有上衣；`soft_knit` 則可以依 `construction=knit` 決定。這一步需要重算 c(i,d) 並跑 ablation，本次沒有做。

## 6. 限制與未做

- 同義詞表依電商分類名稱人工整理，**沒有用真實使用者查詢評估召回**；60 個測試字串是規格，不是評估。建議從 ENGINE 01 的對話紀錄抽 200 句人工標註後再量。
- 沒有做實驗證明階層放寬會提升 NDCG。它是規則上的修正：原本「西裝外套」這類值會得到空結果。可以用 T1 的查詢集重跑，以「是否符合使用者要的 L1」為真值做配對比較。
- 未取得的來源（U）：GS1 GPC、DeepFashion 50 類清單、Polyvore Outfits 類別清單、momo/PChome/UNIQLO 分類頁。
- 針織/梭織與 HS 只是節點先驗，目錄沒有布料資訊。
- `kagl_polyvore` 覆蓋率 100%，是因為合併時已經先濾掉美妝與居家，不代表對應表特別好。
