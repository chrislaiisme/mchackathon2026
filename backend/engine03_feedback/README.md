# ENGINE 03 — 結構化單品回饋

ENGINE 03 不接自然語言、不呼叫 LLM，也暫時不處理套裝。它一次接收整輪所有有互動的商品，轉成 ENGINE 02 已存在的 `FeedbackState` 欄位。

每次會一起處理「前三輪＋本輪」，最多四輪。BFF 負責保存最近三輪原始資料，Frontend 不需要自己傳歷史。

## 輸入

```json
{
  "session_id": "s1",
  "round": 1,
  "previous_rounds": [],
  "shown_item_ids": ["A", "B", "C"],
  "item_feedbacks": [
    {
      "item_id": "A",
      "favorited": true,
      "attribute_ratings": [
        {"attribute": "polished_formality", "stars": 2},
        {"attribute": "soft_energy", "stars": 5}
      ]
    },
    {"item_id": "B", "disliked": true}
  ]
}
```

- `item_feedbacks` 是陣列：一個 request 可以帶整輪多件商品，不需要逐件呼叫 ENGINE 02。
- 沒有任何操作的商品不要放進 `item_feedbacks`。
- `attribute` 必須是下方 `/attributes` 提供的穩定 id，不能使用模糊的 `color`／`fit`／`material`。
- 收藏和倒讚互斥；倒讚是負向偏好，不是永久排除。
- `previous_rounds` 由 BFF 注入，最多三輪，並且必須由舊到新排列。

## 星等與權重

| 星等 | 權重 |
|---:|---:|
| 1 | -1.0 |
| 2 | -0.5 |
| 3 | 0.0 |
| 4 | +0.5 |
| 5 | +1.0 |

同一 attribute 在多件商品上都有評分時，ENGINE 03 取平均，避免只因為評了較多商品就放大整輪權重。每一筆原始轉換保留在回應的 `attribute_evidence`。
當有歷史輪次時，平均範圍是整個四輪視窗內的所有屬性評分。

## 前端顯示文字

Frontend 透過 BFF `GET /feedback/attributes`（或直接向 ENGINE 03 `GET /attributes`）取得三個方向：

| id | 顯示文字 | ENGINE 03 展開範圍 |
|---|---|---|
| `visual_impact` | 醒目亮眼感 | 色調、亮度、霧面／光澤、Logo、極簡／圖案 |
| `polished_formality` | 俐落正式感 | 肩線、寬鬆／合身、正式／休閒、領型 |
| `soft_energy` | 柔軟動感 | 柔軟針織、運動機能 |

每筆包含穩定 `id`、繁中顯示與說明，以及 `maps_to`（ENGINE 03 會展開的 ENGINE 02 軸）：

```json
{
  "id": "visual_impact",
  "label_zh": "醒目亮眼感",
  "prompt_zh": "你喜歡這件商品的「醒目亮眼感」嗎？",
  "effect_zh": "星等越高，下一輪越偏向明亮、光澤、醒目圖案與明顯 Logo；越低則偏向深色、霧面與極簡。",
  "maps_to": {
    "dark_tone": -0.5,
    "bright_color": 0.5,
    "matte_fabric": -0.5,
    "glossy_fabric": 0.5,
    "visible_logo": 1.0,
    "minimal_design": -0.5,
    "bold_pattern": 0.5
  }
}
```

## 給 ENGINE 02 的輸出

```json
{
  "chosen_item_ids": ["A"],
  "rejected_item_ids": ["B"],
  "choice_history": [
    {
      "shown_item_ids": ["A", "B", "C"],
      "chosen_item_id": "A",
      "rejected_item_ids": ["B"]
    }
  ],
  "design_weight_delta": {
    "structured_shoulders": -0.5,
    "formal_style": -0.25,
    "soft_knit": 1.0,
    "athletic_style": 1.0
  }
}
```

這就是 `engine02.contracts.FeedbackState` 真正接受的欄位子集。Orchestrator/BFF 應把整個物件一次放進 ENGINE 02 `/retrieve` 的 `feedback`，不應每件商品呼叫一次 ENGINE 02。

ENGINE 02 的 `choice_history` 每輪只有一個 `chosen_item_id`；如果同輪收藏多件，ENGINE 03 使用第一件作為該輪主選擇，但所有收藏仍會完整放在 `chosen_item_ids`。

## 執行

```powershell
$env:DEV_BYPASS_AUTH="true"
uvicorn backend.engine03_feedback.main:app --port 8003 --reload
pytest -q backend/engine03_feedback/tests
```
