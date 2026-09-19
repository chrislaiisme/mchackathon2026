# agent/

Hermes Profile Distribution。安裝：`hermes profile install ./agent --alias`

負責線：線 4｜Runtime、回饋迴圈與打包（打包與設定）；各 skill 由對應的線負責（見下表）
對應功能：FR-011 Hermes Agent Application Packaging

## 內容

| 檔案 / 資料夾 | 用途 | 負責線 |
|---|---|---|
| `distribution.yaml` | 發佈資訊：名稱、版本、Hermes 版本需求、需要的環境變數 | 線 4 |
| `SOUL.md` | agent 身分與互動原則 | 線 4（全組確認） |
| `config.yaml` | profile 設定（不寫死 provider 與 model） | 線 4 |
| `skills/intent-extractor/` | 需求理解 | 線 1 |
| `skills/need-probe-planner/` | 需求探索出題 | 線 1 |
| `skills/recommendation-explainer/` | 推薦理由 | 線 2 |
| `skills/concept-image-director/` | 概念圖描述 | 線 3 |
| `skills/feedback-interpreter/` | 回饋解讀 | 線 4 |
| `skills/shared/` | 設計師詞表與屬性分類表（不是 skill，由 runtime 直接讀取） | 線 1 |
| `scripts/` | skill 會用到的輔助腳本 | 各 skill 負責線 |

## 規則

- 一支 skill 只負責一件工作。
- 不放絕對路徑、金鑰或個人資料；`.gitignore` 依官方 Profile Distribution 的排除清單。
- 暫不放 `mcp.json`：工具服務由 `bff/` 啟動時自行註冊；distribution 層的 `mcp.json` 格式待線 4 確認後再決定是否使用。
