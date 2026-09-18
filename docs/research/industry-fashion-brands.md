# 產業調查：時尚品牌與平台實際部署／發表了什麼（對照 ENGINE 02）

> 調查日期：2026-09-16｜範圍：聚陽客戶驗證、時尚品牌／平台在檢索、推薦、搭配、對話式導購、可解釋性、屬性標註、需求回饋設計等方面的一手資料
> 標記：**V** = 已實際開啟頁面（或 PDF）核對；**U** = 僅看到搜尋摘要、未能開頁（403、付費牆、逾時等），引用時請保守
> 注意：本輪 WebSearch 配額在後段用完，部分品牌（JD、Nike、H&M 官方頁、Inditex 官方頁）無法再追一手來源，已在文中標明。

---

## (a) 聚陽（Makalot）客戶驗證

| 項目 | 內容 | 來源 | 日期 | V/U |
|---|---|---|---|---|
| 客戶營收占比（2025） | **Gap Inc. 36%、TARGET 18%、Japan Customer 18%、Dick's 9%、Kohl's 7%、Others 12%** | [Makalot Industrial Co., Ltd. 2026 法說簡報 p.8 "2025 Operating Highlight"](https://cdn.financialreports.eu/financialreports/media/filings/51834/2026/RNS/51834_rns_2026-04-10_4bb81ebd-1c93-46fb-95a3-41d97b5c90f7.pdf) | 2026-04-10 | V（已讀 PDF 圖表） |
| 客戶分類 | 同簡報 p.5：Brands = **Gap Inc.、Fast Retailing**；Mass Channels = **Target、Dick's Sporting Goods**；Department Stores = **Kohl's**。p.8 的 "Japan Customer" 對應 p.5 的 Fast Retailing logo（推論，簡報未明寫兩者等同） | 同上 p.5 | 2026-04-10 | V |
| 產品／地區結構 | Functional Sportswear 52% / Fashion Apparel 48%；USA 73%、Asia 25%、Europe 2% | 同上 p.8 | 2026-04-10 | V |
| 媒體交叉印證 | 五大客戶 Gap、Target、Fast Retailing、Dick's、Kohl's 合計約 70%，Gap 約 30% | [鉅亨網](https://news.cnyes.com/news/id/6299329) | 2026-01-06 | V |
| 較早歷史 | FY22：GAP 29%、Target 20%、迅銷 18%、Dick's 6%、Kohl's 6%（二手整理） | 搜尋摘要（vocus／cmoney） | — | U |

**結論**：聚陽 2025 年前五大客戶為 **Gap Inc.（Old Navy / Gap / Banana Republic / Athleta）、Target、Fast Retailing（UNIQLO / GU）、Dick's Sporting Goods、Kohl's**，合計 88%。先前假設中的 Lululemon、Walmart **不在**官方揭露的主要客戶名單（簡報僅以 "Others 12%" 概括，不能斷言有或沒有）。

### 聚陽客戶自己公開的 AI 動作

| 客戶 | 公開做了什麼 | 與 ENGINE 02 相關 | 來源 | 日期 | V/U |
|---|---|---|---|---|---|
| Gap Inc. | 與 Google Cloud 多年合作（Gemini、Vertex AI、BigQuery）；目標含「hyper-personalized shopping、smarter recommendations」，以及用 AI「accelerate design, planning, and pricing processes」 | 個人化推薦；AI 進入設計／企劃流程 | [Gap Inc. 官方新聞稿](https://www.gapinc.com/en-us/articles/2025/10/gap-inc-sets-out-to-reimagine-retail-powered-by-go) | 2025-10-09 | V |
| Target | Photo Search（上傳照片找相似商品，2026-08）；**Review Insights：自動找出評論常討論的商品屬性（如 comfort、fit）並分主題**，官方稱早期結果提升轉換與加入購物車 | 屬性抽取自評論；視覺檢索 | [Target 官方文章](https://corporate.target.com/news-features/article/2026/09/digital-tools) | 2026-09 | V |
| Target | 對話式 Target Gift Finder；ChatGPT 內的對話式、策展式購物 app | 對話式導購 | [節慶 AI 新聞稿](https://corporate.target.com/press/release/2025/11/target-launches-new-ai-powered-features-to-make-holiday-shopping-easier,-smarter-and-more-fun)、[ChatGPT 新聞稿](https://corporate.target.com/press/release/2025/11/target-to-launch-first-of-its-kind-conversational,-curated-shopping-experience-in-chatgpt) | 2025-11 | V |
| Target | AI 偵測 TikTok 上 "mob wife" 豹紋趨勢後與供應商快速放大豹紋商品 | 趨勢→採購／供應商 | Retail Dive 搜尋摘要 | 2024 | U |
| Fast Retailing / UNIQLO | 官方：「每年收到超過 3,900 萬則顧客回饋」，**用 AI「significantly increase the accuracy and speed of customer feedback analysis and dissemination」**，回饋給商品部與門市；R&D 結合顧客意見與趨勢、新材料 | **顧客需求→設計／商品開發（最貼近 OEM）** | [FR: UNIQLO Business Model](https://www.fastretailing.com/eng/group/strategy/uniqlobusiness.html) | 未標日期 | V |
| Fast Retailing | FY2024 UNIQLO 在 26 國收集近 110 萬則顧客意見，「每週把商品相關回饋分享給相關部門，用於商品開發」；改善案例公布於 UNIQLO UPDATE | 需求回饋閉環 | [FR: Pursuing Customer Satisfaction](https://www.fastretailing.com/eng/sustainability/products/customers.html) | 2025-01-15 更新 | V |
| Fast Retailing | Ariake 專案（與 Google Cloud ASL）：「從 make it and they will come 轉向把顧客回饋變成真實商品」、需求預測 | 需求→商品 | [FashionNetwork](https://us.fashionnetwork.com/news/Fast-retailing-teams-up-with-google-to-power-ariake-project,1015620.html) | 2018-09-19 | V |
| UNIQLO | UNIQLO IQ 虛擬購物助理（Dialogflow） | 對話式助理 | [UNIQLO IQ 頁](https://www.uniqlo.com/us/en/special-feature/iq)（開頁逾時） | 2018~ | U |
| UNIQLO（澳洲） | UMood：戴腦波頭戴裝置看影像，量測喜好、壓力、興趣、專注、睏倦五項反應，從 600 款 T 恤推薦 4 款（Dentsu ScienceJam 技術） | **情緒→商品的 affective mapping（行銷活動，非常態系統）** | [Refinery29](https://www.refinery29.com/en-us/2015/10/95533/uniqlo-umood-machine) | 2015-10-12 | V |
| Dick's Sporting Goods | "Coach by Dick's" agentic AI 顧問，依目標、行為、偏好推薦商品與訓練建議（Adobe Brand Concierge） | 對話式導購 | [Retail Dive](https://www.retaildive.com/news/dicks-sporting-goods-coach-ai-shopping-adviser/821356/) | 2026-06 | V |
| Kohl's | AI 購物助理（Gemini Enterprise for CX）：個人化推薦、商品比較、以圖搜商品；前身為 Gift Finder | 對話式導購；以圖搜 | [Retail Dive](https://www.retaildive.com/news/kohls-ai-shopping-assistant/826585/) | 2026-07-30 | V |

---

## (b) 各技術別的產業證據表

### b1. 稠密／多模態嵌入（dense / multimodal embeddings，含 fashion CLIP）

| 公司 | 做了什麼 | 來源 | 發表處／日期 | 規模／結果 | V/U |
|---|---|---|---|---|---|
| Farfetch（+Coveo 等） | **FashionCLIP**：以 Farfetch 超過 70 萬組圖文對微調 CLIP；評估檢索、zero-shot 分類、定位、組合概念 | [Scientific Reports / PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9643437/) | Scientific Reports, 2022-11-08 | 論文稱領域微調在域內有效且可泛化到未見資料集；**論文未聲明 Farfetch 線上部署** | V |
| Musinsa（AWS 技術部落格） | YOLOS-Fashionpedia 偵測 → **FashionCLIP 2.0** 圖文嵌入 → Amazon OpenSearch 向量檢索；Bedrock Nova Lite 做 **query rewriting** | [AWS Korea Tech Blog](https://aws.amazon.com/ko/blogs/tech/musinsa-ai-base-product-recommendation/) | 2025-07-08 | 5,032 張商品圖測試：P@1 72%、P@5 81%、MRR 0.76；自承素色基本款、遮擋、角度難（向量相似度不足以捕捉風格脈絡）。看起來是 PoC 性質的測試 | V |
| Pinterest | **OmniSearchSage**：查詢、Pin、商品共用嵌入；以 LLM 生成的圖片描述、互動、看板資訊強化 | [arXiv 2404.16260](https://arxiv.org/abs/2404.16260) | WWW 2024 Companion | 正式搜尋系統：relevance >8%、engagement >7%、ads CTR >5%；300k QPS | V |
| Pinterest | **PinCLIP**：VLM 圖文對齊 + Pin-Board 圖鄰居對齊 | [arXiv 2603.03544](https://arxiv.org/abs/2603.03544) | 2026-03 | 多模態檢索離線比 Qwen 基線高 20%；線上新內容 Repin +15%、新廣告點擊 +8.7% | V |
| Zalando Research | **Fashion DNA**：以標籤、價格、圖片學到 "fashion space" 向量，「article properties … are associated with specific directions in this space」；可解 cold-start | [Zalando Research](https://research.zalando.com/project/fashion_dna/fashion_dna/) | 頁面 ©2021 | 用途：標註、趨勢偵測、競品分析、street-to-shop、推薦 | V |
| Stitch Fix | **Latent Style**：矩陣分解得到使用者／商品嵌入，再做 PCA；第一主成分被解讀為 **boho ↔ preppy** 風格軸 | [Multithreaded blog](https://multithreaded.stitchfix.com/blog/2018/06/28/latent-style/) | 2018-06-28 | 用於庫存規劃、「product design guidance」、去重、cold-start | V |
| Alibaba iFashion | POG 以圖像、文字、CF 的多模態商品嵌入為第一步 | [arXiv 1905.01866](https://arxiv.org/abs/1905.01866)（PDF 結論節） | KDD 2019 | 見 b4 | V |

### b2. 混合檢索（BM25 + dense + RRF）

| 公司 | 做了什麼 | 來源 | 發表處／日期 | 規模／結果 | V/U |
|---|---|---|---|---|---|
| Shopify | Semantic Search：「goes beyond keyword matching to better understand the intent」（Plus 商家） | [Shopify Editions Winter '24](https://www.shopify.com/editions/winter2024) | 2024-01 | 無數字 | V |
| Google Shopping（AI Mode） | **query fan-out**：一個需求同時發出多個子查詢（例如「雨天、長途」要怎樣的包）；Shopping Graph 超過 500 億筆商品、每小時更新 20 億筆 | [Google Blog I/O 2025](https://blog.google/products/shopping/google-shopping-ai-mode-virtual-try-on-update/) | 2025-05-20 | 規模如左 | V |
| Revolve | 「improved its proprietary search algorithm」＋個人化，官方稱帶來「several million dollars in annualized revenue gains」 | [Digital Commerce 360](https://www.digitalcommerce360.com/2026/02/27/revolve-group-net-sales-ai-q4-2025/) | 2026-02-27 | 如左 | V |
| Nordstrom | App 改版含「improved search」 | [Marketing Dive](https://www.marketingdive.com/news/nordstrom-generative-ai-holiday-app-refresh/732811/) | 2024-11-14 | 無細節 | V |

> **誠實註記**：本次調查**沒有找到任何時尚品牌公開寫明「BM25 + dense + RRF」**的一手資料。業界公開說法多停在「semantic search」「向量檢索」「query rewriting / fan-out」。混合檢索是通用 IR 做法，不是時尚業特有的公開案例。

### b3. 屬性抽取／標註（attribute extraction / tagging）

| 公司 | 做了什麼 | 來源 | 發表處／日期 | 規模／結果 | V/U |
|---|---|---|---|---|---|
| Amazon | **OpenTag**：BiLSTM-CRF + attention 從商品文字抽屬性值；attention 提供可解釋性；主動學習 | [Amazon Science](https://www.amazon.science/publications/opentag-open-attribute-extraction-from-product-profiles) | KDD 2018 | 150 筆標註即達 F1 83%，標註量少 3.3 倍 | V |
| Myntra | **Progressive Fashion Attribute Extraction**：同一件服飾的屬性間漸進微調，處理缺標與模糊標籤 | [arXiv 1907.00157](https://arxiv.org/abs/1907.00157) | KDD 2019 AI for Fashion Workshop | 相對多標籤分類有提升 | V |
| ZOZO 研究所 + 早稻田 | **Fashion Intelligence System**：全身穿搭照與多個抽象標籤（如 casual、formal）映射到同一空間；**Attribute Activation Map** 顯示哪些影像區域對應哪個印象標籤 | [ZOZO NEXT 新聞稿](https://zozonext.com/news/20221122_zozoresearch) | Expert Systems with Applications, 2022-11 | 研究階段；自承需要乾淨照片與專業標註，**未宣布上線** | V |
| Target | Review Insights：從評論抽出常討論的屬性並分主題 | [Target](https://corporate.target.com/news-features/article/2026/09/digital-tools) | 2026-06 上線 | 轉換與加入購物車提升（無具體 %） | V |
| Amazon | StyleSnap：辨識服裝類別（如 fit-and-flare dress、flannel shirt），**排序時也考慮品牌、價格帶、評論** | [About Amazon](https://www.aboutamazon.com/news/retail/stylesnap-will-change-the-way-you-shop-forever) | re:MARS 2019 | — | V |
| ASOS | Style Match 以圖搜（2018-03 全球上線） | 搜尋摘要（aitrace.org） | 2018 | — | U |

### b4. 搭配相容性／Complete-the-look

| 公司 | 做了什麼 | 來源 | 發表處／日期 | 規模／結果 | V/U |
|---|---|---|---|---|---|
| Alibaba iFashion | **POG**：Transformer 結合個人偏好與搭配相容性，生成個人化整套搭配；部署在 Dida 平台 | [arXiv 1905.01866](https://arxiv.org/abs/1905.01866) | KDD 2019 | 公開 101 萬套搭配、2.8 億點擊、357 萬使用者；線上 7 天實驗 **CTR 比 Bi-LSTM+CF 高 70% 以上**（PDF §5.2.3） | V |
| Pinterest | **Complete the Look**：由場景圖（含體型、季節等脈絡）推薦相容商品，全域＋局部 attention | [arXiv 1812.01748](https://arxiv.org/abs/1812.01748) | CVPR 2019 | — | V |
| Pinterest | **Shop The Look**：物件偵測＋視覺嵌入檢索 | [arXiv 2006.10866](https://arxiv.org/abs/2006.10866) | KDD 2020 | 人工相關性累計 +160%、互動 +80%；已上線 | V |
| Amazon | **Fashion Outfit Complementary Item Retrieval**：依類別的 subspace attention ＋ outfit ranking loss | [Amazon Science](https://www.amazon.science/publications/fashion-outfit-complementary-item-retrieval)、[arXiv](https://arxiv.org/abs/1912.08967) | CVPR 2020 | 相容性與互補檢索優於 SOTA | V（Amazon 歸屬由 amazon.science 收錄確認） |
| Zalando | **AFRA**：可重用的 self-attention 推薦器，服務 "Get the Look"、依風格（classic / casual / streetwear）的 outfit carousel、相似品、session 內推薦 | [arXiv 2211.16366](https://arxiv.org/abs/2211.16366)（PDF 標示 Zalando SE） | fashionXrecsys'22 | 線上實驗「substantial improvements in customer retention and engagement」 | V |
| Zalando | Outfit generation 演算法比較（GPT、BERT、Seq2Seq 等），使用真實線上資料 | [arXiv 2211.16353](https://arxiv.org/abs/2211.16353)（Zalando SE） | fashionXrecsys'20 | — | V |
| ZOZO | **SHIFT15M**：IQON 約 1,500 萬件商品的 set-to-set（搭配）匹配資料集，含分布漂移 | [arXiv 2108.12992](https://arxiv.org/abs/2108.12992) | 2021 | 資料集 | V |
| Levi's | **Outfitting**：用庫存、彙總購買歷史、瀏覽行為、商品圖推薦整套穿搭，並隨使用者選擇改善；2025-11 上線 | [Digital Commerce 360](https://www.digitalcommerce360.com/2026/02/05/ecommerce-trends-how-levi-strauss-is-using-ai/) | 2026-02-05 | — | V |
| ASOS | "Styled for You"：以 10 萬套以上專業策展棚拍穿搭訓練，針對單品推薦整套（試行） | 搜尋摘要（LBC／Insider Media） | 2025-11 | — | U |

### b5. 對話式／LLM 購物助理

| 公司 | 做了什麼 | 來源 | 發表處／日期 | 規模／結果 | V/U |
|---|---|---|---|---|---|
| Zalando | ChatGPT 驅動的 fashion assistant beta，可用自己的話問「七月去 Santorini 參加婚禮穿什麼」 | [Zalando Corporate](https://corporate.zalando.com/en/technology/zalando-launch-fashion-assistant-powered-chatgpt) | 2023-04 公告 | — | U（僅摘要） |
| Zalando | **共創觀察**：VP Tian Su：「Many of them **describe the feeling they want to have when wearing the item**」；提供 thumbs up/down 與「要別的」的對話修正 | [Zalando Corporate](https://corporate.zalando.com/en/technology/how-zalando-co-creating-its-new-ai-powered-assistant-together-customers) | 約 2023-11 後 | beta（DE/AT/UK/IE） | V |
| Zalando | 全 25 市場上線；理解地點、天氣、場合；Trend Spotter 附「趨勢成因說明」 | [Zalando Corporate](https://corporate.zalando.com/en/technology/zalando-brings-its-ai-powered-assistant-all-markets-and-adds-four-new-cities-its-trend) | 2024-10-01 | — | V |
| Zalando | 連結帳戶歷史後更個人化；依瀏覽位置給脈絡建議（如看丹寧時提示「Show me flared jeans」） | [Zalando Corporate](https://corporate.zalando.com/en/technology/more-personal-and-smarter-zalando-assistant-enhanced-capabilities-inspire-customers) | 2025-03-27 | 使用者超過 200 萬；測試中 **high-value interactions +40%** | V |
| Myntra | MyFashionGPT（Azure OpenAI）：把開放式需求（海灘度假）展開成跨品類結果 | [Microsoft Source Asia](https://news.microsoft.com/source/asia/features/indias-myntra-innovates-with-generative-ai-to-help-shoppers-put-the-right-look-together/) | 2023 | 使用者 **購買機率 3 倍**、加購品類多約 16% | V |
| Myntra | **Maya**：會「asking follow-up questions to help streamline the query」，同一 session 保留脈絡；230 萬款商品 | [Myntra 新聞稿 PDF](https://blog.myntra.com/wp-content/uploads/2023/10/Maya_Search_Assistant_PR.pdf) | 2023-09-25 | 先開放 10% 使用者 | V |
| Ralph Lauren | **Ask Ralph**（Azure OpenAI）：回傳整套穿搭的 visual laydown，可追問精修（如「怎麼搭我的海軍藍西裝外套」） | [Ralph Lauren 新聞稿](https://corporate.ralphlauren.com/pr_250909_AskRalph.html) | 2025-09-09 | 美國 app | V |
| Amazon | Rufus（2026-05-13 更名 Alexa for Shopping）：RAG，引用 Vogue 等來源 | [About Amazon](https://www.aboutamazon.com/news/retail/amazon-rufus-ai-assistant-personalized-shopping-features) | 2025–26 | 今年超過 2.5 億顧客使用；使用者 **購買可能性高 60% 以上** | V |
| Stitch Fix | AI Style Assistant（對話＋AI 生成穿搭靈感，beta） | [Stitch Fix Newsroom](https://newsroom.stitchfix.com/blog/stitch-fix-announces-latest-generative-ai-and-styling-enhancements/) | 2025-08-11 | — | V |
| Farfetch | **iFetch**：多模態任務導向對話代理（與 CMU、IST 等合作） | 搜尋摘要（MuCAI@ACM MM 2021） | 2021 | 研究計畫 | U |
| Taobao | 淘寶問問、AI 萬能搜（解析模糊情境需求）、AI 幫我挑、AI 試穿 | 搜尋摘要（CSDN／53ai） | 2023–25 | — | U |
| Target / Kohl's / Dick's | 見 (a) 表 | — | — | — | V |

### b6. 推薦的解釋（explanation）

| 公司 | 做了什麼 | 來源 | 發表處／日期 | 規模／結果 | V/U |
|---|---|---|---|---|---|
| Amazon | **Help Me Decide**：看過多件相似商品後出現，依搜尋、瀏覽、購買紀錄推薦並**說明為什麼適合你**；可切換較便宜／較高階替代品 | [TechCrunch](https://techcrunch.com/2025/10/23/amazons-new-ai-shopping-tool-tells-you-why-you-should-buy-a-recommended-product/) | 2025-10-23 | 美國；非時尚專屬 | V |
| eBay | **LLM-PKG**：LLM 產生帶 5 字 rationale 的商品知識圖，修剪後映射到真實商品；卡片副標題顯示理由（如 "Same Brand"） | [arXiv 2412.01837](https://arxiv.org/abs/2412.01837)（PDF 已讀） | IJCAI 2024 OpenKG Workshop | **球鞋品類**線上 A/B；數字（點擊 +5.19%、交易 +7.59%）僅見於搜尋摘要 → U。**注意：實驗組同時換了召回來源與理由文字，無法單獨歸因給「解釋」** | V（論文）/ U（數字） |
| ZOZO 研究所 | Attribute Activation Map：標出影像中對應印象標籤的區域 | [ZOZO NEXT](https://zozonext.com/news/20221122_zozoresearch) | 2022-11 | 研究 | V |
| Pinterest | Complete the Look 的 attention 可指出影像中重要區域 | [arXiv 1812.01748](https://arxiv.org/abs/1812.01748) | CVPR 2019 | — | V |
| Zalando | Trend Spotter 顯示「是什麼帶動這個趨勢」、屬於全球還是在地趨勢 | [Zalando Corporate](https://corporate.zalando.com/en/technology/zalando-brings-its-ai-powered-assistant-all-markets-and-adds-four-new-cities-its-trend) | 2024-10 | — | V |
| Stitch Fix | Style Space：每位客戶可看到依自己評分畫出的 3D 風格地圖 | Stitch Fix Newsroom 搜尋摘要 | — | — | U |

> **誠實註記**：沒有找到任何時尚品牌公開「**加法式分數分解作為解釋**」或「**反事實檢查解釋是否成立**」的部署案例。業界的解釋多是 LLM 自然語言 rationale（Amazon、eBay）或 attention／熱力圖（研究）。

### b7. 評論式修正（critiquing，例如「再休閒一點」）

| 公司 | 做了什麼 | 來源 | 發表處／日期 | 規模／結果 | V/U |
|---|---|---|---|---|---|
| Amazon（Amazon Fashion 標籤） | **FashionVLP**：參考圖 + 自然語言回饋（Fashion IQ relative captions）做檢索 | [Amazon Science](https://www.amazon.science/publications/fashionvlp-vision-language-transformer-for-fashion-retrieval-with-feedback) | CVPR 2022 | FashionIQ 相對提升 23% | V |
| Zalando | 助理允許「corrections requesting alternatives」＋ thumbs up/down | [Zalando Corporate](https://corporate.zalando.com/en/technology/how-zalando-co-creating-its-new-ai-powered-assistant-together-customers) | 2023–24 | — | V |
| Ralph Lauren / Myntra Maya | 追問與精修（見 b5） | 見 b5 | 2023–25 | — | V |
| Google AI Mode | 使用者補充條件（天氣、長途）→ fan-out 重搜 | [Google Blog](https://blog.google/products/shopping/google-shopping-ai-mode-virtual-try-on-update/) | 2025-05 | — | V |
| Amazon Help Me Decide | 較便宜／較高階替代品切換（價格維度的 critique） | [TechCrunch](https://techcrunch.com/2025/10/23/amazons-new-ai-shopping-tool-tells-you-why-you-should-buy-a-recommended-product/) | 2025-10 | — | V |

### b8. 生成圖像用於搜尋／探索

| 公司 | 做了什麼 | 來源 | 發表處／日期 | 規模／結果 | V/U |
|---|---|---|---|---|---|
| Google Shopping | **Vision Match**：描述想像中的衣服 →「uses AI image generation to show you a few ideas」→ 配對可購商品 | [Google Blog](https://blog.google/products/shopping/ai-vision-match-ar-beauty-virtual-try-on/)、[Practical Ecommerce](https://www.practicalecommerce.com/origins-of-google-shoppings-ai-vision-match) | 2025-03-05 | 美國行動版 | V |
| Google Shopping | 虛擬試穿：上傳全身照、用時尚專用圖像生成模型試穿「billions of apparel listings」 | [Google Blog](https://blog.google/products/shopping/google-shopping-ai-mode-virtual-try-on-update/) | 2025-05-20 | — | V |
| Stitch Fix | **Vision**：以客戶自拍生成穿搭情境照，可直接購買，每週更新 | [Stitch Fix IR](https://investors.stitchfix.com/news-events/press-releases/news-details/2025/Stitch-Fix-Introduces-Stitch-Fix-Vision-a-GenAI-Powered-Style-Visualization-Experience-10-06-2025/default.aspx) | 2025-10-06 | beta | V |
| Pinterest | OmniSearchSage 用 LLM 生成圖片描述強化檢索（生成**文字**而非圖） | [arXiv 2404.16260](https://arxiv.org/abs/2404.16260) | WWW 2024 | 見 b1 | V |

### b9. 消費者需求訊號回饋到設計／商品企劃（對 OEM 最關鍵）

| 公司 | 做了什麼 | 來源 | 發表處／日期 | 規模／結果 | V/U |
|---|---|---|---|---|---|
| **Fast Retailing（聚陽客戶）** | 每年 3,900 萬則回饋，用 AI 分析、傳遞給商品部；每週把商品回饋分享給相關部門做商品開發 | [FR Business Model](https://www.fastretailing.com/eng/group/strategy/uniqlobusiness.html)、[FR Customers](https://www.fastretailing.com/eng/sustainability/products/customers.html) | 2025 | 3,900 萬則／年 | V |
| **Gap Inc.（聚陽最大客戶）** | AI 用於「accelerate design, planning, and pricing」 | [Gap Inc.](https://www.gapinc.com/en-us/articles/2025/10/gap-inc-sets-out-to-reimagine-retail-powered-by-go) | 2025-10 | — | V |
| Stitch Fix | **Hybrid Designs / New Style Development**：把服裝當成屬性組（"genes"），以客戶回饋當 fitness，重組並小幅突變屬性，優先「high probability of love」的屬性組合，**再由設計師審核修正** | [Algorithms Tour](https://algorithms-tour.stitchfix.com/) | 未標日期 | — | V |
| Stitch Fix | Latent Style 用於庫存規劃與「product design guidance」；Style Shuffle 從 2018-03 累計 100 億次互動、每天 450 萬次 | [Latent Style](https://multithreaded.stitchfix.com/blog/2018/06/28/latent-style/)、[Newsroom](https://newsroom.stitchfix.com/blog/10-billion-interactions-and-counting-on-style-shuffle-the-data-powering-your-personalized-shopping-experience/) | 2018 / 2022-08-03 | 玩 Style Shuffle 的客戶對 Fix 滿意度較高 | V |
| Stitch Fix | 生成式 AI 納入自有品牌設計流程 | [Newsroom](https://newsroom.stitchfix.com/blog/stitch-fix-announces-latest-generative-ai-and-styling-enhancements/) | 2025-08-11 | — | V |
| Walmart | **Trend-to-Product**：AI 從網路與網紅彙整趨勢，生成 mood board，並產出指導供應商生產的技術包（tech pack）；設計師精修 | [Talk Business & Politics](https://talkbusiness.net/2025/05/walmart-uses-artificial-intelligence-to-fast-track-apparel-offerings/) | 2025-05-09 | 前置期約 6 個月 → 6–8 週（少 18 週） | V |
| Amazon | **Product Opportunity Explorer**：找出「lower conversion rates than the benchmark」的搜尋詞群，也就是**需求高但供給不足**；評論主題「highlighting areas of unmet need」 | [Sell on Amazon](https://sell.amazon.com/tools/product-opportunity-explorer) | 持續更新 | 官方稱用其洞察推出的新品前三個月銷售潛力 2.5 倍 | V |
| Zalando | Trend Spotter：以自有資料追蹤 10 個歐洲城市每週新興趨勢 | [Zalando Corporate](https://corporate.zalando.com/en/technology/zalando-brings-its-ai-powered-assistant-all-markets-and-adds-four-new-cities-its-trend) | 2024-10 | 新聞稿未提是否提供給品牌夥伴 | V |
| SHEIN | 按需模式：每款先做 100–200 件小批量，依即時需求決定追單；未售庫存個位數 % | 搜尋摘要（sheingroup PDF 404／Process 頁無數字） | 2022–23 | 無法開頁核對 | U |
| Inditex / Zara | 與 Jetlore 合作預測顧客行為（尺寸、顏色、版型、風格偏好）；門市觀察回饋設計團隊 | [Retail Dive](https://www.retaildive.com/news/zara-betting-on-ai-big-data-to-outflank-competitors/525920/) | 2018-06-18 | 二手報導，非 Inditex 官方 | V（二手） |
| Lululemon | 設立 Chief AI & Technology Officer，AI 用於加速產品創新與上市 | [PYMNTS](https://www.pymnts.com/news/retail/2025/lululemon-embraces-ai-to-accelerate-design-and-go-to-market-processes/) | 2025-09-04 | 新款占比目標 23% → 35% | V |
| H&M Group | Kaggle "H&M Personalized Fashion Recommendations"（交易、顧客、商品 metadata、圖文） | Kaggle 頁面無法渲染 | 2022 | 約 3,000 隊 | U |

### b10. Kansei／情感屬性（affective）對應：專門檢查

| 證據 | 性質 | 來源 | 日期 | V/U |
|---|---|---|---|---|
| ZOZO 研究所 Fashion Intelligence System：把「casual」「formal」等**模糊印象語**與穿搭影像放進同一嵌入空間，並以 AAM 顯示對應區域 | **最接近 Kansei 的資料驅動版本**；時尚公司研究，未宣布上線 | [ZOZO NEXT](https://zozonext.com/news/20221122_zozoresearch) | 2022-11 | V |
| ZOZO NEXT × 東大曆本研究室 × Cluster：把衣服**觸感／穿著舒適度量化**，目標讓 EC 能「以喜好的舒適度搜尋」 | 感性（觸覺）量化→檢索；研究中 | [東大情報學環](https://www.iii.u-tokyo.ac.jp/news/2025020721997) | 2025-02-07 | V |
| UNIQLO UMood：腦波反應（喜好／壓力／興趣／專注／睏倦）→ T 恤推薦 | 聚陽客戶的情緒→商品對應，但屬店內行銷活動 | [Refinery29](https://www.refinery29.com/en-us/2015/10/95533/uniqlo-umood-machine) | 2015-10 | V |
| Zalando 助理：顧客常「describe the feeling they want to have when wearing the item」 | 證明**需求端**真的用情感語言表達；未公開其內部如何對應到屬性 | [Zalando Corporate](https://corporate.zalando.com/en/technology/how-zalando-co-creating-its-new-ai-powered-assistant-together-customers) | 2023–24 | V |
| Stitch Fix Latent Style 的 boho↔preppy 軸、Zalando AFRA 的 classic/casual/streetwear 風格 | 風格軸（style），不是情緒需求（如「看起來可靠」） | 見 b1/b4 | 2018 / 2022 | V |
| SENSY（原 Colorful Board）「感性 AI」與服飾企業合作個人化 DM，來店率 +58.7% | 日本新創，非品牌自研；原始頁 403／付費牆 | 搜尋摘要（TechCrunch Japan 2017） | 2017 | U |
| 學術 Kansei 服裝研究（西裝設計的 SD 法＋設計要素；永續丹寧 Gen Z SEM） | **學術論文，非企業部署** | ResearchGate 403；Frontiers 僅摘要 | 2021 / 2026 | U |

**結論（Kansei）**：本次**沒有找到任何服飾品牌公開說明以正式 Kansei engineering（SD 法問卷 → 設計要素權重表）用於量產商品企劃或線上檢索**的一手資料。最接近的是 ZOZO（印象語↔影像嵌入、觸感量化）與 UNIQLO UMood（一次性行銷）。我們的「needs→design-element 權重表」在業界是**少見但有學術根據**的做法，應定位為「把 Kansei 學術方法產品化」，不要宣稱是「業界標準」。

**結論（demand gap）**：「搜尋了但買不到」的需求缺口分析，最明確的一手案例是 **Amazon Product Opportunity Explorer**（低轉換搜尋詞群＝未滿足需求）；「顧客回饋 → 設計」最明確的是 **Fast Retailing**（聚陽客戶）與 **Stitch Fix Hybrid Designs**；「趨勢 → tech pack 給供應商」是 **Walmart Trend-to-Product**。

---

## (c) 對 ENGINE 02 的啟示

### c1. 各元件在時尚業的先例程度

| ENGINE 02 元件 | 業界先例 | 判斷 |
|---|---|---|
| LLM 抽取意圖（硬限制＋隱性需求） | Zalando、Myntra Maya、Ask Ralph、Google fan-out、Musinsa query rewriting | **有直接先例**。Zalando 的觀察（顧客描述「想要的感覺」）正好支持「隱性需求」這個問題設定 |
| 需求→設計要素 Kansei 表 | ZOZO 印象語嵌入（研究）、UMood（活動）；學術 Kansei | **沒有量產部署先例**，只有研究和學術基礎。要誠實說是「新嘗試」 |
| fashion CLIP zero-shot 評設計要素 | FashionCLIP（Farfetch 資料）、Musinsa 用 FashionCLIP 2.0 | **有先例**（模型與檢索都有）；但「用 zero-shot 評設計要素分數」這個具體用法沒看到公開部署。Musinsa 自承素色基本款難分，**正是聚陽 OEM 基本款的弱點**，要在 demo 裡主動處理 |
| BM25 + dense + RRF | 只找到「semantic search」「向量檢索」的公開說法 | **沒有時尚業的明確公開先例**（屬通用 IR 做法） |
| 加法式 reranker，分數分解即解釋 | 業界解釋多是 LLM rationale（Amazon、eBay）或 attention 熱力圖 | **沒有直接先例**，是差異化賣點；也比 LLM 事後編理由更可稽核 |
| 反事實檢查理由 | 沒找到 | **沒有先例**。eBay A/B 把召回和理由綁在一起測，說明業界很少把解釋的因果單獨驗證，我們的反事實檢查剛好補這個洞 |
| 搭配相容性項 | POG（CTR +70%）、Pinterest CTL/STL、Amazon CVPR 2020、Zalando AFRA、Levi's Outfitting、Ask Ralph laydown | **強力先例**，是最成熟的一塊 |
| 由回饋改善（critiquing、thumbs） | Zalando thumbs 與修正、Stitch Fix Style Shuffle（100 億次互動）、FashionVLP、Maya 追問 | **有先例**；Stitch Fix 是「回饋→排序→設計」最完整的公開閉環 |
| 需求缺口回饋給設計（OEM 視角） | Fast Retailing、Stitch Fix Hybrid Designs、Walmart Trend-to-Product、Amazon Opportunity Explorer | **有先例且是聚陽客戶正在做的事** |

### c2. 給聚陽評審的 demo 話術

1. **「這是你們客戶已經在做、但 OEM 端還看不到的東西。」** Fast Retailing 官方說每年 3,900 萬則回饋用 AI 分析後送給商品部；Gap 說要用 AI 加速設計和企劃。ENGINE 02 把「一句話→隱性需求→哪些設計要素沒被現有商品滿足」變成可以帶進客戶提案的結構化輸出。
2. **可解釋性要講「可稽核」，不只是「會說理由」。** Amazon Help Me Decide、eBay LLM-PKG 的理由是 LLM 生成的文字；我們的理由就是分數本身（例如 trustworthy → 墊肩結構 +0.8 × 模型信心），而且用反事實驗證「拿掉這個要素，排名真的會掉」。可引用 eBay 的例子說明業界連理由有沒有效都很難單獨驗證。
3. **展示「回饋讓結果變好」要借用業界做法。** 仿 Zalando 的 thumbs 與「換一個」修正、Stitch Fix Style Shuffle：現場做一輪回饋，秀出 Kansei 權重或使用者向量怎麼變、nDCG／命中率前後差多少。要配前後對照，不要只秀單一案例。
4. **把缺口分析講成 Amazon Opportunity Explorer 的 OEM 版本。** 「高需求、低滿足」＝很多查詢的隱性需求在目錄裡分數都偏低。這一格可以直接做成給聚陽設計／業務團隊的「開發建議」（例如「不想看起來太用力」＋通勤場景 → 霧面、低對比、結構化剪裁的供給不足）。
5. **搭配項引用 POG／Pinterest 的量級。** 說明 outfit compatibility 在 Alibaba 線上 CTR 比基線高 70% 以上、Pinterest Shop The Look 互動 +80%，所以把搭配項放進排序是有依據的。
6. **主動講限制，建立信任。** 基本款（聚陽大宗：機能運動服、睡衣、內著）在 CLIP 上難分（Musinsa 自承），所以我們加上文字屬性／BM25 與 Kansei 表來補；Kansei 表目前是專家先驗，需要用回饋校準。這正好接到「從回饋持續改善」的評分重點。
7. **對應聚陽品類。** 聚陽 52% 是 Functional Sportswear（Dick's、Athleta、Old Navy Active），隱性需求範例建議多放運動／機能情境（如「怕穿去健身房太顯眼」「想看起來專業但要能動」），比正式西裝更貼近評審業務。

### c3. 未完成／需保留的地方

- JD 時尚、Nike、H&M 官方頁、Inditex 官方頁、SHEIN 官方數字：本輪未能取得一手來源（搜尋配額用完或頁面 403／404），不要在簡報中引用具體數字。
- Farfetch FashionCLIP 論文**沒有**聲明線上部署；Musinsa 案例是 AWS 部落格上的測試結果，不要說成「全站上線成效」。
- eBay LLM-PKG 的 A/B 數字僅見於搜尋摘要（U）。
