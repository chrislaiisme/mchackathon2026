# ENGINE03 — 偏好回饋迴圈

**負責人：待確認。`backend/engine03_feedback/` 目前是空的（只有 README 佔位），這份文件是 ENGINE01 負責人 2026-09-19 的規格提案，不是定案**——正式負責人接手後應該覆核每一條，尤其是下面「⚠️ 跟已存在的真實實作有落差」那一節，那份東西比這裡寫的更完整、更可信。

## ⚠️ 2026-09-19 更新：三套互不相容的實作同時存在，這份文件底下的提案不是要採用的那一套

**這個警告區塊之前的版本已經過期**——只提到最早、後來被 rebase 掉的 `origin/engine03-feedback`（commit `e697d8d`）。實際狀況是**三套 ENGINE03 契約同時存在於程式碼裡**，這才是使用者反映「分支有點混亂」的真正原因，不是單純的分支衝突。濃縮版見 [docs/status.md](status.md) 的「ENGINE03」一節，這裡是完整版：

1. **`backend/shared/schemas.py` 的 `FeedbackInput`**——ENGINE01 最早定的介面契約（`attribute_scores`、`selected_option_id`），**沒有「不喜歡」的欄位**。下面本文的提案就是基於這一套設計的，見下面「跟真實實作的落差」。
2. **`bff/feedback/main.py`（已經在 main 上）**——Hermes app 技術棧的 `bff/main.py` 的 `POST /feedback`（port 8003）現在打的就是這支。把前端送來的讚／倒讚轉成 `FeedbackInput` 送給 ENGINE02。**它自己的 docstring 承認限制**：`FeedbackInput` 沒有「不喜歡哪幾張卡」的欄位，所以倒讚只會進本地帳本，不會傳給 ENGINE02——這套現在能跑，但天生做不到「不喜歡」這個前端已經在做的明確需求。
3. **`backend/engine03_feedback/`（PR [#14](https://github.com/chrislaiisme/mchackathon2026/pull/14)，分支 `engine3-feadback-new`，尚未 merge）**——決定性（**已經拿掉 LLM 跟 `OPENAI_API_KEY` 依賴**，跟這份文件寫作當下的認知不同，最新版是純規則式的分數門檻映射，不吃自由文字）、op-based（`chosen_item_id`／`rejected_item_ids`／`excluded_item_ids`／`anchor_item_ids`／attribute scores→設計軸調整），**這套才真的有「不喜歡」「永久排除」的概念**，剛好對上前端的需求。有 7 項測試，用 `git merge-tree` 確認過跟目前 main／engine01-intent 完全不衝突，可以直接乾淨 merge。

**決定性的一塊拼圖**：ENGINE02 其實已經準備好接第 3 套了。`engine02/api.py` 的 `POST /intent/rank`（ENGINE01 現在每一輪 `/recommend` 都在呼叫的端點）本來就同時接受 `intent`（這輪更新後的意圖）跟 `feedback`（如果裡面有 `"ops"` key，也就是 PR #14 `FeedbackRound` 的形狀，`engine02/api.py` 會自動呼叫 `apply_round()` 套用），還有 `prev_intent`（上一輪意圖，供對照評分）——也就是說**「ENGINE01 重新抽出的關鍵字」跟「ENGINE03 的回饋」可以在同一次 `/intent/rank` 呼叫裡一起送進去、一起影響這一輪的排序**，`engine02/intent_adapter.py::feedback_from_engine03()`（第 521 行起）甚至還特別防呆：收到 `ops` 形狀的 payload 會明確提示呼叫端改走這條路，不會誤吞。獨立的 `POST /handshake` 端點也是做同一件事（單獨套用一輪回饋，不順便排序），兩支都已經就緒，只是目前完全沒有呼叫端在用。

**建議的下一步順序**：
1. Merge PR #14（風險低，不衝突，有測試）。
2. ENGINE01 新增呼叫 `backend/engine03_feedback`（跑起來是 port 8003）的 client，把結構化回饋（收藏／不喜歡／分項打分／整套 Like-NotLike）送過去，拿回 `FeedbackRound`。
3. `session_store.py` 存住「上一輪的 `Engine02Request`／`Engine02Response`」＋「ENGINE03 回傳的 `FeedbackRound`」。
4. `engine02_client.py::intent_rank()` 補 `feedback`／`prev_intent` 兩個參數，往下傳給 ENGINE02 的 `/intent/rank`。
5. `bff/feedback/main.py` 只有團隊真的要切到 `bff/`／Hermes app 技術棧當 demo 主線時才需要退休／整併，目前不影響現在在跑的 demo 架構（前端直打 ENGINE01、ENGINE01 直打 ENGINE02），可以先不管。

這是跨 ENGINE02／ENGINE03／前端三邊的整合決定，**決定還沒拍板，需要三邊負責人都看過這個結論再動手**，這份文件先如實記錄調查結果，不代表已經定案。下面本文維持原本的提案內容（第 2 套方案基於 `FeedbackInput` 設計，已知跟真的要採用的第 3 套不是同一回事），保留是因為它把整個迴圈的邊界想清楚了，正式定案時可以參考，但**正式負責人接手時應該優先看 `backend/engine03_feedback/README.md`／`contracts.py`，不要把下面這份提案當成規格來源**。

## ⚠️ 2026-09-19 追加：資料庫商品跟「Design for Me」生成圖的回饋要怎麼共用同一套邏輯

使用者接著問：資料庫商品跟生成圖現在都需要收藏／不喜歡／打分／整套 Like-NotLike 這四種回饋，而且以後還會細分成「單一商品」跟「整套穿搭」兩種對象——這兩種來源的回饋*邏輯*很像（都是「使用者對某個東西表態」），但*能不能變成 ENGINE02 排序訊號*完全不一樣：資料庫商品有真的 `item_id` 在 ENGINE02 目錄裡，生成圖沒有。查證後確認：**這塊目前完全沒有人設計過**——`agent/skills/feedback-interpreter/SKILL.md` 整支是空的 TODO 檔案，沒有任何實作；就算 merge 了 PR #14，它的 `interaction.chosen_item_id`／`rejected_item_ids` 也是拿去對照 `engine02_response.items[].item_id` 驗證合法性的，生成圖沒有這個 id、根本不在 ENGINE02 的候選池裡，直接送會被判定「引用了沒顯示過的商品」，整筆回饋被丟進 `rejected_ops`（等於白送）。

以下是可以拿去跟 ENGINE02／ENGINE03／前端三邊討論的具體草案，**還沒拍板，只是把問題想清楚、給一個可以討論的起點**：

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

**現在的實作現況**：`backend/engine03_feedback`（PR #14）目前只認得 `interaction`／`attribute_scores` 這兩個既有欄位，還沒有 `target_level`／`items[].source`／`design_attributes` 這些——這份格式需要 ENGINE01／ENGINE02／ENGINE03／前端一起看過、拍板欄位命名之後才能真的實作。另外，實作的**前提**是前端要先有生成圖卡片的收藏／不喜歡／打分 UI（目前連資料庫商品這塊都還在許綺文那邊修，見上面代辦事項 4／`docs/status.md`）——這份格式規劃在前，UI／後端接線在後，不是今天就要做完的量。

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
