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

## 「AI 幫我搭」配對（`outfit-pairer` skill 使用）

從已經生好的六件上衣與六件下身裡挑出一組最搭的，附一句繁體中文理由。判斷規則見
[`../skills/outfit-pairer/SKILL.md`](../skills/outfit-pairer/SKILL.md)——腳本會把那份
SKILL.md 裡 `<!-- prompt:rules:start -->` 與 `<!-- prompt:rules:end -->` 之間的段落逐字讀進
prompt，所以規則改 skill 就好，不用改腳本。

| 檔案 | 用途 | 跑在哪個環境 |
|---|---|---|
| `pair_outfit.py` | 讀 `{intent, tops, bottoms}`，呼叫 `codex exec` 挑一組，印出 `{top_id, bottom_id, reason, source}` | 專案 venv |

介面一樣是 stdout 最後一行的 JSON：

```
python agent/scripts/pair_outfit.py --input pair_input.json          # 真的挑，實測 12–14 秒
python agent/scripts/pair_outfit.py --input pair_input.json --dry-run  # 只印 prompt，不花額度
```

codex 失敗／逾時（預設 45 秒）／回傳不合法／挑了清單以外的 id，一律退回 `tops[0]` 與
`bottoms[0]`、理由用 keywords 拼、`source` 標成 `fallback`，**退出碼仍是 0**——現場 demo
不能因為 codex 慢就整條壞掉，呼叫端看 `source` 就知道這組是挑出來的還是退場來的。
真正配不出來的情況（`tops` 或 `bottoms` 是空的、輸入不是合法 JSON）才用非零退出碼。

依賴跟 ENGINE01 一樣：`codex` CLI 裝好並 `codex login` 過（吃 ChatGPT/Codex 訂閱額度，
**不需要** `OPENAI_API_KEY`）。`CODEX_BIN`／`CODEX_MODEL`／`CODEX_REASONING_EFFORT`
兩邊共用；逾時另外看 `PAIR_OUTFIT_TIMEOUT`（預設 45 秒，ENGINE01 的
`CODEX_TIMEOUT_SECONDS` 跟這支無關），但只在手動跑且沒帶 `--timeout` 時才算數——
透過 BFF 呼叫時會被蓋掉，見下面。

輸入的 `keywords` 兩種形狀都吃：manifest 的 `{欄位: 中文值}` dict，或前端
`FashionRecommendation.attributes` 那種字串陣列。dict 會連欄位名一起餵給模型
（`fit=寬鬆` 比單獨一個「寬鬆」分得出講的是版型還是材質），拿得到 dict 就給 dict。

**呼叫端**：前端「AI 幫我搭」按鈕 → 生圖 BFF（8100）`POST /outfit-pair` →
`bff/images/outfit_pair.py` 用子行程跑這支，手法跟 `bff/images/concept.py` 叫
`generate_grid.py` 一樣。請求是 `{session_id?, intent, tops, bottoms}`；`tops`／`bottoms`
空的或缺 id 由 pydantic 擋成 422，其餘一律 200，回傳就是腳本那四個欄位原樣透出。

BFF 會把 `OUTFIT_PAIR_TIMEOUT`（預設 60 秒）明確當 `--timeout` 傳進來，所以走按鈕時
腳本自己的 `PAIR_OUTFIT_TIMEOUT` **不生效**，兩個都設以 `OUTFIT_PAIR_TIMEOUT` 為準；
BFF 外層 subprocess 的逾時再多留 10 秒，是讓腳本來得及自己印出退場那行 JSON。
BFF 只在腳本**跑不起來**（找不到、逾時到來不及印退場、stdout 最後一行不是 JSON）
或回傳的 id 不在這次請求的清單裡時才再墊一層退場，一樣 `tops[0]`／`bottoms[0]`、
`source: fallback`；正常情況腳本自己的退場就已經把 codex 的問題吃掉了，BFF 這層
看不出差異。
