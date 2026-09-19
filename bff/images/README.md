# bff/images/

生成平拍單品圖，填進 `RoundResult.concept_image`。

負責線：線 3｜概念圖與選項圖
對應功能：FR-007 Concept Image Generation

## 兩段式：skill 寫 prompt，runtime 執行

| 職責 | 在哪 |
|---|---|
| 寫 prompt（政策） | Hermes skill `agent/skills/concept-image-director/` |
| 整理材料、執行生圖、存檔（流程） | `concept.py` |

流程不交給模型決定要不要做。skill 還沒到位時 `fallback_prompt()` 頂著，整條路現在就能跑。

## 端點

```
POST /concept-image  {session_id, reference_item_id?, prompt?}
GET  /generated/<檔名>
```

`prompt` 給定時就用它（skill 的產出），省略則用 fallback。**明確觸發，不在每輪自動跑** ——
一張 27–50 秒會把整輪拖垮。`/round` 的回傳有 `concept_image_suggested`，目錄給不出使用者要的
東西時為 true，前端拿它決定按鈕要不要亮。

## 材料取自 ENGINE 02，但原話一定要一起帶

| 欄位 | 來源 | 用途 |
|---|---|---|
| `utterance` | 使用者原話 | **目錄詞彙表達不了的細節只存在這裡** |
| `hard` | `match_score_detail.requirements` kind=hard | 必須出現在圖上 |
| `design` | 同上 kind=design | 有方向性的偏好 |
| `relaxed` | `match_score_detail.relaxed` | 目錄給不出什麼 —— 生圖的主角 |
| `unresolved` | `unresolved_from_intent` | 目錄詞彙對不到的說法 |
| `reference_image` | 該輪商品的目錄照片 | 版型與構圖參考 |

實測佐證：輸入「我想要寬鬆的深色牛仔褲，上方有珍珠褲鏈」，ENGINE 02 的結構化欄位裡
**完全沒有「珍珠褲鏈」**（目錄沒有這個概念），只有 `utterance` 保住了它，生成的圖也確實有那條鏈子。

## 已知限制

- Codex 那條路**忽略尺寸參數**，要 1024×1024 可能回 1086×1448，前端不要寫死尺寸。
- `ConceptImage.response_id` 是 OpenAI Responses API 多輪接續用的，Hermes 這條路不支援，恆為 None；
  多輪要接續就把上一張圖當 `reference_item_id` 之外的參考圖傳入。

## 待收斂：呼叫 Hermes 的方式要統一

目前 `concept.py` 是**在同一個直譯器裡** `sys.path` 插進 Hermes repo 再 import。它能跑，但
Hermes 的 plugin 住在自己的虛擬環境，而 prompt 組裝要 import 專案的 engine02（在專案 venv），
兩邊依賴沒有交集，長期會出事。

`agent/scripts/hermes_image.py`（生圖 skill 那條線）採的是**跨行程**做法：用 Hermes 自己的 venv
執行，介面是 stdout 的 JSON，跟 ENGINE 01 shell out 給 `codex exec` 同一套模式。那個做法比較穩。

**這支落地之後，把 `_dispatch_image_generate()` 換成呼叫它**，全專案只留一條呼叫 Hermes 的路。
函式界線已經留好，換掉那一個函式即可，其餘不動。

## 與選項圖的分工

| | 選項圖（`concept-image-director` skill） | 這裡 |
|---|---|---|
| 產出 | 一張六格拼圖，切成六個單變因變體 | 一張單品圖 |
| 用途 | 需求探索的選擇題 | 目錄給不出使用者要的東西時 |
| 觸發 | 出題時 | 使用者按「生成單品」 |

兩者都該走同一條 Hermes 呼叫路徑。
