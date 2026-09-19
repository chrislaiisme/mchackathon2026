# bff/images/

使用者對 ENGINE 02 撈到的東西不滿意時，一次生六件新單品讓他挑。

負責線：線 3｜概念圖與選項圖
對應功能：FR-007 Concept Image Generation

## 這裡只做流程，不生圖也不寫 prompt

| 職責 | 在哪 |
|---|---|
| 寫 prompt、呼叫 Hermes、產出六宮格與 manifest | `agent/scripts/generate_grid.py --mode concepts` |
| 把六宮格切成六張單品圖 | `agent/scripts/slice_grid.py` |
| 何時生、重試、把結果整理給前端 | 這裡 |

**依賴**：上面兩支腳本要在 repo 裡才會動。缺檔時回 `ConceptImageUnavailable`，
端點回 502 並指名缺什麼，不會把整輪拖垮。

## 為什麼是一張六宮格，不是生六次

走 Hermes 的 openai-codex provider 一次生圖 26–48 秒。六件逐一生成要三四分鐘，
現場撐不住。擠在一張圖裡實測 **43.8 秒拿到六件，攤下來每件 7.3 秒**。

附帶好處：六格在同一次生成裡產出，攝影規格、背景、水洗色天然一致，
不必額外約束就能互相比較。

## 端點

```
POST /concept-image   {session_id, cells?, model?, dry_run?}
GET  /generated/<路徑>
```

`dry_run` 只組 prompt 與 manifest，不生圖不花額度 —— 開發時先用它。

**明確觸發**，不在每輪自動跑。`/round` 的回傳有 `concept_image_suggested`，
ENGINE 02 為了湊足結果而放寬條件時為 true，前端拿它決定按鈕要不要亮。

## 回傳

```
grid_image   六宮格原圖（展示用）
cells[]      六件單品：image_url、keywords、varied_label（中文，可直接顯示）、check
locked       六格都一樣的屬性（使用者說出口的東西）
unresolved   翻不成英文、沒進圖的字
```

## 版面沒切成會自動重生

`slice_grid.py` 會檢查 gutter 位置是否均勻，不合格就拒切並建議重生。這裡最多重生
`CONCEPT_IMAGE_ATTEMPTS`（預設 2）次；只有版面問題才重生，其餘錯誤照實往上拋。

實測五次裡有一次沒切成，重生一次就過。
