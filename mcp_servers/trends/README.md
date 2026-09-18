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
