# 現況總覽

單一一份「各模組現在做到哪裡、還缺什麼」的總覽表，給接手的人或隊友一眼看懂全貌用。細節規格仍然分別在各自的 `docs/*.md`，這裡不重複寫規格，只記「現況」跟「下一步」。內容會過期，每次大改動後應該回來更新一次，不是寫一次就不管。

最後更新：2026-09-19（黑客松比賽日）。

## ENGINE01（需求理解＋登入）—— 負責人：這個工作目錄的擁有者

**今天做完的事：**
- 前端「我們幫你推」真的接上 ENGINE01／ENGINE02（`POST /recommend` → ENGINE02 的 `POST /intent/rank`／`POST /visual-search`；`POST /style-me` 真配對）。
- 真人 demo 抓到並修好 3 個 bug：ENGINE02_PUBLIC_BASE 少 `/engine02` 前綴、Pinterest 參考圖蓋掉文字意圖、gender 詞彙英中對不上（PR [#15](https://github.com/chrislaiisme/mchackathon2026/pull/15)，還沒 merge 進 main）。
- 澄清問題（clarifying questions）修正：ENGINE01 一輪如果同時缺好幾個核心欄位，後端本來就會一次回好幾題，但前端 `adaptToClarifyingMessage()` 只轉第一題、其餘題目被丟掉——已修成前端本地依序問完一批題目、答完才送出下一次 `/intent`，不會漏問。
- 新增 `POST /concept-image`（重用 `bff/images/concept.py::generate_concepts()`），前端「Design for Me」按鈕已經接上（目前 `dry_run: true`，只組 prompt 不花額度）。

**還缺什麼：**
- Hermes Agent 生圖真正接通（見下面「生成模組」）。
- 推薦理由目前是 ENGINE02 的樣板句，會露出內部分數／備註（例如「整體風格和你描述的相近（+1.44）」），需要改寫成自然語句（見下面「推薦理由品質」）。
- ENGINE03 merge 之後，`engine02_client.py::intent_rank()` 要補 `feedback`／`prev_intent` 兩個參數，把 ENGINE03 的回饋帶進每一輪 ENGINE02 排序——ENGINE02 那一側已經就緒，見下面「ENGINE03」一節。
- PR #15（gender 修正）還沒 merge 進 main。

## ENGINE02（檢索與排序）—— 負責人：Evan-Jiamg（明志）

**現況：** 已實作、有測試（258 項），目前明志在 update 中，細節這份文件沒有第一手資訊，需要跟他本人確認最新進度。

**跟這次調查相關、值得留意的兩個既有能力（本來就有，只是還沒被用到）：**
- `POST /intent/rank`：已經支援同時吃「這輪重新抽出來的 intent」＋「`feedback` 欄位（含 ENGINE03 的 op-based `FeedbackRound`會自動套用）」＋「`prev_intent`（上一輪意圖，供對照評分）」——ENGINE01 目前只送了 `intent`，`feedback`／`prev_intent` 還沒接（見上面「ENGINE01 還缺什麼」）。
- `POST /handshake`：`engine02/handshake.py::apply_round()` 的 HTTP 版，單獨把一輪 ENGINE03 回饋套進 request，回傳套用後的 `next_request` 跟 ledger——`/intent/rank` 內部就是呼叫同一支函式，两支端點都可以用，目前都沒有任何呼叫端在用。

## ENGINE03（回饋 → 權重／意圖更新）—— 負責人：文件裡還沒指定，確定後補上

**現況：三套互不相容的實作同時存在，這是「有點混亂」的真正原因，不是分支衝突：**

1. `backend/shared/schemas.py` 的 `FeedbackInput`——ENGINE01 最早定的介面契約，`attribute_scores`／`selected_option_id`，**沒有「不喜歡」的欄位**。
2. `bff/feedback/main.py`（已經在 main 上，Hermes app 技術棧 `bff/main.py` 的 `/feedback` 現在打的就是這支，port 8003）——把讚／倒讚轉成 `FeedbackInput`。**它自己的 docstring 承認限制**：倒讚只進本地帳本，不會傳給 ENGINE02。這套現在能跑，但做不到「不喜歡」這個明確需求。
3. `backend/engine03_feedback/`（PR [#14](https://github.com/chrislaiisme/mchackathon2026/pull/14)，分支 `engine3-feadback-new`，尚未 merge）——決定性（不吃 LLM）、op-based（`chosen_item_id`／`rejected_item_ids`／`excluded_item_ids`／`anchor_item_ids`／attribute scores→設計軸調整），**這套才有「不喜歡」「永久排除」的概念**，跟 ENGINE02 的 `apply_round()`／`/handshake` 是同一套 op 契約，剛好對得上。

`origin/engine03-feedback`（另一個名字很像的分支）只是 PR #14 rebase 前的舊版本，不是第四套分歧設計，不用另外處理。用 `git merge-tree` 確認過 PR #14 跟目前 main／engine01-intent 完全不衝突。

**建議的下一步順序（先 merge、再接線，理由跟細節見 `docs/engine03-feedback.md`）：**
1. Merge PR #14（風險低，不衝突，有 7 項測試）。
2. ENGINE01 新增呼叫 `backend/engine03_feedback`（port 8003）的 client，把結構化回饋（收藏／不喜歡／分項打分／整套 Like-NotLike）送過去、拿回 `FeedbackRound`。
3. `session_store.py` 存住「上一輪的 Engine02Request/Response」＋「ENGINE03 回傳的 FeedbackRound」。
4. `engine02_client.py::intent_rank()` 補 `feedback`／`prev_intent` 兩個參數。
5. `bff/feedback/main.py` 只有團隊真的要切到 `bff/`／Hermes app 技術棧當 demo 主線時才需要處理，目前不影響現在在跑的 demo 架構（前端直打 ENGINE01、ENGINE01 直打 ENGINE02），可以先不管。

這是跨 ENGINE02／ENGINE03／前端三邊的整合決定，建議先讓三邊負責人看過這個結論再動手。

## 前端（IntentWeave，Next.js 16 + React 19）—— 負責人：許綺文

**現況：** 登入／onboarding 已接上真後端；推薦（Top Pick／Try More）已接上真後端；「Design for Me」已接上真後端（dry-run 模式）。

**已知落差（已經傳給許綺文，不是待認領的開放項目，這裡只是記錄現況方便對照修完了沒）：**

| 互動 | 現況 |
|---|---|
| 套裝收藏／不喜歡 | 部分能用，但用不同機制存：不喜歡存 localStorage，收藏只存在 React state，重新整理頁面就消失 |
| 單品收藏／不喜歡 | 唯一同時有讚＋倒讚的元件 `RecommendationCard` 是死碼（吃的 `message.recommendations` 陣列從未被填值），畫面上實際渲染的 `RecommendationCarousel` 只有倒讚沒有讚；單品收藏／打分是純 React state，不會存檔 |
| 打分（現在單一 1-5 星，之後要改分項） | 現在的單一星等能動但不存檔；分項打分（風格／設計…）完全沒有對應資料結構，是全新功能 |
| Try On | 完整實作，但純前端視覺模擬（CSS 疊圖），不是真的合成，也沒打後端 |
| 虛擬人物「整套穿上才能 Like/Not Like」 | 規則目前沒被強制：只要穿任一件（不用兩區都穿）就會顯示按鈕；記錄的也只是「最後穿上的那一件」id，不是上衣＋下身兩個 id |

**全部 5 項，目前沒有任何一項會打 `/feedback`**——這是等 ENGINE03 merge、ENGINE01 接上之後，前端也要跟著改的部分。

## 生成模組（概念圖／Design for Me）—— 負責人：Tony（`agent/scripts/generate_grid.py` 作者）

**現況：** Hermes Agent 裝在這台機器的 WSL2（Ubuntu），不在 Windows 側；程式碼假設的安裝路徑（`~/.hermes/hermes-agent/venv`）跟這台機器實際的安裝方式（`/usr/local/lib/hermes-agent/venv`，root 模式安裝）不一樣。真正的障礙是 Windows 側的 ENGINE01 沒辦法直接跨進 WSL2 執行 Hermes 的 venv，今天要加一段 Windows→WSL2 的橋接（`platform.system()` 判斷式包住，只在 Windows 上生效，不影響 Tony 原本在 Linux／WSL2 上的用法）。

**還缺什麼：**
- 橋接程式碼驗證通過、`dry_run` 開關關掉、真的生一次圖確認整條管線動得起來。
- 生圖出來的理由／`varied_label` 之後也可以套用跟推薦理由一樣的自然語句改寫（見下面）。

## 推薦理由品質

現況：ENGINE02 沒有 `OPENAI_API_KEY`，推薦理由預設走樣板句，會露出內部細節（分數片段如「+1.44」、內部備註如「為了有足夠結果，放寬了 season 條件」），不是使用者想看到的推薦理由。

解法：ENGINE01 已經有現成、零成本的機制——`style_me.py` 的「幫你搭」理由已經在用 `llm_client.generate_freeform_text()`（`codex exec`）把樣板句改寫成自然語句，`/recommend` 還沒套用同一招。計畫是在 `/recommend` 回傳前批次（一次 `codex exec` 呼叫處理整輪所有理由，不逐卡呼叫）改寫，避免一輪要等十幾次 8-17 秒的呼叫。

## 文件本身的已知問題

- `CLAUDE.md` 連到 `docs/migration-to-hermes-app.md` 的連結在這個分支（`engine01-intent`）上是死的，那份文件只存在於 `integration/hermes-app` 分支。
- `docs/engine03-feedback.md` 原本的「發現分歧」警告區塊只提到最早、已經被 rebase 掉的 `origin/engine03-feedback`，沒提到後來的 PR #14 或已經在 main 上的 `bff/feedback/main.py`——已經在這次更新裡重寫。
- `docs/research/integration-map.md`（ENGINE02 團隊寫的）內容還算準，值得直接參考，這次沒有重寫它。
