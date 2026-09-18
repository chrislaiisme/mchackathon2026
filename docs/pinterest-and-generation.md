# Pinterest 趨勢訊號與概念圖生成

**負責人：Pinterest 板子策展是品諭（依規劃文件）；兩個模組的程式碼負責人都還沒確認。** 這份是從 [hackathon-brief.md](hackathon-brief.md) 抄出來的骨架摘要——正式負責人接手後應該把這裡展開成真正的規格，不要直接把這份當成定案。這兩塊依團隊「5 人對 6 條線」的分法合併成一條線（Pinterest 的工作量集中在賽前，現場那兩天主力轉去做生成迴圈）。

## Pinterest 趨勢訊號

Pinterest API v5 的 Trial access 只能讀寫／搜尋連結帳號自己的 pins／boards，沒辦法用關鍵字搜整個公開網站（那需要 partner／beta 權限，審核時程不可控，兩週內申請不下來）。實際做法：團隊自己手動策展一個板子，放進目標／趨勢圖，再用 Trial access 讀這個板子。這樣仍然算是串了 Pinterest API，只是「搜尋」這一步是人工先做好，不是即時關鍵字搜尋。

這是餵給 ENGINE02 排序權重（跟 ENGINE03 偏好模型）的補充訊號——「近期趨勢」的加分，不是取代 Polyvore 商品庫。使用者看到的產品畫面上不會直接出現「Pinterest」這個名字。Pinterest 原圖只在內部算相似度用，絕對不要放進現場 demo 或簡報畫面（版權疑慮）。

## 概念圖生成

OpenAI Responses API，`image_generation` tool，`action: "auto"`。每一輪的 `Intent` 轉成一段抽象的 prompt（顏色／剪裁／場合／材質——避免點名真實品牌或設計師，畢竟是在出題企業的評審面前 demo）。多輪銜接用 `previous_response_id`，讓模型看得到上一輪的圖加上這輪回饋，不用整張重生。範例程式碼在 [hackathon-brief.md](hackathon-brief.md) 的「評分怎麼具體變成下一次生成的修正」段落。

**Live** demo 要跑幾輪完全由使用者回饋決定（絕不是模型自己判斷要不要停）。**離線驗證迴圈**則固定跑 2–4 輪，用 FashionCLIP 相似度當硬性的量化停止依據——見 [validation-plan.md](validation-plan.md)。

生成出來的圖片同步轉成 FashionCLIP 向量，併入 ENGINE02 dense 側的分數，讓生成分支跟檢索分支互相加強，不是兩個各自獨立的功能。

## 依賴

`OPENAI_API_KEY`（生成用）、`PINTEREST_ACCESS_TOKEN`（讀 Pinterest 用）——兩個都在 `.env.example` 裡。
