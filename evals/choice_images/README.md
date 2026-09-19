# evals/choice_images/

負責線：線 3｜概念圖與選項圖
對應功能：FR-010 中的選項圖檢查通過率

## 內容

- 先前的生圖可行性驗證結果（褲口、腰線）：比賽前由線 3 整理放入
- 每種變化重複生成多次的檢查通過率
- 用已知結果校準選項圖自動檢查（線 1 可支援）

## Hermes OpenAI OAuth 實測（2026-09-16）

使用 Hermes Agent v0.21.2 的 `image_gen/openai-codex` plugin，以 ChatGPT/Codex 訂閱帳戶 OAuth 產圖，不使用 `OPENAI_API_KEY`。

| 測試 | 模型 | 耗時 | 結果 |
|---|---|---:|---|
| text-to-image：Sweet Lolita JSK 商品照 | `gpt-image-2-medium` | 39.0 秒 | 通過；1145 × 1374 PNG |
| image-to-image：只把主布由粉紅改成薰衣草紫 | `gpt-image-2-medium` | 39.2 秒 | 通過；構圖、蕾絲、蝴蝶結、袖型、領型與三層裙結構均保留 |

測試素材：

- `hermes_openai_codex_test_prompt.txt`
- `hermes_openai_codex_edit_prompt.txt`
- `hermes_openai_codex_sweet_lolita.png`
- `hermes_openai_codex_sweet_lolita_lavender.png`

Hermes 的 `openai-codex` provider 只會在收到 `image_source=final` 時保存並回傳成功結果；progressive partial 會被拒絕，不會成為上述成品。

## Pinterest → Hermes 實測（2026-09-17）

Pinterest Trial app 透過 `/v5/boards/{board_id}/pins` 成功讀取公開圖版 [IntentWeave References](https://www.pinterest.com/pinyucs15/intentweave-references/) 的 3 張參考 Pin。下載後的圖片只作為高階輪廓、層次與配色參考，再交給 Hermes `openai-codex` OAuth provider 生成全新人物與場景；沒有使用 `OPENAI_API_KEY`。

| 測試 | 模型 | 耗時 | 結果 |
|---|---|---:|---|
| Pinterest reference-to-image：中性極簡街頭穿搭 | `gpt-image-2-medium` | 44 秒 | 通過；1024 × 1536 PNG；新人物、新姿勢、新場景，無品牌、標誌與可讀文字 |

測試素材：

- `hermes_pinterest_reference_prompt.txt`
- `hermes_pinterest_reference_streetwear.png`

下載的 Pinterest 原始參考圖保存在被 Git 忽略的 `data/pinterest_trends/`，不提交到版本庫。
