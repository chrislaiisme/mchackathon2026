# Kansei K 表 v1：文獻依據（kansei_v1_literature）

> 產出日期：2026-09-17　對應檔案：`engine02/resources/kansei_v1_literature.json`
> 用途：ENGINE 02 設計元素權重 β_d = Σ_n p(n)·K[n,d] 的 K 表，從「沒有依據的草稿（v0）」改成「每一格非零值都有文獻出處」。

## 1. 規則

- **有證據才給非零值**：每個非零格都在 JSON 的 `evidence["need|element"]` 裡記了數值、強度、出處和說明；連弱證據都沒有的格子一律是 0。
- **強度與數值上限**：
  - **S（強）**：多個獨立實驗都重現過，|K| ≤ 0.8
  - **M（中）**：單一實驗或問卷，或結果互相矛盾，|K| ≤ 0.5
  - **W（弱）**：專家意見、從別的領域推論，或從服裝整體推到單一部件，|K| ≤ 0.3
  - 實際給的值都比上限保守：最大只有 0.6。
- **V／U 標記**：
  - **V** = 我透過 OpenAlex／PubMed API 讀過摘要。**全文都沒讀**，所以效果量主要來自摘要。
  - **U** = 沒有核實。
  - 本次 WebSearch 的額度用完了，所有出處改用學術資料庫 API，依 DOI 或標題逐篇核對。
- **正負號**：沿用 v0。K > 0 表示「這個元素有助於滿足這項需求」。例如 `avoid_tryhard × visible_logo = −0.6`，意思是明顯的 logo 會讓人更像「太用力」。

## 2. K 表（10 項需求 × 15 個元素）

`·` = 0；數字後面的字母是證據強度（S/M/W）。

| need \ element | structured_shoulders | matte_fabric | glossy_fabric | dark_tone | bright_color | visible_logo | minimal_design | bold_pattern | relaxed_fit | tailored_fit | formal_style | casual_style | crisp_collar | soft_knit | athletic_style |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| trustworthy（被信任） | +0.2W | · | · | · | · | -0.2W | · | · | · | · | +0.5M | -0.4M | +0.2W | · | -0.2W |
| energetic（有精神） | · | · | · | -0.2W | +0.4M | · | · | · | · | · | · | · | · | · | +0.2W |
| polished（俐落專業） | +0.3W | · | · | · | · | · | · | · | -0.4M | +0.5M | +0.6S | -0.5S | +0.3W | · | -0.4M |
| approachable（親切好相處） | · | · | · | -0.2W | +0.2W | -0.4M | · | · | · | · | -0.2M | +0.2M | · | +0.2W | · |
| relaxed（輕鬆自在） | · | · | · | · | · | · | · | · | +0.3W | -0.2W | -0.3W | +0.3W | · | +0.2W | +0.2W |
| avoid_tryhard（怕顯得太用力） | · | +0.2W | -0.2W | · | · | -0.6S | +0.3W | -0.2W | · | · | -0.2W | · | · | · | · |
| avoid_salesperson（怕像業務） | · | · | · | · | · | · | · | · | · | · | -0.2W | · | · | · | · |
| avoid_sloppy（怕顯得邋遢） | · | · | · | · | · | · | · | · | -0.4M | +0.4M | +0.3M | -0.4M | +0.2W | · | -0.3M |
| sporty（有運動感）★新增 | · | · | · | · | +0.2W | · | · | · | · | · | -0.3W | · | · | · | +0.5M |
| avoid_cheap（怕看起來廉價）★新增 | · | · | +0.2W | · | · | · | · | · | -0.2W | +0.5M | +0.4M | -0.2W | · | · | -0.3M |

非零格共 50 個：S 3 格、M 18 格、W 29 格。每一格的完整理由請看 JSON 的 `evidence`。

### 各格的主要依據

| 格子 | 值 | 出處（對應第 4 節的代號） | 一句話理由 |
|---|---|---|---|
| polished × formal_style | +0.6 S | Xun21, Furnham13, Jennings16, Petrilli18, Sotak23 | 在醫療、法律、牙醫、商業情境都有重現：正式服裝被評為較專業、較有經驗 |
| polished × casual_style | −0.5 S | Xun21, Furnham13, Sotak23, Jennings16 | 同上，方向相反 |
| avoid_tryhard × visible_logo | −0.6 S | Berger10, Han10, Garcia18, Cannon18 | 四篇獨立的多研究論文：大 logo 對應高地位需求；懂行的人偏好低調；展示地位標誌會被歸因為印象管理，較不討喜 |
| trustworthy × formal_style | +0.5 M | Petrilli15（系統性回顧）, Furnham13 | 30 篇中有 18 篇偏好正式服裝；亞洲與年長者更明顯；實際看診後效果變弱 |
| trustworthy × casual_style | −0.4 M | Jennings16, Sotak23 | 休閒服裝在信任與倫理感上評分較低 |
| polished／avoid_cheap × tailored_fit | +0.5 M | Howlett13, Rucker81, Oh19 | 訂製西裝在 5 秒內就被評為較自信、較成功、收入較高；合身比寬鬆有利；看起來「較富有」的衣服會提高對能力的判斷 |
| polished × athletic_style | −0.4 M | Xun21, Kraus14 | 刷毛衣／軟殼外套的專業度 3.2 對白袍 4.9；運動褲在實驗中被當作低階層的象徵 |
| approachable × visible_logo | −0.4 M | Cannon18, Garcia18 | 展示奢侈品會降低他人對溫暖度的評價，也較不被選為朋友 |
| approachable × casual/formal | ±0.2 M（結果互相矛盾） | Peluchette07, Karl13, Morris96, Matsuhisa21 對上 Furnham13, Chatelain15 | 有研究支持休閒較親切，也有研究發現正式服裝較友善或沒有差異，所以壓低數值 |
| energetic × bright_color | +0.4 M | Valdez94, Palmer13 | 飽和度預測喚起度（Arousal = −.31B + .60S）；快速、歡快的音樂配到較飽和的顏色（美國與墨西哥受試者） |
| sporty × athletic_style | +0.5 M | Lipson19, Kraus14 | 穿運動休閒服傳達「健身生活方式」；運動褲在實驗中是西裝的對立面 |
| avoid_cheap × formal_style | +0.4 M | Kraus14, Oh19 | 西裝是上層階級的符號 |
| 其餘 W 格 | ≤0.3 | 見 JSON | 多數是從整體服裝推論到部件（肩線、領子），或從包裝、色彩情緒研究推論到服裝 |

## 3. 相對 v0 的改變

**新增需求**
- `sporty`（有運動感）：對應聚陽的機能／運動休閒線。
- `avoid_cheap`（怕看起來廉價）：Oh et al. 2019 在 9 個研究裡都發現，「看起來較富有」的衣服會提高他人對能力的判斷，屬於強證據。

原本考慮加入 `comfortable`（看起來舒適），但找不到以觀察者為對象的研究，所以沒加。

**新增元素**
- `athletic_style`（運動機能風格）：
  - 正向描述詞：leggings、joggers、track jacket、technical performance fabric
  - 反向描述詞：tailored wool office garment、crisp woven dress shirt
  - `applies_to`：top、bottom、outerwear、dress、shoes

原本構想的 `fitted_performance_cut` 和 `neutral_palette` 沒有加：前者從商品照很難和 `athletic_style` 分開，後者只找到包裝和產品領域的證據（Pichierri & Pino 2023，低飽和色讓產品顯得較環保）。

**大幅調降或歸零（v0 → v1）**

| 格子 | v0 | v1 | 原因 |
|---|---|---|---|
| trustworthy × structured_shoulders | +0.8 | +0.2 | 沒有研究單獨檢驗肩線，只能從正式服裝推論 |
| trustworthy × dark_tone | +0.6 | 0 | 沒有支持證據；黑色反而和惡意、攻擊性的觀感有關（Frank & Gilovich 1988） |
| trustworthy × tailored_fit | +0.5 | 0 | Howlett 2013 明確發現訂製西裝**唯獨在信任度上沒有差異** |
| trustworthy × matte／minimal／bold_pattern／glossy | ±0.3～0.5 | 0 | 找不到證據 |
| polished × minimal_design | +0.5 | 0 | 找不到證據 |
| approachable × soft_knit | +0.6 | +0.2 | 只有觸覺研究（而且其中一項沒有重現成功），針織本身沒有人研究過 |
| relaxed × relaxed_fit／casual／formal | ±0.6～0.7 | ±0.3 | 「輕鬆」這個感受沒有被直接測量過，只能從語意推論 |
| avoid_tryhard × formal_style | −0.6 | −0.2 | 刻意穿得不正式可能提升地位觀感（Bellezza 2013），但在面試中對資歷弱的求職者反而不利（Oostrom 2020） |
| avoid_tryhard × glossy_fabric | −0.6 | −0.2 | 只有包裝領域的推論 |
| avoid_salesperson 整列 | 5 格非零 | 只剩 formal −0.2 | 找不到任何研究「像業務」這種觀感 |

**調升**
- `polished × formal_style`：+0.4 → +0.6
- `avoid_tryhard × visible_logo`：−0.5 → −0.6
- `polished`／`trustworthy`／`avoid_sloppy` × `casual_style`：原本是 0，現在是 −0.4～−0.5

**對 PRD 面試範例的含意**

「不想太正式但要可靠」這個情境，目前的文獻**只強力支持「可靠 → 正式」**。「怕太正式」相關的格子（avoid_tryhard、avoid_salesperson × formal）證據都是弱的。所以用 v1 時，面試情境的 β 會偏向正式、壓低休閒。

如果產品想推「商務休閒」，可以參考 Sotak 2023 與 Karl 2013：business casual 在倫理感和可信度上不輸正式服裝。但目前沒有「business casual」這個元素，未來可以考慮新增。

## 4. 出處清單

全部標 V，但都只讀了摘要，沒有讀全文。

| 代號 | 出處 | V/U |
|---|---|---|
| Howlett13 | Howlett, Pine, Orakçıoğlu & Fletcher (2013). The influence of clothing on first impressions. *J Fashion Marketing & Management*. doi:10.1108/13612021311305128 | V |
| Han10 | Han, Nunes & Drèze (2010). Signaling status with luxury goods: the role of brand prominence. *J Marketing*. doi:10.1509/jmkg.74.4.015 | V |
| Berger10 | Berger & Ward (2010). Subtle signals of inconspicuous consumption. *J Consumer Research*. doi:10.1086/655445 | V |
| Valdez94 | Valdez & Mehrabian (1994). Effects of color on emotions. *JEP: General*. doi:10.1037/0096-3445.123.4.394（PMID 7996122） | V |
| Palmer13 | Palmer, Schloss, Xu & Prado-León (2013). Music–color associations are mediated by emotion. *PNAS*. doi:10.1073/pnas.1212562110 | V |
| Bellezza13 | Bellezza, Gino & Keinan (2013). The red sneakers effect. *J Consumer Research*. doi:10.1086/674870 | V |
| Petrilli15 | Petrilli et al. (2015). Physician attire and patient perceptions: systematic review (TAILOR). *BMJ Open*. doi:10.1136/bmjopen-2014-006578 | V |
| Petrilli18 | Petrilli et al. (2018). Patient preference for physician attire, 10 US centres. *BMJ Open*. doi:10.1136/bmjopen-2017-021239 | V |
| Xun21 | Xun et al. (2021). Public perceptions of physician attire and professionalism in the US. *JAMA Netw Open*. doi:10.1001/jamanetworkopen.2021.17779 | V |
| Jennings16 | Jennings et al. (2016). Physicians' attire influences patients' perceptions (orthopaedics). *CORR*. doi:10.1007/s11999-016-4855-7 | V |
| Morris96 | Morris, Gorham, Cohen & Huffman (1996). Fashion in the classroom. *Communication Education*. doi:10.1080/03634529609379043 | V |
| Sotak23 | Sotak, Serban, Friedman & Palanski (2023). Perceptions of ethicality: attire style. *J Business Ethics*. doi:10.1007/s10551-023-05347-7 | V |
| Furnham13 | Furnham, Chan & Wilson (2013). What to wear? Professionalism of dentists and lawyers. *JASP*. doi:10.1111/jasp.12136 | V |
| Sebastian08 | Sebastian & Bristow (2008). Formal or informal? Dress and forms of address, perceptions of professors. *J Education for Business*. doi:10.3200/joeb.83.4.196-201 | V（摘要沒寫效果方向，方向部分為 U） |
| Kraus14 | Kraus & Mendes (2014). Sartorial symbols of social class. *JEP: General*. doi:10.1037/xge0000023 | V |
| Oh19 | Oh, Shafir & Todorov (2019). Economic status cues from clothes affect perceived competence from faces. *Nature Human Behaviour*. doi:10.1038/s41562-019-0782-4 | V（摘要取自預印本 doi:10.31234/osf.io/saqnv） |
| Peluchette07 | Peluchette & Karl (2007). Workplace attire and employee self-perceptions. *HRDQ*. doi:10.1002/hrdq.1208 | V |
| Karl13 | Karl, McIntyre Hall & Peluchette (2013). City employee perceptions of dress. *Public Personnel Management*. doi:10.1177/0091026013495772 | V |
| Garcia18 | Garcia, Weaver & Chen (2018). The status signals paradox. *SPPS*. doi:10.1177/1948550618783712 | V |
| Cannon18 | Cannon & Rucker (2018). The dark side of luxury. *PSPB*. doi:10.1177/0146167218796790 | V |
| Meert13 | Meert, Pandelaere & Patrick (2014). Taking a shine to it. *J Consumer Psychology*. doi:10.1016/j.jcps.2013.12.005 | V |
| Spence21 | Spence (2021). On the questionable appeal of glossy/shiny food packaging. *Foods*. doi:10.3390/foods10050959 | V |
| Frank88 | Frank & Gilovich (1988). Black uniforms and aggression. *JPSP*. doi:10.1037/0022-3514.54.1.74 | V |
| Kamata20 | Kamata et al. (2020). Patient preferences for physician attire in Japan. *J Hospital Medicine*. doi:10.12788/jhm.3350 | V |
| Matsuhisa21 | Matsuhisa et al. (2021). Physician attire and perceived empathy in Japan (quasi-RCT). *BMC Family Practice*. doi:10.1186/s12875-021-01416-w | V |
| Lipson19 | Lipson, Stewart & Griffiths (2020). Athleisure: a qualitative investigation. *Body Image*. doi:10.1016/j.bodyim.2019.10.009 | V |
| Wang11 | Wang, Liu & Wu (2011). High grade sense of silk garment based on Kansei engineering. *Adv Mater Res*. doi:10.4028/www.scientific.net/amr.175-176.859 | V（摘要沒有數據） |
| Rucker81 | Rucker, Taber & Harrison (1981). Clothing variation and first impressions of female job applicants. *SBP*. doi:10.2224/sbp.1981.9.1.53 | V |
| Chatelain15 | Chatelain (2015). Academics' dress and perceived approachability. *JHEPM*. doi:10.1080/1360080x.2015.1056598 | V |
| Wu17 | Wu, Luo, Schroeder & Borgerson (2017). Forms of inconspicuous consumption (China). *Marketing Theory*. doi:10.1177/1470593117710983 | V |
| Ackerman10 | Ackerman, Nocera & Bargh (2010). Incidental haptic sensations. *Science*. doi:10.1126/science.1189993；Study 1 在 2017 年預登記重現失敗 | V |
| Oostrom20 | Oostrom, Ronay & van Kleef (2020). Nonconforming dress in personnel selection. *EJWOP*. doi:10.1080/1359432x.2020.1813112 | V |

**讀過但沒有拿來定 K 值的背景文獻**
- Hester & Hehman (2023). Dress is a fundamental component of person perception. *PSPR*. doi:10.1177/10888683231157961（V）
- Horton, Adam & Galinsky (2023). Enclothed cognition z-curve / meta-analysis. *PSPB*. doi:10.1177/01461672231182478（V）：2015 年以前的研究可重現性堪慮，而且講的是穿的人自己的感受，不是別人怎麼看，所以不用於 K。
- IJCST (2024). Kansei engineering in emotional clothing design（綜述）. doi:10.1108/ijcst-02-2024-0047（V）：只談研究方法，沒有可以直接用的 K 值。

## 5. 注意事項與文化差異

1. **樣本以西方為主**，美國與英國占多數；台灣找不到直接研究。
   - 可以參考的東亞證據有兩項：
     - Petrilli 2015 回顧指出，亞洲與歐洲患者**更偏好正式服裝**，所以在台灣情境下 formal 相關的格子可能還低估了。
     - 日本的兩項研究方向不一致：Kamata 2020 發現「休閒服加白袍」最受偏好，年長者則偏好正式服裝；Matsuhisa 2021 發現男性患者覺得穿休閒服的醫師更有同理心。
   - 關於 logo：Wu 2017 發現中國的低調消費正在興起，但中國傳統上偏好明顯的品牌訊號，所以 `visible_logo` 的負值在華人市場可能要依年齡和城市分群，不能一體適用。
2. **情境依賴很強**：
   - 多數正式／休閒的證據來自醫師、律師、教師等「專業角色」，拿到求職面試是合理的類推，但拿到日常社交就不一定成立。
   - Bellezza 2013 指出，「刻意不正式」只有在觀察者熟悉規範、而且認為是故意的時候才會加分。
3. **看到顏色的感受 ≠ 對穿著者的判斷**：Valdez、Palmer 測的是顏色引起的情緒，推到「穿這個顏色的人看起來有精神」屬於推論。
4. **部件層級證據稀缺**：肩線、領子、光澤、針織、圖案幾乎沒有單獨操弄的實驗，所以全部是 W。這些格子最需要用聚陽或消費者資料來校正（PRD M3 的人工修正步驟）。
5. **反義元素會被重複計算**：formal/casual、tailored/relaxed、glossy/matte、minimal/bold 在表中是成對出現的。只要兩邊都非零，β 的差距就會被放大，建議在計算 c(i,d) 時處理這種共線性。
6. **只讀了摘要**：有些效果量和交互作用（例如性別、年齡）沒有反映在數值上。例如 Xun 2021 發現，穿商務服裝的女性被評為較不專業，但 K 表沒有區分性別。
