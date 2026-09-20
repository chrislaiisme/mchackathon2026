# ENGINE03 — 偏好回饋迴圈

**現況（2026-09-20）：已實作並接通，前後端都在跑。** `backend/engine03_feedback/` 有完整實作（`contracts.py`／`service.py`／`attributes.py`＋測試），ENGINE01 透過 `engine03_client.py` 呼叫它，前端 `stylist-experience.tsx::submitPendingRoundFeedback()` 會在每輪對話送出前自動把使用者的收藏／不喜歡／分項打分／整套喜歡送過去。**正式規格請直接看 `backend/engine03_feedback/README.md`／`contracts.py`**，下面「⚠️」開頭的兩節是歷史調查記錄（曾經三套契約並存、後來怎麼收斂成現在這套），留著給接手的人理解決策脈絡，不是待辦事項。

## ⚠️ 歷史記錄：曾經三套互不相容的實作同時存在

（以下是 2026-09-19 的調查結果，記錄「當時混亂在哪、後來怎麼解決」，方案 3 已經是現在採用的那一套，方案 1／2 僅供對照。）

實際狀況一度是**三套 ENGINE03 契約同時存在於程式碼裡**，這是當時「分支有點混亂」的真正原因，不是單純的分支衝突：

1. **`backend/shared/schemas.py` 的 `FeedbackInput`**——ENGINE01 最早定的介面契約（`attribute_scores`、`selected_option_id`），**沒有「不喜歡」的欄位**。下面本文保留的舊提案就是基於這一套設計的。
2. **`bff/feedback/main.py`**——Hermes app 技術棧 `bff/main.py` 的 `POST /feedback`（port 8003）打的是這支，把前端送來的讚／倒讚轉成 `FeedbackInput` 送給 ENGINE02。它的 docstring 承認限制：倒讚只進本地帳本，不會傳給 ENGINE02。**這套只在 `bff/`／Hermes app 那條獨立的技術棧裡運作，不影響現在真正在跑的 demo（前端直打 ENGINE01、ENGINE01 直打 ENGINE02）。**
3. **`backend/engine03_feedback/`（原 PR #14，分支 `engine3-feadback-new`）**——決定性（不吃 LLM、不用 `OPENAI_API_KEY`）、op-based（`chosen_item_id`／`rejected_item_ids`／`excluded_item_ids`／`anchor_item_ids`／attribute scores→設計軸調整），有「不喜歡」「永久排除」的概念，跟 ENGINE02 的 `apply_round()`／`/handshake` 是同一套 op 契約。**這套已經 merge，就是現在採用的那一套。**

`engine02/api.py` 的 `POST /intent/rank`（ENGINE01 每輪 `/recommend` 都在呼叫的端點）同時接受 `intent`（這輪更新後的意圖）跟 `feedback`（`"ops"` key 形狀時會自動呼叫 `apply_round()` 套用）、`prev_intent`（上一輪意圖，供對照評分）——**這條路徑現在真的有呼叫端在用**：`backend/engine01_intent/recommend.py::build_zoned_recommendation()` 把 ENGINE03 回傳的 `engine02_feedback` 當 `feedback` 參數傳進每一次 `intent_rank()` 呼叫。

下面本文保留原本的提案內容（第 2 套方案基於 `FeedbackInput` 設計），純粹當歷史紀錄——**不要照這份舊提案的 JSON 範例動手，正式欄位以 `backend/engine03_feedback/contracts.py` 為準**。

## ⚠️ 歷史記錄：資料庫商品跟「Design for Me」生成圖的回饋要怎麼共用同一套邏輯——現在已經實作

（以下同樣是 2026-09-19 的調查與草案，**2026-09-20 核對：這個設計方向已經實際落地**——`backend/engine01_intent/main.py` 的 `POST /feedback` 現在會依 `source: "catalog"|"generated"` 分流，ENGINE03 這邊對應的 commit 是 `db01cf3 feat(engine3): map generated feedback to design weights`；整套（outfit-level）回饋見 `54869d4 feat(engine3): support outfit favorite feedback`。草案裡「一筆 outfit 回饋拆成兩筆」的分流邏輯方向正確，但**沒有逐欄位比對命名是否完全一致**，改欄位前請先讀 `contracts.py` 為準，不要照下面的 JSON 範例直接套用。）

原始問題描述：資料庫商品跟生成圖現在都需要收藏／不喜歡／打分／整套 Like-NotLike 這四種回饋，而且以後還會細分成「單一商品」跟「整套穿搭」兩種對象——這兩種來源的回饋*邏輯*很像（都是「使用者對某個東西表態」），但*能不能變成 ENGINE02 排序訊號*完全不一樣：資料庫商品有真的 `item_id` 在 ENGINE02 目錄裡，生成圖沒有。當時查證確認：**這塊完全沒有人設計過**——`agent/skills/feedback-interpreter/SKILL.md` 是空的 TODO 檔案；PR #14 的 `interaction.chosen_item_id`／`rejected_item_ids` 是拿去對照 `engine02_response.items[].item_id` 驗證合法性的，生成圖沒有這個 id，直接送會被判定「引用了沒顯示過的商品」而被丟進 `rejected_ops`。

以下是當時擬的具體草案（**現在已經是實作方向，不是還沒拍板的提案**）：

**建議的資料格式**（打 `POST /feedback` 時，每一筆回饋）：

```json
{
  "session_id": "...",
  "round": 3,
  "target_level": "item",              // "item"（單一商品／單一生成格）或 "outfit"（整套穿搭，兩個 zone 一起表態）
  "action": "favorite",                // favorite | dislike | rating | like_outfit | not_for_me_outfit
  "rating_value": null,                 // 只有 action="rating" 才有值，1-5（之後改分項評分時，這裡會變成 {element: score} 的物件，不是單一數字）
  "items": [
    {
      "zone": "top",                    // "top" | "bottom"；target_level="item" 時只會有一筆，"outfit" 時固定兩筆（上衣＋下身）
      "source": "catalog",              // "catalog"（資料庫商品）| "generated"（Design for Me 生成的）——這就是區分兩種來源的欄位
      "item_id": "ENGINE02的product_id",   // source="catalog" 時填真的 product_id
      "design_attributes": null          // source="generated" 時才填，填生成那一格的 varied_attribute／keywords（例如 {"length": "膝上"}），因為生成格沒有 item_id 可以引用
    }
  ]
}
```

**兩條處理路徑（這是關鍵，不是隨意分的）**：

1. `source="catalog"` 的項目 → 走 PR #14（`backend/engine03_feedback`）現有的 `interaction.chosen_item_id` / `rejected_item_ids` / `excluded_item_ids`：favorite→chosen（或 anchor，看使用者是不是要拿它當搭配基準）、dislike→rejected（重複出現多次就考慮升級成 excluded，這個門檻由 ENGINE03 決定）。**這條路現有的驗證邏輯本來就要求這個 id 要出現在 `engine02_response.items[]`（也就是這輪真的顯示過的商品）**，資料庫商品符合這個前提，可以直接用，不用改 ENGINE03 的程式碼。
2. `source="generated"` 的項目 → **不能**塞進 `interaction.*`（理由見上面）。這條路要改送 `attribute_scores`：把 `design_attributes` 裡的欄位（例如 `length: 膝上`）對應到 ENGINE02 kansei 認得的設計軸 id，favorite 對應到接近 1 的分數、dislike 對應到接近 0 的分數。**這個對應表（生成格的中文屬性名稱 ↔ ENGINE02 kansei 設計軸 id）需要 ENGINE02 負責人一起確認**，不是 ENGINE01 這邊可以單方面定的。

**整套（`target_level="outfit"`）回饋怎麼處理**：一筆 outfit 回饋會拆成兩筆（上衣一筆、下身一筆），各自照上面兩條路徑分流——因為使用者可能整套裡一件是資料庫商品、一件是生成的（例如資料庫上衣配生成的下身），兩邊的 `source` 不一定一樣，不能假設整套一定同源。

**採用順序**：使用者確認過方向是「先進 ENGINE03 當權重（`WeightAdjustment`／`design_adjust_steps`），之後再讓這個權重影響 ENGINE02 的排序」——這本來就是 ENGINE03 回饋迴圈的既定設計，不是另外發明新機制，只是要先把上面 `source` 欄位這個分流邏輯定下來，兩種來源才能共用同一個 `/feedback` 端點。

**現在的實作現況（2026-09-20 更新）：已經落地。** `backend/engine01_intent/main.py` 的 `POST /feedback` 會依 `item_feedback.source`／`item.source`（`"catalog"|"generated"`）分流：`catalog` 驗證 `item_id` 在 `state.shown_item_ids` 裡；`generated` 驗證 `item_id` 在 `state.shown_generated_item_ids` 裡，並且改用伺服器端由生成 manifest 保存的 `design_attributes`（不信任瀏覽器傳來的內容）。ENGINE03 這邊對應 `db01cf3 feat(engine3): map generated feedback to design weights`（生成圖回饋映射進設計軸）、`54869d4 feat(engine3): support outfit favorite feedback`（整套回饋）兩個 commit。前端也已經有收藏／不喜歡／打分 UI 並且統一存進 `preferenceService`，細節見 `docs/status.md`「前端」一節。**欄位命名有沒有逐字照這份草案落地沒有重新核對過**，改動前請以 `backend/engine03_feedback/contracts.py`／`backend/shared/schemas.py` 的 `FeedbackRequest` 為準。

## 目標

把一輪的回饋轉成能讓下一輪真的、可量化地變準的修正——這是整個比賽現場評測方式的核心引擎（評審出題 → 看結果 → 給回饋 → 出第二題 → 檢查系統是否真的變準）。簡報明確把「量化可驗證」列成這個引擎的評分重點之一。

## 跟 ENGINE01／ENGINE02 的分工（這份文件的提案，跟上面真實分支的設計不一樣，見上面警語）

使用者自己追問過這件事，這裡直接畫清楚兩條資料流，全程不交叉、只在 ENGINE02 那一步合流：

```
使用者打字／講話（這輪新的一句話）
  └─→ ENGINE01（POST /intent，extract_intent()）→ 更新後的 Intent
                                                        │
使用者對上一輪結果的動作（收藏／不喜歡／分項打分／整套試穿讚踩）              │
  └─→ ENGINE03（結構化輸入，不碰自由文字）→ weight_adjustments  │
                                                        ▼        ▼
                                      ENGINE02（POST /intent/rank：intent 欄位＋feedback 欄位一起送）
```

- **自由文字一律先經過 ENGINE01，這份提案裡沒有第二套獨立的自然語言拆解邏輯**：使用者這輪不管打字還是講話，前端都呼叫 `POST /intent`，用 ENGINE01 現有的 `extract_intent()` 更新同一組 `Intent` 欄位——避免同一件事在兩個引擎各做一次、還可能兜不起來。**這一點正是跟上面真實分支最大的分歧，還沒有定論，等正式負責人接手時要跟 ENGINE01/02 負責人一起拍板選哪一個方向。**
- ENGINE03 收的是**結構化的使用者動作**：這一輪裡「使用者真的有做動作」的每張卡片（收藏／不喜歡／分項打分，只送有動作的，沒動作的完全不送，見下面「輸入」）＋整套試穿讚踩（`top_product_id`＋`bottom_product_id`＋讚／踩，只有整套試穿才有，見 [frontend.md](frontend.md) 代辦事項 4）＋目前的 `Intent`（唯讀上下文，讓 ENGINE03 知道使用者現在到底在找什麼，不是拿去重算）。
- ENGINE03 只輸出 `weight_adjustments`（軟性加權，交給 ENGINE02 用），**不獨立產生新的 `updated_intent`**——`FeedbackResult.updated_intent` 這個既有欄位的定位是「回傳當下這輪 ENGINE01 已經算好的 Intent，給前端顯示用的一份 echo」，不是 ENGINE03 自己重新推算出來的。
- **ENGINE03 不需要回傳任何東西給 ENGINE01**——迴圈靠 ENGINE02 收斂：`weight_adjustments` 透過 `POST /intent/rank` 既有的 `feedback` 欄位（`IntentRankRequest.feedback`，ENGINE02 那邊已經有 `engine02/handshake.py::apply_round` 在處理）交給 ENGINE02，下一輪 `/recommend` 呼叫時帶著這份 feedback 一起送出去；ENGINE01 全程只聽使用者自己打的新句子，不會被 ENGINE03 的輸出影響。

## 輸入

自由文字回饋（見上一節，這份提案裡不會直接送進 ENGINE03），加上分項評分（顏色／版型／圖案／領子），推薦商品跟生成概念圖**分開**打分，不是打一個總分。粒度更細，ENGINE03 才能調得更精準，前端也才能明確秀出使用者到底是對哪個屬性不滿意（強化「可解釋」）。

**規則（2026-09-19 補充，前端代辦事項 4 帶出來的要求）：每張圖片的收藏／不喜歡／分項打分／整套試穿讚踩全部都是選填，使用者對某張圖片完全沒有任何動作，這張圖片就不能算進這一輪的權重調整計算。** 不能把「使用者沒表態」當成「中立」或默認的某個分數去帶進運算，這樣會把「使用者沒空看」誤判成一種偏好訊號。實作上，ENGINE03 收到的每一輪回饋資料裡，只有使用者真的做過動作的項目才會出現，沒有動作的項目根本不會被送過來（而不是送一個空值/預設值再靠 ENGINE03 這邊過濾）。

**整套試穿讚踩的額外限制（2026-09-19 補充）**：只有虛擬形象同時穿上上衣區＋下身區（一整套）才會有這筆資料，只穿單一單品不會產生這個訊號——前端那邊沒有按鈕可以按，自然不會送出來。

確切的資料形狀（怎麼標示「這是對哪張卡片的哪個動作」）還沒有定案，草案見 [interface-contract.md](interface-contract.md) 第 7 節。

## 處理方式

GPT structured output（chat completions，不用 LangChain）把分項評分＋結構化動作轉成 `weight_adjustments`。

## 輸出

`weight_adjustments`（`WeightAdjustment[]`，交給 ENGINE02 用）＋當下這輪的 `Intent` echo（給前端顯示，不是重算）。這個迴圈會一直跑到使用者滿意為止——不是固定兩輪就停——但現場 demo 至少要把第一輪跟第二輪並排展示出來。

## 介面

輸入：`FeedbackInput`。輸出：`FeedbackResult`（`updated_intent`、`weight_adjustments`）——見 [interface-contract.md](interface-contract.md)。跟 ENGINE02 的交接方式：`POST /intent/rank` 既有的 `feedback` 欄位（`IntentRankRequest.feedback`），細節見上面「跟 ENGINE01／ENGINE02 的分工」。

## 怎麼讓這個迴圈在台上看得出來有效

定義一個「符合度分數」（`RetrievalResult.match_score`）：目前結果跟目前結構化意圖的符合程度（例如意圖要求的顏色／場合／預算條件，推薦清單裡實際符合的比例）。回饋前顯示一次，ENGINE03 處理完回饋、重新產出結果後再顯示一次——例如畫面上直接秀「符合度：62% → 89%」。這樣「回饋迴圈有效」就不是一句空話，而是評審眼前真實發生的數字變化。

「1 個 `WeightAdjustment` 大概等於幾步權重調整」這類量化細節這份提案先留白——沒有實作依據前不要瞎編數字；上面提到的真實分支的 README 有一條量化過的參考值（「1 feedback = 2 steps」），正式定案時可以參考那邊，不是這裡憑空定的。

## 依賴

`OPENAI_API_KEY`。
