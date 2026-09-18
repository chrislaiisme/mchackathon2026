# Pinterest 趨勢訊號與概念圖生成

**負責人：Pinterest 板子策展是品諭（依規劃文件）；兩個模組的程式碼負責人都還沒確認。** 這份是從 [hackathon-brief.md](hackathon-brief.md) 抄出來的骨架摘要——正式負責人接手後應該把這裡展開成真正的規格，不要直接把這份當成定案。這兩塊依團隊「5 人對 6 條線」的分法合併成一條線（Pinterest 的工作量集中在賽前，現場那兩天主力轉去做生成迴圈）。

## Pinterest 趨勢訊號

Pinterest API v5 的 Trial access 只能讀寫／搜尋連結帳號自己的 pins／boards，沒辦法用關鍵字搜整個公開網站（那需要 partner／beta 權限，審核時程不可控，兩週內申請不下來）。實際做法：團隊自己手動策展一個板子，放進目標／趨勢圖，再用 Trial access 讀這個板子。這樣仍然算是串了 Pinterest API，只是「搜尋」這一步是人工先做好，不是即時關鍵字搜尋。

這是餵給 ENGINE02 排序權重（跟 ENGINE03 偏好模型）的補充訊號——「近期趨勢」的加分，不是取代 Polyvore 商品庫。使用者看到的產品畫面上不會直接出現「Pinterest」這個名字。Pinterest 原圖只在內部算相似度用，絕對不要放進現場 demo 或簡報畫面（版權疑慮）。

## 概念圖生成

OpenAI Responses API，`image_generation` tool，`action: "auto"`。每一輪的 `Intent` 轉成一段抽象的 prompt（顏色／剪裁／場合／材質——避免點名真實品牌或設計師，畢竟是在出題企業的評審面前 demo）。多輪銜接用 `previous_response_id`，讓模型看得到上一輪的圖加上這輪回饋，不用整張重生。範例程式碼在 [hackathon-brief.md](hackathon-brief.md) 的「評分怎麼具體變成下一次生成的修正」段落。

**Live** demo 要跑幾輪完全由使用者回饋決定（絕不是模型自己判斷要不要停）。**離線驗證迴圈**則固定跑 2–4 輪，用 FashionCLIP 相似度當硬性的量化停止依據——見 [validation-plan.md](validation-plan.md)。

生成出來的圖片同步轉成 FashionCLIP 向量，併入 ENGINE02 dense 側的分數，讓生成分支跟檢索分支互相加強，不是兩個各自獨立的功能。

## 虛擬形象試穿（延伸功能，2026-09-18 使用者口頭補充，不在原始簡報或 hackathon-brief.md 裡）

生圖之後的下一步：把生成出來的概念圖給虛擬形象「穿上」，讓使用者看到接近實際上身的樣子，不只是單純的服裝概念圖。跟前面的概念圖生成一樣，正式負責人接手後要把這裡展開成真正的規格，這裡先記下已經定案的方向：

- **預設虛擬形象**：每個使用者一開始就有一個固定的預設虛擬形象可以用，不需要額外設定，零門檻就能看到試穿效果。
- **客製化虛擬形象**：使用者願意的話，可以上傳一張全身照＋填身高體重，系統就用這些資料客製化出屬於這個使用者自己的虛擬形象（比預設形象更貼近本人）。全身照上傳這塊可以直接沿用 [engine01-intent.md](engine01-intent.md) 待辦事項裡「圖片上傳功能」同一套機制（本機 `data/uploads/`，不進資料庫）。
- **回饋機制待定**：使用者對試穿結果的回饋，可能是細項打分（例如版型合身度、顏色是否適合本人），也可能是單純喜歡／不喜歡——這兩種都在考慮中，還沒定案，正式負責人要跟團隊拍板一個方向。如果最後走細項打分，設計上可以直接沿用 [interface-contract.md](interface-contract.md) 裡 `FeedbackInput`／`AttributeScore` 同一套結構（`target` 欄位目前只有 `"recommended"`／`"generated"` 兩種，屆時可能要加第三種，例如 `"tryon"`），不用另外發明一套回饋格式。

跟 ENGINE01／ENGINE02 的關係：虛擬形象是「per-user」的持久資料（不是單一對話 session 裡的東西），性質上跟 `UserProfile` 裡已有的 `age_range`／`style_preferences` 類似，正式設計時可以考慮要不要併進 `UserProfile`，或另外開一個模型——這個決定留給正式負責人跟 ENGINE01 owner 一起談，這裡不先幫忙決定。

**前端互動想法（同樣還沒定案）**：點一下虛擬形象圖片切換「穿上生成的衣服」跟「沒穿」，像奇跡暖暖那樣——只要試穿後的圖跟原本（沒穿／預設）的圖都準備好了，前端純粹是切換顯示哪一張，不用額外呼叫後端。細節見 [frontend.md](frontend.md#延伸功能待討論想法使用者口頭提出還沒定案正式負責人接手時要評估要不要做)。

## 依賴

`OPENAI_API_KEY`（生成用）、`PINTEREST_ACCESS_TOKEN`（讀 Pinterest 用）——兩個都在 `.env.example` 裡。
