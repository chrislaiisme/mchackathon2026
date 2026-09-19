# agent/scripts/

skill 會用到的輔助腳本，隨 distribution 一起發佈。

負責線：使用該腳本的 skill 所屬的線

## 六宮格生圖（線 3，`concept-image-director` skill 使用）

一次生一張多宮格、再切成單品卡片，而不是一件一件生。使用規則見
[`../skills/concept-image-director/SKILL.md`](../skills/concept-image-director/SKILL.md)，
實測數字與門檻推導見 [`../../evals/choice_images/README.md`](../../evals/choice_images/README.md)。

| 檔案 | 用途 | 跑在哪個環境 |
|---|---|---|
| `grid_common.py` | Intent → 每格關鍵字 → prompt，以及 manifest 的形狀 | 專案 venv |
| `generate_grid.py` | 組 prompt、呼叫生圖、寫出 grid.png 與 manifest.json | 專案 venv |
| `hermes_image.py` | 實際呼叫 Hermes 的 image_gen provider | **Hermes 自己的 venv** |
| `slice_grid.py` | 偵測 gutter、切成六格、auto-trim | 專案 venv |
| `check_cells.py` | 每格自動檢查（像素層必跑，語意層選配） | 專案 venv |

`hermes_image.py` 單獨跑在 Hermes 的虛擬環境，是因為 Hermes 的 plugin 跟專案的 engine02
依賴沒有交集；`generate_grid.py` 用子行程呼叫它，介面是 stdout 的 JSON——跟 ENGINE01
shell out 給 `codex exec` 是同一套做法。

依賴：`hermes` 已安裝且 `hermes auth` 登入過（吃 ChatGPT/Codex 訂閱額度，**不需要**
`OPENAI_API_KEY`）；`~/.hermes/config.yaml` 的 `image_gen.provider` 要是 `openai-codex`。
專案端只需要 Pillow 與 numpy。路徑可用 `HERMES_PYTHON`／`HERMES_AGENT_DIR` 覆寫。
