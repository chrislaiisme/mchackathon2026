# mcp_servers/trends/

負責線：線 2｜商品推薦與流行趨勢
對應功能：FR-006 Trend Signal

## 負責內容

- 讀取團隊 Pinterest 板子上手動挑選的趨勢圖
- 提供趨勢訊號給推薦排序與使用者偏好
- 使用者沒附參考圖時，挑選相近的輔助參考圖
- 使用者介面不出現 Pinterest 名稱；原圖不公開展示

## 介面

- 提供：輔助參考圖（線 4）、趨勢訊號（本線的 `catalog/`）

本機圖片快取放在 `data/pinterest_trends/`（不進版控）。

目前狀態：尚未開始。

---

（以下併自搬移前的 `mcp_servers/trends/README.md`）

# Pinterest — 趨勢訊號串接

**負責人：品諭負責板子策展（依規劃文件）——程式碼負責人還沒確認。** 這是建 repo 骨架時順便建立的佔位資料夾，讓這條線可以馬上開始動工。

Pinterest API v5 的 Trial access 只能讀寫／搜尋連結帳號自己的 pins／boards，沒辦法用關鍵字搜整個公開網站（partner 等級的檢索端點審核時程不可控，兩週內申請不下來）。實際做法：手動策展一個團隊板子，放進理想的趨勢／目標圖，再用 Trial access 讀這個板子。這樣仍然算是串了 Pinterest API，只是資料來源是人工先篩選好的，不是即時關鍵字搜尋。這個訊號會餵進 ENGINE02 的排序權重（使用者不會在畫面上直接看到「Pinterest」這個名字），也是離線驗證迴圈（見 `evals/`）的隱藏目標圖來源。

完整規格：[../../docs/pinterest-and-generation.md](../../docs/pinterest-and-generation.md)。

需要 `PINTEREST_ACCESS_TOKEN`（`.env.example` 裡有）。簡報裡的提醒：Pinterest 原圖只在內部算相似度用——絕對不要出現在現場 demo 或簡報畫面上（版權疑慮）。
