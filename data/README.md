# data/

**只存在本機，不進版控**（`.gitignore` 排除本資料夾內除了這份 README 以外的所有檔案）。
原因：資料集體積大；Pinterest 圖片只能內部使用，不能公開。

| 資料夾 | 內容 | 負責線 |
|---|---|---|
| `polyvore/` | Polyvore Outfits Dataset | 線 2 |
| `pinterest_trends/` | 從團隊 Pinterest 板子讀取的趨勢圖 | 線 2 |
| `target_images/` | 驗證用目標圖 30–50 張（額度不足時縮到 15–20 張） | 線 1 |
| `demo_cache/` | demo 情境預先準備的結果與圖片，網路失效時重播用 | 線 3、線 5 |

demo 當天使用的電腦需要事先把 `demo_cache/` 複製過去。
