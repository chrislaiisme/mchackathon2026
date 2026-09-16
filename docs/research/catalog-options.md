# ENGINE 02 商品目錄資料集選型（2026-09-17）

> 範圍：替 ENGINE 02（時尚檢索＋排序）選一個**可公開下載、授權對贊助商（公司）相對安全**的商品目錄，並提供統一 schema 的轉檔腳本。
> 驗證方式：HF Hub API（`dataset_info`、README）、dataset-viewer `/size`、`/first-rows`、`/statistics` 端點，以及只讀 parquet 非影像欄位。**沒有**整包下載，沒有使用 HF token。
> 下表的「授權」一律是「HF 卡片上寫的」，不是法律意見；Marqo 系列卡片本身都寫 *We do not own this dataset*，上游影像版權多屬原零售商／網站。

## 1. 候選資料集（已驗證欄位）

| 資料集 | 可否下載 | 筆數 | 影像尺寸（第一筆） | 卡片授權 | color | season | occasion | gender | price | outfit | 主要欄位 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Marqo/KAGL** | 公開 | 44,434 | 1800×2400 | MIT（上游 Kaggle paramaggarwal，影像來自 Myntra；Kaggle 端授權本次未驗證） | ✔ baseColour | ✔ season | ✔ usage | ✔ gender | ✘ | ✘ | image, gender, category1/2/3, baseColour, season, year, usage, text, item_ID |
| **Marqo/polyvore** | 公開 | 94,096（21,587 套 outfit） | 274×400 | apache-2.0（上游 xthan/polyvore-dataset，爬自 polyvore.com） | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ 由 item_ID `<set_id>_<index>` 推得 | image, category, text, item_ID |
| Marqo/fashion200k | 公開 | 201,624 | 266×430 | apache-2.0 | ✘（只在文字裡） | ✘ | ✘ | ✘ | ✘ | ✘ | image, category1/2/3, text, item_ID |
| Marqo/deepfashion-inshop | 公開 | 52,591 | 224×224 | **未標** | ✔ color | ✘ | ✘ | category1=men/women | ✘ | ✘ | image, category1/2/3, color, description, text, item_ID |
| Marqo/deepfashion-multimodal | 公開 | 42,537 | 153×224 | **未標** | ✘ | ✘ | ✘ | category1=men/women | ✘ | ✘ | image, category1/2/3, text, item_ID |
| Marqo/atlas | 公開 | 78,370 | 1000×1447 | MIT | ✘ | ✘ | ✘ | ✔ | ✘ | ✘ | image, gender, category, sub-category, text, item_ID（印度電商，民族服飾多） |
| Marqo/iMaterialist | 公開 | 721,065（71.5 GB） | 500×500 | **未標** | ✔（多 null） | ✘ | ✘ | ✔ | ✘ | ✘ | image, gender, color, material, sleeve, pattern, neckline, style, category, item_ID（**無標題文字**） |
| ashraq/fashion-product-images-small | 公開 | 44,072 | **60×80** | **未標**（上游 Kaggle small 版） | ✔ | ✔ | ✔ | ✔ | ✘ | ✘ | id, gender, masterCategory, subCategory, articleType, baseColour, season, year, usage, productDisplayName, image |
| mvasil/polyvore-outfits | **gated（auto）**，無 token 401 | 卡片：261,058 items / 68,306 outfits | — | YAML 標 cc-by-4.0，但正文寫「僅限學術與非營利研究」「作者不擁有影像版權」→ **自相矛盾** | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ | README 可讀，資料檔（含 categories.csv）GatedRepoError |
| owj0421/polyvore（+ owj0421/polyvore-outfits） | 公開 | 251,008 items；outfit json（nondisjoint train 53,306 套…） | 300×300 | other（「同原始 Polyvore Outfits 授權」） | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ set_id→item_id | item_id, image, url_name, title, description, category（第一筆 title/description 為空） |
| Stylique/Polyvore | 公開 | viewer 無 size | — | mit（轉載，授權同上游問題） | — | — | — | — | ✘ | ✔ 只有 set_id/items，無影像 | items[index,item_id], set_id |
| einrafh/hnm-fashion-recommendations-data（= dinhlnd1610/HM-…） | 公開 | articles 105,542；transactions 31.8M | **無影像** | **未標**（上游 Kaggle H&M 競賽資料，競賽規則對商用有限制，本次未查證條文） | ✔ colour_group_name | ✘ | ✘ | index_group_name（Ladieswear…） | transactions 內 price 為**正規化值** | ✘（只有共購） | article_id, prod_name, product_type_name, product_group_name, colour_*, department/section/garment_group, detail_desc |
| tomytjandra/h-and-m-fashion-caption | 公開 | 20,491 | 1166×1750 | 未標 | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | text, image 兩欄 |
| crawlfeeds/asos-fashion-products-dataset | 公開 | 1,000（免費樣本） | 只有 URL | other（商業爬蟲樣本） | ✔ | ✘ | ✘ | 麵包屑 | ✔ AUD | ✘ | 38 欄含 price/original_price/currency/image_urls |
| UniqueData/asos-e-commerce-dataset | 公開 | 30,845 | 只有 URL | **cc-by-nc-nd-4.0**（禁商用） | ✔ | ✘ | ✘ | ✘ | ✔ | ✘ | url, name, size, category, price, color, sku, description, images |
| DBQ/Farfetch.Product.prices.* | 公開 | UK 613,571 | 只有 URL | unknown | ✘ | ✘ | ✘ | URL 內 | ✔ GBP + EUR | ✘ | brand, category1/2/3_code, title, imageurl, full_price, price, price_eur |
| gatech-scheller-ai-in-business/myntra-products | 公開 | viewer 無 size | 只有 URL | apache-2.0 | ✘ | ✘ | ✘ | 名稱內 | ✔ INR | ✘ | URL, Product_id, BrandName, price, name, description |
| Gssmc/myntra_dataset | 公開 | 15,000 | 無影像 | mit | ✔ | ✘ | specifications 內 Occasion | ideal_for | ✔ INR | ✘ | 24 欄（variant_price, complete_the_look 文字…） |

搜尋關鍵字：h&m / polyvore / outfit / fashion price / fashion product / myntra / zalando / farfetch / asos / shein / fashion recommendation。**找不到同時具備「影像＋價格＋outfit」且授權明確可商用的公開 HF 資料集**；有價格的全都是「只給圖片 URL 的爬蟲表」（抓圖＝直接複製零售商版權素材，且多為 unknown / NC 授權）。

### 驗證時發現的注意事項
- **Marqo/polyvore 其實有 outfit 分組**：item_ID 格式 `<set_id>_<index>`（Maryland Polyvore, Han et al. 2017），94,096 筆全部符合；每套 1–8 件，中位數 4。不需要 gated 的 mvasil 版就能算共現。
- Marqo/polyvore 類別很髒：含大量美妝、家居、食物（Floral Decor、Lipstick、Sofas…），轉成 coarse 後約 21% 是 `other`。
- Marqo/KAGL 原圖 1800×2400、12.7 GB；即使串流也要下載所在 parquet 的影像區塊，5,000 筆約 8 分鐘。ashraq 版只有 60×80，不適合做影像嵌入。
- KAGL 約 6% 是保養/美妝/內衣（coarse=`other`），`dress` 很少（全庫 category2=Dress 在 viewer 統計的部分樣本中僅 44/14k）。
- KAGL `season`/`usage` 有少量 null（樣本中 0.4%/0.1%），已保留為 null。
- H&M transactions 的 price 是縮放後的相對值，不是真實金額，不能當價格欄位。
- 所有來源都**沒有真實可用的價格**；統一 schema 的 `price`/`currency` 目前一律 null。價格若是 demo 必需，只能由贊助商提供自有商品資料，或明確標示為合成值（本腳本不做）。

## 2. 建議

**主目錄：`Marqo/KAGL`**
- 唯一一個同時有 color / season / occasion(usage) / gender 四個結構化屬性的公開影像資料集，直接對應 ENGINE 02 的 hard filter 與 kansei 概念；覆蓋率 ≥99.6%。
- 卡片標 MIT，公開不需 token（Kaggle 上游授權本次未查證）。仍需提醒贊助商：影像實為 Myntra 商品圖，MIT 標籤不等於影像著作權清楚，對外 demo 前請法務確認。
- 圖片品質高（原圖 1800×2400，縮到 384 px 仍清楚）、標題為乾淨商品名。
- 缺點：無價格、無 outfit、無長描述；dress/jewelry 很少；印度電商特有品項（Kurtas、Sarees）。

**次要（outfit 共現）：`Marqo/polyvore`**
- 公開、apache-2.0（卡片）、有 21,587 套 outfit → 可算 coarse×coarse 共現，供 `engine02/compat.py` 的 NPMI 使用。
- 只用它的**類別共現統計**（聚合數字）比直接展示它的影像風險低；它不適合當主目錄（無屬性、類別雜）。
- 不建議再用 `mvasil/polyvore-outfits`：gated、卡片正文限學術/非營利、且與 YAML 的 CC-BY 自相矛盾。

不建議：iMaterialist（71 GB、無標題）、fashion200k（無結構屬性）、DeepFashion 系列（卡片未標授權，上游 DeepFashion 一般認知為限非商業研究，本次未查證）、H&M（無影像、上游競賽規則）、ASOS/Farfetch 價格表（只有外連圖、授權 NC/unknown）。

## 3. 轉檔腳本

`scripts/prepare_catalog.py`，支援 `Marqo/KAGL`、`Marqo/polyvore`、`ashraq/fashion-product-images-small`。

```bash
# 在 repo 根目錄
.venv/Scripts/python.exe scripts/prepare_catalog.py --source Marqo/KAGL --limit 5000 \
    --shuffle-buffer 256 --seed 0 --out data/catalog/kagl
.venv/Scripts/python.exe scripts/prepare_catalog.py --source Marqo/polyvore --limit 3000 \
    --out data/catalog/polyvore --full-cooccurrence \
    [--metadata-parquet data/catalog/polyvore/metadata_full.parquet]   # 重用快取，省 ~10 分鐘
```

- `--limit 0` = 全部；`--shuffle-buffer N` 會打亂 shard 順序＋buffer 抽樣（非完全隨機，但可重現）。
- 輸出：`<out>/items.parquet`、`<out>/images/*.jpg`（最長邊 384 px，透明 PNG 墊白底）、`stats.json`、`README.md`；有 outfit 的來源另輸出 `category_cooccurrence.json`（上三角，格式與 `CategoryCooccurrence.load` 相容，已實測可載入）與 `.meta.json`。
- `--full-cooccurrence`：只讀全部 parquet 的文字欄（不留影像）來算全庫共現；沒加時只用 limit 內樣本。
- schema：`item_id, title, description, category(coarse), subcategory, color, season, occasion, gender, price(float), currency, outfit_ids(list<str>), image_path, source, attr_source(JSON)`；來源沒有的值一律 null，`attr_source` 記錄 color/season/occasion/gender/price 是 `dataset` 還是 `null`。
- coarse 類別對照表寫在腳本內（`KAGL_CAT3 → KAGL_CAT2 → KAGL_CAT1` 依序比對；`POLYVORE_COARSE`，`Men's X` 視同 `X`），未列出的一律 `other`。重點規則：
  - KAGL：Topwear→top，但 Jackets/Blazers/Waistcoat/Shrug/Rain Jacket/Nehru Jackets→outerwear；Dresses/Jumpsuit→dress；Kurta Sets、Night suits、Sarees、Swimwear、Innerwear、美妝保養→other；Watches/Wallets/Belts/Eyewear/Headwear/Scarves/Socks/Ties→accessory；Jewellery、Cufflinks→jewelry。
  - Polyvore：各式 Jeans/Skirts/Pants/Shorts→bottom；Rompers/Jumpsuits/Gowns→dress；Vests/Blazers/Coats/Jackets→outerwear；Watches/Tech Accessories/Hats/Sunglasses→accessory；美妝、家居、食物、Clothing（泛稱）→other。

## 4. 實際執行結果（2026-09-17，CPU、家用網路）

| 目錄 | 筆數 | 耗時 | 磁碟 | 影像失敗 | 屬性覆蓋率 |
|---|---|---|---|---|---|
| `data/catalog/kagl` | 5,000（44,434 中抽，shuffle-buffer 256） | 串流 497 s（總計 8 分 21 秒） | 79 MB | 0 | color 100%、season 99.6%、occasion 99.9%、gender 100%、price 0% |
| `data/catalog/polyvore` | 3,000（前 3,000 筆，618 套 outfit） | 92 s（總計 1 分 37 秒；全庫文字欄先前已讀，約 10 分鐘） | 71 MB（另有事後複製進來的 3.1 MB metadata_full.parquet） | 0 | 全部 0% |

KAGL 全量未跑：原始 12.7 GB > 3 GB 門檻；預估全量約 75 分鐘、影像約 700 MB。串流中偶有 HF 連線中斷，`datasets` 自動重試成功。

### KAGL（5,000）值分佈
- **category**：top 1451、shoes 1158、accessory 755、other 729、bag 500、bottom 324、outerwear 42、jewelry 22、dress 19
- **color**：Black 1123、White 651、Blue 489、Brown 458、Grey 315、Red 274、Green 251、Purple 210、Pink 197、Navy Blue 195、Maroon 87、Yellow 82、Beige 78、Olive 54、Gold 52、Skin 49、Silver 48、Orange 47、Cream 38、Multi 36，其餘 24 種各 < 30
- **occasion**：Casual 3842、Sports 489、Formal 422、Ethnic 230、null 7、Travel 6、Smart Casual 4
- season：Summer 2373、Fall 1357、Winter 756、Spring 493、null 21
- gender：Men 2595、Women 1994、Unisex 274、Boys 109、Girls 28

### Polyvore（3,000）值分佈
- **category**：other 632、jewelry 432、top 368、shoes 364、bottom 310、accessory 309、bag 296、outerwear 176、dress 113
- **color / occasion**：全部 null（來源沒有）

## 5. Outfit 類別共現（Marqo/polyvore 全庫）

`data/catalog/polyvore/category_cooccurrence.json`：94,096 件、21,587 套 outfit（大小分佈 1:973、2:2294、3:3820、4:4658、5:4134、6:3041、7:1809、8:858）。定義：`counts[a][b]`（a≤b）＝同一套 outfit 中類別為 a、b 的單品配對數。`.meta.json` 另附「同時包含 a、b 的 outfit 數」。

| | top | bottom | dress | outerwear | shoes | bag | jewelry | accessory | other |
|---|---|---|---|---|---|---|---|---|---|
| top | 949 | 6851 | 363 | 2808 | 6949 | 5866 | 5839 | 5757 | 5698 |
| bottom | | 285 | 171 | 2617 | 5968 | 4997 | 5069 | 4870 | 5016 |
| dress | | | 185 | 1031 | 2914 | 2668 | 3600 | 1860 | 3089 |
| outerwear | | | | 143 | 3579 | 3180 | 2778 | 2583 | 2483 |
| shoes | | | | | 425 | 7329 | 7888 | 6304 | 7532 |
| bag | | | | | | 508 | 6863 | 5301 | 6245 |
| jewelry | | | | | | | 5071 | 5511 | 6425 |
| accessory | | | | | | | | 2887 | 5847 |
| other | | | | | | | | | 16368 |

以 `engine02.compat.CategoryCooccurrence` 載入後的 NPMI 合乎直覺：top–bottom +0.127、dress–jewelry +0.108、top–dress −0.236、bottom–dress −0.293、shoes–shoes −0.411。

注意：這是 Polyvore（歐美、女裝為主）的搭配習慣，套用到 KAGL（印度電商、男裝過半）時只在 coarse 層級有意義；KAGL 本身沒有 outfit，無法計算自己的共現。
