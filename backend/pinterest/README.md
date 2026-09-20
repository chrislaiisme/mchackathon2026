# Pinterest — 趨勢訊號串接

**負責人：品諭負責板子策展（依規劃文件）——程式碼負責人還沒確認。** `client.py` 已經是真的實作，對真實 API／真實策展板子驗證過（見根目錄 CLAUDE.md「環境備註」），不是占位資料夾。

Pinterest API v5 的 Trial access 只能讀寫／搜尋連結帳號自己的 pins／boards，沒辦法用關鍵字搜整個公開網站（partner 等級的檢索端點審核時程不可控，兩週內申請不下來）。實際做法：手動策展一個團隊板子，放進理想的趨勢／目標圖，再用 Trial access 讀這個板子。這樣仍然算是串了 Pinterest API，只是資料來源是人工先篩選好的，不是即時關鍵字搜尋。這個訊號會餵進 ENGINE02 的排序權重（使用者不會在畫面上直接看到「Pinterest」這個名字），也是離線驗證迴圈（見 `validation/`）的隱藏目標圖來源。

完整規格：[../../docs/pinterest-and-generation.md](../../docs/pinterest-and-generation.md)。

需要 `PINTEREST_ACCESS_TOKEN`（`.env.example` 裡有）。簡報裡的提醒：Pinterest 原圖只在內部算相似度用——絕對不要出現在現場 demo 或簡報畫面上（版權疑慮）。
