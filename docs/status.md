# 現況總覽

單一一份「各模組現在做到哪裡、還缺什麼」的總覽表，給接手的人或隊友一眼看懂全貌用。細節規格仍然分別在各自的 `docs/*.md`，這裡不重複寫規格，只記「現況」跟「下一步」。內容會過期，每次大改動後應該回來更新一次，不是寫一次就不管。

最後更新：2026-09-20。**這次更新的主因：上一版（2026-09-19）寫的「ENGINE03 三套契約並存、PR #14 還沒 merge、前端全部沒有打 `/feedback`」已經是歷史——回頭讀程式碼＋`git log` 才發現這中間已經完成並 merge，文件沒跟上。這是一個提醒：這份文件本身也會過期，發現內容跟程式碼對不上時，永遠以程式碼為準。**

## ENGINE01（需求理解＋登入）—— 負責人：這個工作目錄的擁有者

**今天做完的事：**
- 前端「我們幫你推」真的接上 ENGINE01／ENGINE02（`POST /recommend` → ENGINE02 的 `POST /intent/rank`／`POST /visual-search`；`POST /style-me` 真配對）。
- 真人 demo 抓到並修好 3 個 bug：ENGINE02_PUBLIC_BASE 少 `/engine02` 前綴、Pinterest 參考圖蓋掉文字意圖、gender 詞彙英中對不上（PR [#15](https://github.com/chrislaiisme/mchackathon2026/pull/15)，還沒 merge 進 main）。
- 澄清問題（clarifying questions）修正：ENGINE01 一輪如果同時缺好幾個核心欄位，後端本來就會一次回好幾題，但前端 `adaptToClarifyingMessage()` 只轉第一題、其餘題目被丟掉——已修成前端本地依序問完一批題目、答完才送出下一次 `/intent`，不會漏問。
- 新增 `POST /concept-image`（重用 `bff/images/concept.py::generate_concepts()`）＋ Windows→WSL2 的 Hermes 橋接，**已驗證真的能生圖**（Hermes 裝在這台機器的 WSL2，`agent/scripts/generate_grid.py` 加了跨界呼叫）。單一品項＋整套（`outfit_requested`）兩種情境都做了：整套會比照 `/recommend` 的兩分區模式，上衣／下身各生一組六格（**平行執行，已實測 35 秒完成兩組，沒有撞到 WSL2/Hermes session 衝突**），組一句 Top Pick 理由，前端重用既有的 Top Pick／Try More UI 殼顯示。
- 推薦理由自然語句改寫：新增 `llm_client.rewrite_recommendation_reasons()`，批次（一次 `codex exec`）把 `/recommend` 回傳的樣板句理由改寫成自然語句，已驗證「整體風格和你描述的相近（+1.44）」→「風格貼近經典商業套裝」這種效果。
- Merge 了前端剛推的虛擬試穿後端（`backend/virtual_you/`，許綺文寫的，用跟 ENGINE01 同一種 `codex exec` 零成本機制），裝好新依賴、啟動測試中（見下面「虛擬穿衣」）。

**還缺什麼（2026-09-20 更新）：**
- ~~ENGINE03 merge 之後，`engine02_client.py::intent_rank()` 要補 `feedback`／`prev_intent` 兩個參數~~——**已完成**，見下面「ENGINE03」一節，`build_zoned_recommendation()` 現在會把 `feedback`／`prev_intent` 傳給每一次 `intent_rank()` 呼叫。
- PR #15（gender 修正）是否已經 merge 進 main 需要重新核對一次，這份文件沒有第一手資訊。
- ~~生成圖的收藏／不喜歡／打分——設計草案，還沒實作~~——**已實作**，見下面「ENGINE03」一節（`source: "generated"` 分流、`db01cf3`）。虛擬形象區塊「整套穿上才能 Like/Not Like」的前端強制規則是否已經真的鎖住兩區都穿才顯示按鈕，需要現場核對（這是原本傳給許綺文的落差清單項目，見「前端」一節）。

## ENGINE02（檢索與排序）—— 負責人：Evan-Jiamg（明志）

**現況：** 已實作、有測試（258 項），目前明志在 update 中，細節這份文件沒有第一手資訊，需要跟他本人確認最新進度。

**跟這次調查相關、值得留意的兩個既有能力（本來就有，只是還沒被用到）：**
- `POST /intent/rank`：已經支援同時吃「這輪重新抽出來的 intent」＋「`feedback` 欄位（含 ENGINE03 的 op-based `FeedbackRound`會自動套用）」＋「`prev_intent`（上一輪意圖，供對照評分）」——ENGINE01 目前只送了 `intent`，`feedback`／`prev_intent` 還沒接（見上面「ENGINE01 還缺什麼」）。
- `POST /handshake`：`engine02/handshake.py::apply_round()` 的 HTTP 版，單獨把一輪 ENGINE03 回饋套進 request，回傳套用後的 `next_request` 跟 ledger——`/intent/rank` 內部就是呼叫同一支函式，两支端點都可以用，目前都沒有任何呼叫端在用。

## ENGINE03（回饋 → 權重／意圖更新）—— 已實作並接通，前後端都在跑

**2026-09-20 更新：上一版寫的「三套契約並存、PR #14 還沒 merge」已經是歷史。** 目前採用的就是原本 PR #14 那一套決定性、op-based 設計，程式碼在 `backend/engine03_feedback/`（`contracts.py`／`service.py`／`attributes.py`＋測試），純規則式分數門檻映射、不吃 LLM、不用 `OPENAI_API_KEY`。三套契約並存的歷史脈絡（`FeedbackInput`／`bff/feedback/main.py`／`backend/engine03_feedback/`）留在 `docs/engine03-feedback.md` 當紀錄，正式規格請直接看 `backend/engine03_feedback/README.md`，不要照舊版提案動手。

**現在整條迴圈長這樣：**
- 前端 `frontend/lib/services/stylist.ts::submitFeedback()`／`adaptPreferencesToFeedbackRequest()` 把使用者這輪的收藏／不喜歡／分項打分／整套喜歡（統一存在 `preferenceService`，見「前端」一節）組成 `POST /feedback` 的形狀，在 `stylist-experience.tsx::submitPendingRoundFeedback()` 裡於下一輪對話送出前自動呼叫——不是使用者要另外按一個「送出回饋」按鈕。
- ENGINE01 的 `POST /feedback`（`backend/engine01_intent/main.py`）驗證這些 id 真的是這輪展示過的商品（`state.shown_item_ids`／`state.shown_generated_item_ids`，不信任瀏覽器自己講的），依 `source: "catalog"|"generated"` 分流：`catalog` 直接用 `item_id`；`generated`（Design for Me 生成的單品）改用 session 裡由生成 manifest 建立、伺服器端保存的 `design_attributes`（瀏覽器傳來的內容不採信）。接著透過 `engine03_client.py` 呼叫 `backend/engine03_feedback`（port 8003）。
- `db01cf3 feat(engine3): map generated feedback to design weights`：生成圖回饋映射進設計軸權重的機制已經實作，不是草案。
- `54869d4 feat(engine3): support outfit favorite feedback`：整套（outfit-level）收藏回饋也已支援。
- `7f2a57a feat(engine3): aggregate four-round feedback window`：ENGINE03 每次會一起看「前三輪＋本輪」，最多四輪視窗內的評分取平均。
- 回傳的 `engine02_feedback` 存進 `state.pending_engine02_feedback`，下一輪 `POST /recommend` 呼叫 `engine02_client.intent_rank()` 時當 `feedback` 參數往下傳給 ENGINE02——**這一步已經接通**（上一版文件寫「還缺這段」是舊資訊）。

**仍待確認／可以再做的**：
- `docs/engine03-feedback.md` 原本草擬的 `target_level`／`items[].source`／`design_attributes` 欄位命名，跟 `backend/engine03_feedback/` 實際落地的欄位是否逐字一致——這次盤點確認邏輯（`source: catalog|generated` 分流、outfit 拆兩筆）已經照草案的方向做了，但沒有逐欄位比對命名，接手的人如果要改欄位，先讀 `backend/engine03_feedback/contracts.py` 為準，不要照舊草案的 JSON 範例直接套。
- 「符合度分數」（`match_score`）現場展示——`docs/engine03-feedback.md` 提過的「畫面上秀出符合度從 62% → 89%」這種量化呈現，目前 `ZoneSlate.match_score` 有欄位，但前端有沒有真的把這個數字在兩輪之間並排顯示出來給評審看，需要現場核對一次。

## 前端（IntentWeave，Next.js 16 + React 19）—— 負責人：許綺文

**現況（2026-09-20 重新核對）：** 登入／onboarding、推薦（Top Pick／Try More）、「Design for Me」生圖都已接上真後端。**上一版寫的「收藏／不喜歡／打分／Try On 全部是 mock、沒有任何一項會打 `/feedback`」已經過時**——實際讀 `frontend/lib/services/preferences.ts`／`stylist-experience.tsx` 之後確認：

| 互動 | 現況 |
|---|---|
| 收藏／不喜歡／分項打分／整套喜歡 | 已經統一收進 `preferenceService`（`toggleSavedItem`／`toggleDislikedItem`／`setDimensionRating`／`toggleSavedOutfitItems`），單一資料來源，不再是「收藏在 React state、不喜歡在 localStorage」各存各的舊問題。這份 `preferenceState` 會在 `submitPendingRoundFeedback()` 裡於下一輪對話送出前**自動**轉成 `POST /feedback` 的形狀送給 ENGINE01→ENGINE03，不需要使用者另外按送出——見上面「ENGINE03」一節。**持久化方式是瀏覽器 `localStorage`（依登入的使用者 id 分開存），不是後端資料庫**：換瀏覽器、清瀏覽器資料、或用無痕視窗會讓偏好重置，demo 前如果要確保「上一輪回饋真的影響下一輪」的效果看得到，同一場 demo 要全程用同一個瀏覽器設定檔。 |
| Try On（虛擬形象試穿） | `virtualYouService.extractPerson()` 會呼叫 `frontend/app/api/virtual-you/extract`，該路由在設定好 `PERSON_EXTRACTION_SERVICE_URL`（`backend/virtual_you/` 的 `/extract`）時會真的去背，沒設定會退回內建的 `provider: "mock"` 路徑（原樣回傳照片）；試穿合成的細節（`/try-on` 這條路的即時狀態、CSS 疊圖跟真實合成兩者現在的分工）這份文件沒有第一手驗證，demo 前建議直接跟許綺文核對一次現況，不要照這裡的敘述當定案。 |
| 虛擬人物「整套穿上才能 Like/Not Like」 | 上一版記錄的落差（只穿一件就會顯示按鈕、只記錄最後一件的 id）目前是否已經修正，這份文件沒有重新核對，需要現場確認。 |

上面第一項（收藏／不喜歡／打分／整套喜歡 → `/feedback`）是這次盤點確認**已經真的接通並在跑**的部分；後兩項標「沒有第一手驗證」的，請照實跟許綺文核對，不要假設已經修好。

## 生成模組（概念圖／Design for Me）—— 負責人：Tony（`agent/scripts/generate_grid.py` 作者）

**現況：已接通並驗證過。** Hermes Agent 裝在這台機器的 WSL2（Ubuntu），程式碼假設的安裝路徑（`~/.hermes/hermes-agent/venv`）跟這台機器實際的安裝方式（`/usr/local/lib/hermes-agent/venv`，root 模式安裝）不一樣；`agent/scripts/generate_grid.py` 加了 Windows→WSL2 的橋接（`platform.system()` 判斷式包住，只在 Windows 上生效，Tony 原本在 Linux／WSL2 上的用法不受影響）。Hermes 的 `openai-codex` image_gen plugin 原本沒啟用，已經 `hermes plugins enable openai-codex` + `hermes config set image_gen.provider openai-codex`（這是這台機器 Hermes 自己的設定，不在 git 裡）。

單一品項、整套（上衣＋下身各六格、平行執行）兩種情境都實測生過真圖，六格版型/顏色都正確發散，圖片品質良好。

**還缺什麼：**
- 生圖出來的理由／`varied_label` 之後也可以套用跟推薦理由一樣的自然語句改寫（技術上可以直接做，這次沒排進去）。
- 生成圖的收藏／不喜歡／打分／Try On——見上面 ENGINE01「還缺什麼」跟 `docs/engine03-feedback.md`。

## 虛擬穿衣（Virtual You / Create You）—— 負責人：許綺文

**現況：** 全新、獨立的 FastAPI 服務 `backend/virtual_you/`（`POST /extract` 去背、`POST /try-on` 合成試穿圖），用跟 ENGINE01 同一種零成本機制（`codex exec` 的 `$imagegen`，不需要 `OPENAI_API_KEY`，直接在 Windows 上跑、不用像生圖那樣跨 WSL2）。已經 merge 進 `engine01-intent`、裝好新依賴（`pillow`／`rembg`／`onnxruntime`）、啟動在 port 8081。

**卡住的地方**：`POST /extract`／`/try-on` 第一次呼叫時，`rembg` 的去背模型（`birefnet-portrait`，973MB）要從 GitHub 下載到本機快取——**這台機器現在的下載速度只有約 150kB/s，下完可能要 1-2 小時**，不是程式碼問題，是網路速度問題。今天稍早已經先觸發下載讓它在背景跑，demo 前務必先確認這個模型已經下載完成、warm up 過一次，不然 demo 現場第一次呼叫會卡在下載而不是在生成——建議提早（不要等到 demo 前）用一張測試照打一次 `/extract` 確認模型已經快取好。

**還缺什麼：**
- 等模型下載完成後，實際跑一次 `/try-on` 端到端驗證（目前卡在下載，還沒驗證過真的試穿合成效果）。
- 前端 `.env.local` 要補 `PERSON_EXTRACTION_SERVICE_URL`／`VIRTUAL_TRY_ON_SERVICE_URL` 才會真的打這支服務，不然前端會自動退回 mock（`provider: "mock"`，回傳原圖）。

## 推薦理由品質

**已完成。** 現況（改前）：ENGINE02 沒有 `OPENAI_API_KEY`，推薦理由預設走樣板句，會露出內部細節（分數片段如「+1.44」、內部備註如「為了有足夠結果，放寬了 season 條件」）。

解法：新增 `llm_client.rewrite_recommendation_reasons()`，批次（一次 `codex exec` 呼叫處理整輪所有理由，不逐卡呼叫）把樣板句改寫成自然語句，`main.py` 的 `/recommend` 回傳前套用，失敗會原樣退回樣板句不擋主流程。已實測：「整體風格和你描述的相近（+1.44）」→「風格貼近經典商業套裝」。

## 文件本身的已知問題

- `CLAUDE.md` 連到 `docs/migration-to-hermes-app.md` 的連結在這個分支（`engine01-intent`）上是死的，那份文件只存在於 `integration/hermes-app` 分支。
- `docs/engine03-feedback.md` 原本的「三套契約並存」警告區塊已經是舊聞（ENGINE03 早就 merge 並接通），2026-09-20 已經重寫成「現況已完成，方案 1／2 是歷史紀錄」。
- `docs/research/integration-map.md`（ENGINE02 團隊寫的）內容還算準，值得直接參考，這次沒有重寫它。
- **2026-09-20 教訓：這份文件（跟 `docs/engine03-feedback.md`）曾經連續好幾天沒跟上程式碼的實際進度**，寫著「還沒 merge」「還是 mock」的東西其實早就做完了。以後改完重要功能，養成「回來補一行到這份文件」的習慣，不要等到隔了好幾個 commit 才發現落差。

## Repo 整理

repo 裡有哪些資料夾／文件是死碼、跟現場 demo 無關的占位、或應該同一份卻已經分岔的重複目錄，完整盤點見 **[docs/repo-cleanup-audit.md](repo-cleanup-audit.md)**（2026-09-20 新增）。目前只列清單，沒有動手刪除任何東西。

## 一鍵啟動 / 遠端 demo

- 跨平台啟動／關閉／重啟單一服務的方式：見根目錄 README.md「Running the services」一節（`python scripts/dev_services.py`，Windows 也可以繼續用既有的 `scripts/start-demo.ps1`）。
- 想讓評審用自己的電腦連上這台機器跑的 demo：見根目錄 README.md「Demo it remotely」一節與 [docs/remote-demo-tunnel.md](remote-demo-tunnel.md)（Cloudflare Quick Tunnel，含 Google OAuth 網域允許清單這個容易漏掉的手動步驟）。
