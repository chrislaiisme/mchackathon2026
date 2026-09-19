# Pinterest 趨勢訊號與概念圖生成

**負責人：Pinterest 板子策展是品諭（依規劃文件）；兩個模組的程式碼負責人都還沒確認。** 這份是從 [hackathon-brief.md](hackathon-brief.md) 抄出來的骨架摘要——正式負責人接手後應該把這裡展開成真正的規格，不要直接把這份當成定案。這兩塊依團隊「5 人對 6 條線」的分法合併成一條線（Pinterest 的工作量集中在賽前，現場那兩天主力轉去做生成迴圈）。

## Pinterest 趨勢訊號

Pinterest API v5 的 Trial access 只能讀寫／搜尋連結帳號自己的 pins／boards，沒辦法用關鍵字搜整個公開網站（那需要 partner／beta 權限，審核時程不可控，兩週內申請不下來）。實際做法：團隊自己手動策展一個板子，放進目標／趨勢圖，再用 Trial access 讀這個板子。這樣仍然算是串了 Pinterest API，只是「搜尋」這一步是人工先做好，不是即時關鍵字搜尋。

這是餵給 ENGINE02 排序權重（跟 ENGINE03 偏好模型）的補充訊號——「近期趨勢」的加分，不是取代 Polyvore 商品庫。使用者看到的產品畫面上不會直接出現「Pinterest」這個名字。Pinterest 原圖只在內部算相似度用，絕對不要放進現場 demo 或簡報畫面（版權疑慮）。

## 單輪參考圖解析（代辦事項 2，2026-09-19 新增，ENGINE01 已實作）

除了上面「趨勢訊號」這個離線／整體排序用途之外，2026-09-19 起 Pinterest 板子多了第二個用途：**每一輪 `POST /intent` 的參考圖 fallback**。解析順序：

1. **使用者這一輪有上傳參考圖** → 直接用使用者上傳的圖（見 [engine01-intent.md](engine01-intent.md) 的圖片上傳端點）。
2. **使用者沒上傳** → 用這一輪更新後的 `Intent`（顏色／品項／風格關鍵字／場合……）去比對團隊策展的板子（`https://www.pinterest.com/pinyucs15/intentweave-references/`，**板子的顯示名稱是「IntentWeave References」**——注意跟網址 slug `intentweave-references` 不一樣，`PINTEREST_BOARD_NAME` 環境變數要填顯示名稱；比對邏輯也會把連字號／空白正規化，兩種寫法都吃得到），比對邏輯是關鍵字子字串比對＋一個小型中英對照表（板子上的 pin 是英文策展內容，純中文比對命中率是 0%，見 [`backend/pinterest/client.py`](../backend/pinterest/client.py)），命中就用比對到的那張 pin 的圖。**已對真實 API／真實板子驗證過**，過程中發現並修掉上面這兩個問題。
3. **兩者都沒有** → 不帶任何參考圖，繼續往下跑，不擋 `/intent` 的主流程。

**這張圖依照上面已經定案的規則，只能給 ENGINE02 內部當參考特徵／生成 prompt 素材，不會顯示在使用者畫面上**——這條規則這次新用途也一樣適用，2026-09-19 有跟使用者確認過維持不顯示。**2026-09-19 起已經正式接進 ENGINE02**：`POST /recommend` 有參考圖時會呼叫 ENGINE02 的 `POST /visual-search`（base64 圖片＋文字），不是透過 `Intent` model 傳遞，細節見 [interface-contract.md](interface-contract.md) 第 6 節；在那之前的解析結果一樣先存在 ENGINE01 內部的 session 狀態（`backend/engine01_intent/session_store.py` 的 `reference_image_url`／`reference_image_source`）。

**2026-09-19 真人測試發現並修正：`POST /visual-search` 現在只有「使用者自己上傳的圖」才會觸發，Pinterest fallback 的圖不會**（`backend/engine01_intent/main.py` 的 `post_recommend()` 現在檢查 `reference_image_source == "user_upload"` 才把圖傳下去，`"pinterest"` 一律當沒有圖，走純文字流程）。原因：Pinterest 板子上關鍵字硬湊出來的圖，使用者根本沒看過也沒選過，讓它的圖片相似度搜尋結果去決定「這輪主要在講哪個分區」，會蓋掉使用者自己打的文字意圖——真人測試打「商務白色襯衫」，上衣區結果被換成一雙襪子就是這樣來的（Pinterest 比對到一張跟襯衫無關的圖，圖片比對的第一名自然也跟襯衫無關）。使用者自己上傳的圖沒有這個問題（那是使用者自己選的、真的想比對的圖），所以只擋 Pinterest 這一種來源。Pinterest 參考圖現在退回原本規劃的角色：只是離線的趨勢訊號／生成模組素材，不參與即時推薦的分區決定。

## 概念圖生成

> **這一節描述的是早期規劃，已經被實作取代。** 現在的做法是「一次生一張六宮格、吃 ENGINE02 top-1 的真實商品照當基準圖」，走 Hermes 的 `image_generate` 工具而不是 OpenAI Responses API，也不需要 `OPENAI_API_KEY`。執行規則在 [`agent/skills/concept-image-director/SKILL.md`](../agent/skills/concept-image-director/SKILL.md)，理由與實測數字在 [concept-image-generation.md](concept-image-generation.md)。下面這段保留作為原始規劃的紀錄。

OpenAI Responses API，`image_generation` tool，`action: "auto"`。每一輪的 `Intent` 轉成一段抽象的 prompt（顏色／剪裁／場合／材質——避免點名真實品牌或設計師，畢竟是在出題企業的評審面前 demo）。多輪銜接用 `previous_response_id`，讓模型看得到上一輪的圖加上這輪回饋，不用整張重生。範例程式碼在 [hackathon-brief.md](hackathon-brief.md) 的「評分怎麼具體變成下一次生成的修正」段落。

**2026-09-19 規格修正：生圖跟資料庫推薦一樣拆成上衣／下身兩張獨立圖片，不是生成一張統一的套裝合照。** 原本討論過「生圖統一生成一整套」，後來使用者修正成要跟 `POST /recommend` 的兩分區展示邏輯一致——這樣兩張圖才能各自獨立試穿、也才能套進 [frontend.md](frontend.md) 代辦事項 3 新增的「我們幫你搭」按鈕。這代表生圖至少要跑兩次生成呼叫（一次上衣、一次下身），`previous_response_id` 的銜接邏輯要分別對上衣鏈跟下身鏈各自維護，不是一條鏈。**「幫你搭」不是隨機挑**（2026-09-19 再次修正）——`POST /style-me` 已實作，接 ENGINE02 的 `/complete-look` 拿有理由的相容性搭配；生圖商品不在 ENGINE02 商品庫裡，錨點傳生圖 id 過去會找不到，這種情況退回 LLM 生一句理由，細節見 [interface-contract.md](interface-contract.md) 第 6a 節。

**Live** demo 要跑幾輪完全由使用者回饋決定（絕不是模型自己判斷要不要停）。**離線驗證迴圈**則固定跑 2–4 輪，用 FashionCLIP 相似度當硬性的量化停止依據——見 [validation-plan.md](validation-plan.md)。

生成出來的圖片同步轉成 FashionCLIP 向量，併入 ENGINE02 dense 側的分數，讓生成分支跟檢索分支互相加強，不是兩個各自獨立的功能。

## 虛擬形象試穿（延伸功能，2026-09-18 使用者口頭補充，不在原始簡報或 hackathon-brief.md 裡）

生圖之後的下一步：把生成出來的概念圖給虛擬形象「穿上」，讓使用者看到接近實際上身的樣子，不只是單純的服裝概念圖。跟前面的概念圖生成一樣，正式負責人接手後要把這裡展開成真正的規格，這裡先記下已經定案的方向：

- **預設虛擬形象**：每個使用者一開始就有一個固定的預設虛擬形象可以用，不需要額外設定，零門檻就能看到試穿效果。
- **客製化虛擬形象**：使用者願意的話，可以上傳一張全身照＋填身高體重，系統就用這些資料客製化出屬於這個使用者自己的虛擬形象（比預設形象更貼近本人）。全身照上傳這塊可以直接沿用 [engine01-intent.md](engine01-intent.md) 待辦事項裡「圖片上傳功能」同一套機制（本機 `data/uploads/`，不進資料庫）。
- **回饋機制：2026-09-19 已定案**——試穿結果的回饋走簡單的 **LIKE IT／NOT FOR ME** 二選一，不是細項打分（細項打分是留給推薦商品／概念圖本身的，見 [frontend.md](frontend.md) 代辦事項 4）。互動流程：圖片下方按 Try On → 右側虛擬形象穿上／再按一次脫掉 → 虛擬形象區塊下方出現 LIKE IT／NOT FOR ME 讓使用者表態。**同一天再補充一條限制：只有上衣區＋下身區都試穿上了（一整套）才能按這兩個按鈕，只穿單一單品不能按**——單一單品看不出「這樣搭好不好看」，這兩個按鈕本來就是對「一整套穿搭」表態，不是對單一商品表態（單一商品的喜歡／不喜歡已經有另一組獨立的收藏／不喜歡按鈕，見 [frontend.md](frontend.md) 代辦事項 4）。這個訊號跟「對圖片本身」的收藏／不喜歡是分開的兩種訊號，且一樣是選填——使用者沒按就不算進 ENGINE03 的權重（見 [engine03-feedback.md](engine03-feedback.md)）。介面上要新增什麼欄位還沒定案，草案見 [interface-contract.md](interface-contract.md)（至少要帶 `top_product_id`＋`bottom_product_id` 兩個 id，不是單一 `product_id`）。

跟 ENGINE01／ENGINE02 的關係：虛擬形象是「per-user」的持久資料（不是單一對話 session 裡的東西），性質上跟 `UserProfile` 裡已有的 `age_range`／`style_preferences` 類似，正式設計時可以考慮要不要併進 `UserProfile`，或另外開一個模型——這個決定留給正式負責人跟 ENGINE01 owner 一起談，這裡不先幫忙決定。

**前端互動想法（同樣還沒定案）**：點一下虛擬形象圖片切換「穿上生成的衣服」跟「沒穿」，像奇跡暖暖那樣——只要試穿後的圖跟原本（沒穿／預設）的圖都準備好了，前端純粹是切換顯示哪一張，不用額外呼叫後端。細節見 [frontend.md](frontend.md#延伸功能待討論想法使用者口頭提出還沒定案正式負責人接手時要評估要不要做)。

## 依賴

`OPENAI_API_KEY`（生成用）、`PINTEREST_ACCESS_TOKEN`（讀 Pinterest 用，2026-09-19 起也被 ENGINE01 的單輪參考圖解析使用，已對真實 API 驗證過）、`PINTEREST_BOARD_NAME`（要比對的板子顯示名稱，預設 `IntentWeave References`——注意是顯示名稱不是網址 slug）——都在 `.env.example` 裡。
