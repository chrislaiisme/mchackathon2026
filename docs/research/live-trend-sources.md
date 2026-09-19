# 即時公開趨勢訊號：哪些來源真的能用、能用來做什麼、怎麼對映到封閉詞彙

> 調查與實測日期：**2026-09-19**（除非另註）｜**本檔只新增**，另交付 `scripts/fetch_trends.py`
> 標記：**V** = 我今天親自打開一手頁面／親自打過那個端點並貼出回應碼｜**C** = 沿用先前文件已核實、今天沒有重新核｜**U** = 無法核實
> 前提文件（讀過，本檔不重覆推翻）：`docs/engine02-design.md` §3.15（趨勢進排序 28 組全變差）、§3.26（KOL 訊號否決）、§3.34（外部訊號一律走側車）、`docs/research/social-trend-signals.md`、`docs/research/social4fashion-appraisal.md`、`engine02/trends.py`
> **本輪工具限制**：本 session 的 WebSearch 配額在開工前已用盡（200/200）。所有查證是 WebFetch 直打官方頁 ＋ 直接用 curl／Python 打端點看回應碼。Reddit 的條款頁與 `redditinc.com` 從本機皆抓不到（403／網域被擋），該段一律標 U。

---

## 0. 一句話結論

**能誠實接上的即時公開來源只有三個：Wikipedia pageviews（最穩、CC0、可存檔）、Google Trends 官方 RSS（穩但是全域熱搜不是時尚熱搜）、Bluesky 公開 AppView ＋ Jetstream firehose（唯一不需登入的社群來源）。**
而且——**不論來源多乾淨，它都不該進排序**。§3.15 已經量過 28 組，全部變差；本輪沒有做任何能推翻它的新實驗，所以本檔交付的東西定位就是 **展示標籤 ＋ 後台需求面板的一欄**，`data/trends/*.json` 裡逐檔寫死 `"affects_score": false`。

---

## 1. 哪些公開來源真的能用

### 1.1 總表（合法性＝2026-09-19、無付費合約、無機構資格的狀態）

| 來源 | 給什麼 | 金鑰／帳號 | 速率限制 | 非商業學術的條款位置 | 判定 |
|---|---|---|---|---|---|
| **Wikimedia Pageviews REST** | 任一條目的**每日瀏覽數**，`agent=user` 已濾爬蟲 | **都不要** V | **匿名 10 req/min** V | 資料 CC0，可存檔可散布；UA 政策要求可聯絡的 UA V | ✅ **主力** |
| **Google Trends 官方 RSS** `/trending/rss?geo=TW` | 當日**全域**熱搜標題＋約略量級 | 不要 V | 未公布 | Google 自己發布的公開 feed | 🟡 **能用，但幾乎打不到時尚詞** |
| **Google Trends 非官方 widget 端點** | 單一關鍵字 12 個月相對搜尋興趣（0–100） | 不要，但要 cookie | **實測 429** V | 非公開 API；Google ToS 只允許以官方文件化介面自動存取 | ⚠️ **opt-in、當它會壞** |
| **Bluesky 公開 AppView（`public.api.bsky.app`）** | profile／author feed／平台熱門主題 | **都不要** V | 未公布 | ToS（2025-08-14 生效）**沒有**自動存取條款 V | ✅ **可用** |
| **Bluesky Jetstream firehose** | **全站公開貼文即時串流**（JSON） | **都不要** V | 未公布 | 同上 | ✅ **唯一免登入的社群訊號** |
| **Bluesky `app.bsky.feed.searchPosts`** | 關鍵字搜貼文 | — | — | — | ❌ **從台灣呼叫 403（CDN 邊緣擋）** V |
| **Reddit 公開 JSON（`/r/x/top.json`）** | 版上熱門貼文 | — | — | **`robots.txt` 是 `User-agent: * / Disallow: /`** V | ❌ **爬＝違規，不做** |
| **Reddit Data API（OAuth）** | 同上，官方管道 | **要 Reddit 帳號＋註冊 app（登入）** | U | U（條款頁本機抓不到） | ❌ **需登入，本腳本拒絕** |
| **Pinterest Trends API** | 地區熱門關鍵字 | 要 app | — | 開發者規範逐字禁止**儲存** API 取得的資訊 C | ⚠️ **只能即時、不能存**（已有 `trends.from_live_fetch`） |
| **Google Books Ngrams** | 書籍詞頻 | 不要 | — | 可下載 | ❌ **最新語料 2024-07，資料本身仍停在書籍年代**：不是即時訊號 V |
| **Lyst Index** | 季度品牌／單品熱度榜 | — | — | 頁面寫「請聯絡 press@lyst.com 索取」 V | ❌ **無 API、無機器可讀 feed、再散布要授權** |
| **EDITED 公開指標** | — | — | — | — | ❌ **沒有免費公開指標**；且其漂亮數字量的是定價最佳化不是預測準確度 C |
| **Instagram / TikTok / X** | 實穿照、貼文 | 都要登入＋資格審 | — | §3.26 已逐條列 C | ❌ |

### 1.2 逐條細節（今天實際打過的回應）

**Wikipedia pageviews** — `GET https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{article}/daily/{start}/{end}`。今天跑 19 個條目：**200 × 18、404 × 1**（`Loafer_(shoe)` 不存在，正確條目是 `Loafer`）。這件事本身就是教訓：**條目名要一個一個驗，猜不得**。
速率：`Wikimedia APIs/Rate limits` 寫「Requests with no identifying characteristics other than IP address」→ **10 requests per minute**；瀏覽器未登入 200/min；已登入老編輯 2000/min；該頁自註「these rate limits are new in 2026 and are subject to experimentation and change」（V）。所以爬蟲每次呼叫間隔寫死 **6.5 秒**。
UA 政策（頁面版本 **2026-03-27**）逐字：「**Scripts should use an informative User-Agent string with contact information, or they may be blocked without notice.**」（V）。爬蟲的 UA 因此帶專案名、非商業聲明、repo 與 email。
授權：Wikimedia 分析資料為 CC0 → **可以存檔、可以重現、可以放進報告**。這是所有來源裡唯一四項全過的。

**Google Trends** — 兩個端點要分清楚：
- **官方公開 RSS**：`https://trends.google.com/trending/rss?geo=TW`，帶我們自己的描述性 UA → **HTTP 200** V。今天回 10 則：`總統府／秋老虎／資料中心／游智彬／klasemen brentford vs chelsea／林憲銘／新聞／鋐寶科技／費城半導體／股災`。**沒有一則跟服飾有關**。這不是壞掉，這是這個端點的本質：它是**全域**熱搜。
- **非官方 widget 端點**（`/trends/api/explore` → `/trends/api/widgetdata/multiline`，也就是 `pytrends` 包的那個）：今天第一次有拿到 200（帶 cookie jar），**之後穩定 429**。我用三種 UA 各試一次都是 429（自家描述性 UA、`Mozilla/5.0 (compatible; …)`、純 `Mozilla/5.0`）V。**結論：這個端點不是「要偽裝成瀏覽器就能過」，是本來就會擋**；把它做成預設會讓 demo 隨機爆掉。
- **`pytrends` 2026 年的狀態**：**作者已於 2025-04-17 將 repo 封存為唯讀**（GitHub 頁面明文「This repository was archived by the owner on Apr 17, 2025. It is now read-only.」）V。README 一直寫著「This is not an official or supported API」與「Only good until Google changes their backend again」。**所以答案是：pytrends 沒有被取代，它被放棄了**，而且它包的那個端點今天對我們回 429。爬蟲因此**不依賴 pytrends**（也沒安裝），改用 `urllib` 直打，並把 429 當成資料寫進輸出檔而不是當成錯誤。

**Bluesky** — `public.api.bsky.app` 今天逐一實測（全部**不帶任何憑證**）：`_health` 200、`app.bsky.actor.getProfile` 200、`app.bsky.feed.getAuthorFeed` 200、`app.bsky.unspecced.getTrendingTopics` 200、`app.bsky.unspecced.getTrends` 200；**`app.bsky.feed.searchPosts` → 403**，回應標頭是 `Server: BunnyCDN-TW1-1121`、`CDN-RequestCountryCode: TW`，**擋在 Bluesky 自己的 CDN 邊緣**，不是沙箱 proxy（關閉沙箱重測同樣 403）V。
所以關鍵字搜尋這條路從台灣走不通，改走 **Jetstream 公開 firehose**（`wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post`）：免登入、連得上、今天 300 秒讀到 **10,063 則**公開貼文 V。**firehose 其實比 search 更好**，因為它給得出**分母**（總貼文數），能算「每百萬則貼文出現幾次」，而 search 只給你一堆命中、算不出比率。
ToS（生效日 **2025-08-14**）**沒有**任何關於自動存取／爬取／API 再利用的條款 V。這是「沒有禁止」不是「明文允許」——我們的自我約束是：**只統計詞頻，不落地任何貼文內容、作者或 DID**（爬蟲輸出檔裡確實只有計數）。

**Reddit — 明確不做。** `https://www.reddit.com/robots.txt` 今天回 200，全文只有：

```
User-agent: *
Disallow: /
```

（前面的註解把讀者導去 Public Content Policy 與 r/reddit4researchers。）**`Disallow: /` 就是全站禁止自動抓取**，所以 `r/femalefashionadvice`、`r/malefashionadvice` 的 `.json` 端點**不能爬**——實測帶描述性 UA 也是 **403** V。唯一合法管道是 OAuth Data API，那需要 Reddit 帳號＋註冊應用程式，**屬於「登入後才拿得到」，本腳本一律拒絕**（`LOGIN_REQUIRED`）。
`redditinc.com/policies/data-api-terms` 與 `support.reddithelp.com/.../Public-Content-Policy` 從本機都抓不到（網域被擋／403），**所以我無法核實其速率階層與學術條款的具體文字**，見 §5。

**Pinterest** — 立場不變且不需要新實驗：規範禁止**儲存** API 取得的資訊（C，2026-09-18 核實）。本腳本**會存檔**，所以 Pinterest 在 `LOGIN_REQUIRED` 名單裡被拒絕，並在拒絕訊息裡指回 `engine02.trends.from_live_fetch()`——那條路是請求時呼叫、物件標記 `ephemeral`、`save()` 直接丟 `PermissionError`。

**Google Books Ngrams — 不要。** 不是因為條款，是因為**它根本不是即時訊號**：最新語料版本是 **2024 年 7 月**，且語料是書籍，對「今年秋天大家在看什麼」沒有任何解析度。官方說明頁也沒有 API，只有整包下載 V。

**Lyst / EDITED — 不要。** Lyst Index 是季度 PR 產物（品牌榜＋單品榜），頁面明寫要向 `press@lyst.com` 索取資料與圖片，**無 API、無機器可讀 feed**，再散布要授權 V。EDITED 沒有免費公開指標。兩者都不是「即時訊號」，是「季度新聞稿」。

---

## 2. 這個訊號在這裡能誠實拿來做什麼

§3.15 的邊界要先講清楚，否則四個用途會被混為一談：**`eval_trends.py` 的標準答案是商品屬性 metadata，所以任何與那個標準答案正交的新項都只會扣分**。它否證的是「熱門關鍵字進 BM25 式分數項」，**不是**「所有趨勢訊號都無用」。

| 用途 | 先前證據說什麼 | 要證成它需要什麼實驗 | 本輪判定 |
|---|---|---|---|
| **(a) 展示標籤** `trends.trend_badges()` | **代價 0**：不動分數、不動排序、可加總不變式不受影響（§3.15） | **不需要排序實驗**。需要的是**人審**：抽 100 張有標籤的卡，問「這個詞出現在這件商品上，你覺得合理嗎」，報一致率。這是內容正確性不是排序效果 | ✅ **直接上**，本檔交付的資料就是餵這裡 |
| **(b) 後台需求面板** | 沒有任何反證：面板不參與排序，`panels.py` 的欄位本來就是給人看的 | **不需要 NDCG 實驗**，需要的是「這一欄有沒有讓企劃改決定」。黑客松尺度做不到，**誠實的做法是標成「觀察欄位」而不是「建議」** | ✅ **可以上，但標籤要寫「注意力，不是需求」** |
| **(c) 查詢擴展**（把趨勢詞塞進檢索句） | **最危險的一個**。它會改候選池，等於偷偷進了排序，而且不會被 `affects_score:false` 擋住 | 要跟 §3.16 概念圖同一套規格：配對排列檢定、同一組 query、報 ΔNDCG@5 與 95% CI，**而且實驗必須有可能失敗**。先驗上我預期它會像 §3.15 一樣變差，因為它加的是同一種與標準答案正交的訊號 | ❌ **本輪不做**。沒有實驗就不能開 |
| **(d) 進排序** | **28 組全變差，NDCG@5 −0.16～−0.38，p≈1e-4**（§3.15）；手動清單只比隨機字詞好一點 | 需要**另一套帶時間軸的標準答案**（§3.26 指的方向：Polyvore `date` 欄位做的時間切分），不是現在這套 metadata 標準答案。在那之前任何「這次會變好」都是猜 | ❌ **不做**，而且現場要主動講這個負結果 |

**接進 ENGINE 02 的方式**（不改 `pipeline.py`）：`data/trends/*.json` → `trends.load_trends(path)` → `trends.trend_badges(engine, resp, keywords)`。已實測可通（§4）。
**不要**用 `attach_trends()`／`arm.use_trend`——那條路就是 §3.15 量壞的那條。

另有一條既有的、**有上限且有歸因**的入口：`Engine02Request.design_weight_prior`（§3.26）。它吃的是「設計要素 → 權重」的外部先驗，卡片上分開歸因為「外部趨勢／企劃偏好（非你本人的輸入）」，且被夾在一格使用者回饋的幅度內（`KanseiTable.step_size = 0.25`）。**如果哪天主辦方要把訊號真的用進決策，正確的位置是這裡，不是 `w_trend`。** 但本輪**不自動灌**：把一個 z 分數直接當 Δβ 需要一個「Wikipedia z → Δβ」的換算係數，而**沒有任何資料能定出那個係數**（這正是 `social-trend-signals.md` §4.2 說的「單位不可辨識」）。

---

## 3. 對映問題：一個搜尋詞怎麼變成 ENGINE 02 講得出來的東西

Google Trends 回的是**一個字串的相對興趣時間序列**。我們的商品庫講的是封閉詞彙：
**101 個 taxonomy 節點**（`tops.shirts`、`outerwear.blazers`、`shoes.loafers`…）、**7 組屬性槽位**（`fit ∈ {tight, regular, loose, oversized}`、`length ∈ {mini … cropped}`、`neckline`、`sleeve_length`、`construction ∈ {knit, woven, mixed, non_textile}`、`heel_height`、`carry`）、以及 **15 個感性設計要素**（`minimal_design`、`relaxed_fit`、`glossy_fabric`…，折疊反義極後 11 條正規軸）。

### 3.1 唯一誠實的做法：一張寫死的、逐列附風險註記的對映表

`scripts/fetch_trends.py` 裡的 `VOCAB` **就是這張表**，20 列，每列四個欄位：

```python
{"term": "turtleneck", "wiki": "Polo_neck", "kind": "attr", "target": "neckline=turtle",
 "risk": "英式條目名 Polo neck，字面與 tops.polos 撞名"},
```

`kind` 只有四種目的地，對應封閉詞彙的四種東西：
- `category` → taxonomy 節點 id（`trench coat → outerwear.coats`）
- `attr` → 槽位＝值（`miniskirt → length=mini`、`crop top → length=cropped`）
- `element` → 感性設計要素（`linen → matte_fabric`、`quiet luxury → minimal_design`）
- `color` → 自由色票（**我們沒有顏色槽位**，所以這種詞落不進任何結構，只能當文字標籤）

**為什麼是寫死的表而不是模糊比對**：模糊比對會在簡報上看起來很聰明，但它把判斷藏起來了。寫死的表的好處是**它可以被吵**——企劃看得懂、可以刪一列、可以加一列，而且每一列的錯誤都指名道姓。

### 3.2 這個對映會在哪裡說謊（四種，今天的資料裡四種都出現了）

1. **同名污染。** `cardigan` 這個詞在 Wikipedia 上最大的條目是**威爾斯的一個地名（Cardigan, Ceredigion）**。我刻意把這一列留在表裡當反例——今天 Bluesky firehose 抓到 `cardigan` 2 次，**我沒有辦法知道那兩則是毛衣還是威爾斯**。`trench coat` 會被電影與軍事新聞拉高，`sneakers` 會被球鞋轉售新聞拉高，`hoodie` 會被社會新聞拉高。
2. **粒度掉下去。** `cargo pants` 對映到 `bottoms.trousers` 就沒了——**「cargo」這個設計細節在我們的封閉詞彙裡沒有槽位**。`pleated skirt` 一樣，`pleat` 無處可去。**趨勢的資訊量正好都在那個掉掉的細節裡。**
3. **投影有損。** `linen → matte_fabric` 這種「材質 → 感性軸」是我們的判斷不是資料的判斷：亞麻是霧面的，但霧面遠不只亞麻。`quiet luxury → minimal_design` 更糟，那是媒體造詞，語意逐季漂移。
4. **注意力不是需求。** 這是最根本的一條。Wikipedia 條目瀏覽、Google 搜尋、Bluesky 貼文量量的都是**注意力**；「有人查了 trench coat 的維基條目」跟「有人要買風衣」之間沒有任何已驗證的係數。**今天的資料直接示範了這件事**：`satin` z=+1.26 排第一，`linen` z=−1.10 排倒數——**我沒有任何理由相信九月的台灣市場真的在從亞麻轉向緞面**，這兩個數字更可能是某則新聞或某部戲。

### 3.3 所以對映的輸出只能是「詞」，不能是「係數」

對映表的 `target` 欄位**現在不被程式拿去改任何權重**，它的用途是兩個：
(i) 讓 `trend_badges()` 的標籤能寫成「符合近期趨勢關鍵字：緞面」而不是一串英文；
(ii) 讓後台面板能把 19 個外部詞**歸戶**到 4 個結構層（品類／屬性／要素／無處可去），並且把「無處可去」那一格**顯示出來**——那一格的大小就是「我們的封閉詞彙接不住多少當季語言」的誠實量測。

---

## 4. 爬蟲：`scripts/fetch_trends.py`

完全照 `scripts/fetch_context.py` 的結構：模組 docstring 說明為什麼是側車、`ROOT`、常數帶查證日期、`--every` 更新迴圈、網路死掉時印訊息並**保留舊檔**而不是崩潰。

- `--source google_trends | wikipedia | bluesky | all`
- 寫 `data/trends/<source>_<date>.json`，鍵 `source/as_of/catalog/notes/terms[{term,score,df}]` **就是 `TrendKeywords.from_dict` 讀的那五個**，其餘為附加 provenance（`from_dict` 會忽略不認得的鍵，已實測 round-trip）
- **拒絕登入**：`LOGIN_REQUIRED` 表（reddit / instagram / tiktok / x / twitter / pinterest / instaloader），逐條附拒絕理由
- **速率**：Wikimedia 每次呼叫 `sleep 6.5`（對應 10/min），Google Trends widget 模式 `sleep 8.0`
- **UA**：`mchackathon2026-trend-sidecar/0.1 (academic hackathon, non-commercial; +https://github.com/Evan-Jiamg; ben940815@gmail.com)`
- **HTTP 錯誤是資料不是例外**：429／403／404 全部寫進輸出檔的 `per_term` 與 `notes`
- 每個輸出檔逐檔寫 `"affects_score": false` 與一段指回 §3.15 的 `not_a_ranking_term`

### 4.1 `--dry-run`（節錄，實際輸出）

```
DRY RUN — nothing is fetched. User-Agent: mchackathon2026-trend-sidecar/0.1 (academic hackathon, non-commercial; +https://github.com/Evan-Jiamg; ben940815@gmail.com)
login/credentials used: NONE

[google_trends]  1 request(s), 8.0s apart → data/trends/google_trends*_2026-09-19.json
   GET https://trends.google.com/trending/rss?geo=TW

[wikipedia]  19 request(s), 6.5s apart → data/trends/wikipedia*_2026-09-19.json
   GET https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Trench_coat/daily/20260620/20260918
   ... (19 條，逐條列出完整 URL)

[bluesky]  2 request(s), 0.0s apart → data/trends/bluesky*_2026-09-19.json
   GET https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrends?limit=25
   GET wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post   (websocket, read-only, 60s sampling window)

refused without asking (login required):
   reddit       Reddit's robots.txt is `User-agent: * / Disallow: /`; the only sanctioned route is the OAuth Data API, which needs a Reddit account + registered app (login).
   pinterest    Pinterest developer guidelines forbid STORING API data — this script stores. Use engine02.trends.from_live_fetch() at request time instead (ephemeral).
   ...
```

### 4.2 實跑（`--source all`，2026-09-19）

```
2026-09-19T02:02:12+00:00  google_trends   0 terms  top: (本輪無交集)  -> data\trends\google_trends_rss_2026-09-19.json
2026-09-19T02:13:57+00:00  wikipedia      19 terms  top: satin、knitwear、miniskirt、trench coat、turtleneck  -> data\trends\wikipedia_pageviews_2026-09-19.json
2026-09-19T02:10:42+00:00  bluesky         2 terms  top: cardigan、jeans  -> data\trends\bluesky_public_2026-09-19.json
```

**Wikipedia**（`HTTP 統計：{200: 19}`，視窗 `2026-06-20 .. 2026-09-18`，`score` = 最近 7 日日均相對前段的 z）：

```json
[{"term":"satin","score":1.2599,"df":2457},{"term":"knitwear","score":1.0022,"df":1780},
 {"term":"miniskirt","score":0.7986,"df":2020},{"term":"trench coat","score":0.5811,"df":2379},
 {"term":"turtleneck","score":0.5178,"df":581},{"term":"quiet luxury","score":0.4031,"df":804},
 {"term":"jeans","score":0.2569,"df":3539},{"term":"corduroy","score":0.1046,"df":2456},
 {"term":"athleisure","score":-0.1419,"df":1328},{"term":"sneakers","score":-0.1449,"df":63}, ...]
```
末端：`crop top` −0.956、`linen` −1.098。**首輪 19 條裡有 1 條是 404（`Loafer_(shoe)`），已修為 `Loafer` 後重跑成 19/19 200。**

**Google Trends RSS**：`HTTP 200`，當日熱搜 10 則、落在封閉詞彙內 **0 則**。原始標題已寫進檔案的 `trending_titles`：`總統府／秋老虎／資料中心／游智彬／klasemen brentford vs chelsea／林憲銘／新聞／鋐寶科技／費城半導體／股災`。**這個 0 是誠實的 0。**

**Google Trends widget 模式**（`--gt-mode widgets --limit 3`）：

```json
{"notes":["來源：Google Trends **非官方** widget 端點（pytrends 包的那個），geo=TW",
          "HTTP 統計：{429: 3}；429 是這個端點的常態，不是本腳本的錯誤", ...],
 "terms":[],
 "per_term":[{"term":"trench coat","http_status":429},{"term":"blazer","http_status":429},{"term":"cardigan","http_status":429}]}
```

**Bluesky**：`getTrends` 200（平台當下熱門主題全是政治／體育／娛樂，**沒有一則時尚**），firehose 300 秒讀到 **10,063 則**公開貼文，命中 `cardigan` 2 次、`jeans` 2 次（各約 199 次/百萬則）。
**這個 2 就是本輪最有用的數字**：它量出了「在一般社群串流裡，服飾詞彙的基準率大約是百萬分之二百」。要讓這個訊號有統計意義，**需要連續跑數天累積分母**，單輪的 log10 分數沒有基準線、不能解讀——檔案的 `notes` 裡逐字寫了這句。

### 4.3 與 `engine02/trends.py` 的接合（已實測）

```
>>> from engine02.trends import load_trends
>>> tk = load_trends('data/trends/wikipedia_pageviews_2026-09-19.json')
source= live:wikipedia_pageviews  as_of= 2026-09-19  n= 19
keywords(8)= ['satin','knitwear','miniskirt','trench coat','turtleneck','quiet luxury','jeans','corduroy']
round-trip keys ok: True
```

接下來只要 `trend_badges(engine, resp, tk.keywords(30))` 就有標籤，**不碰 `attach_trends()`、不碰 `arm.w_trend`**。

---

## 5. 我無法核實的部分

1. **Reddit Data API 的免費層速率與學術條款的確切文字。** `redditinc.com/policies/data-api-terms` 從本機無法抓取（網域被擋），`support.reddithelp.com` 的 Public Content Policy 回 403。我核實到的只有 `robots.txt` 全文（`Disallow: /`）與 `r/*/top.json` 的 403。**「Reddit 免費層是 100 QPM / OAuth client」這類數字我今天沒有一手來源，故不寫進表格。**
2. **官方 Google Trends API（alpha）的取用方式與配額。** 我只核實到 `developers.google.com/search/blog/2025/07/trends-api` 這篇公告**存在、日期是 2025 年 7 月**；頁面正文在 WebFetch 下被截斷，**候補名單、端點、時間範圍、配額我都拿不到**。所以爬蟲沒有實作它，只在註記裡寫「官方 API 仍在 alpha」。
3. **Pinterest 開發者規範的逐字條文**今天沒有重新核（頁面回傳無正文）。沿用 `social-trend-signals.md` 2026-09-18 的核實結果（標 C）。
4. **Bluesky 公開 AppView 與 Jetstream 的官方速率限制**：`docs.bsky.app` 已 301 到 `bsky.network`，該頁在 WebFetch 下回空內容。**沒有公布數字**，爬蟲因此採單次連線＋固定取樣視窗的保守做法，而不是猜一個 QPS。
5. **`searchPosts` 的 403 是政策還是地區封鎖**，我只知道它擋在 `BunnyCDN-TW1` 邊緣、`CDN-RequestCountryCode: TW`。**我沒有第二個地區可以對照**，所以不能斷言它對所有人都 403。
6. **所有分數的外部效度。** `satin` z=+1.26、`linen` z=−1.10 是真實計算，但**沒有任何實驗證明這兩個數字與台灣成衣需求有關**。本檔不宣稱它們有。
