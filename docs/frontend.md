# 前端

**負責人：待確認。** 這份原本是從 [hackathon-brief.md](hackathon-brief.md) 抄出來的骨架摘要（React + Vite 規劃），2026-09-19 main 上已經合併了實際蓋出來的前端原型（PR #4，"IntentWeave"），技術棧、畫面、串接狀態都跟原始規劃不一樣，這份文件已經改成如實反映現況＋記錄當天新增的三項規格待辦。正式負責人接手後仍然要把這裡展開成真正的規格（元件拆解、狀態管理方式），不要直接把這份當定案。

## 目前實際狀態（2026-09-19 盤點）

實際蓋出來的是 **Next.js 16 + React 19** 專案（`frontend/`，程式碼名稱 IntentWeave），不是原始規劃的 React + Vite——這件事本身要記住：CORS、Google OAuth 的 Authorized JavaScript origins 都要用 Next.js 的預設 port `3000`，不是 Vite 的 `5173`（兩個都已經加進後端 CORS 預設清單，見根目錄 CLAUDE.md）。

畫面／流程：`/login`（登入）→ `/onboarding`（偏好調查，三步）→ `/stylist`（主要對話＋推薦畫面）→ `/profile`、`/insights`。

**串接狀態（2026-09-19 盤點，這欄位隨時間推進會過期，跟 [docs/status.md](status.md) 對照著看）：**

| 功能 | 現況 |
|---|---|
| 登入（`/login`） | **真的接後端**：載入真正的 Google Identity Services、渲染官方登入按鈕，拿到 `credential` 後打 `POST /auth/google` 換真正的 `session_token`／`profile`（見 [`frontend/lib/services/auth.ts`](../frontend/lib/services/auth.ts)、[`frontend/components/intentweave/login-experience.tsx`](../frontend/components/intentweave/login-experience.tsx)）。已用真實 Google 帳號登入驗證過。 |
| 偏好調查（`/onboarding`） | **真的接後端且必填**：完成才會呼叫 `PUT /profile`（見 [`frontend/lib/services/onboarding.ts`](../frontend/lib/services/onboarding.ts)），已端到端驗證過（`data/users/<sub>.json` 真的寫入 `age_range`／`gender`／`style_preferences`／`contexts`）。Skip 按鈕已經拿掉。 |
| 推薦／檢索 | **~~前端還沒接~~ 已經真的接上**（2026-09-19 稍早這裡還寫著沒接，當天稍晚就接上了，這是舊版文件會過期的一個實例）：`frontend/lib/services/stylist.ts` 的 `fetchIntentTurn()`／`fetchRecommendation()`／`fetchStyleMe()` 真的打 `POST /intent`／`POST /recommend`／`POST /style-me`，Top Pick 用 `/style-me` 做真配對，不是兩分區各自最高分硬湊。 |
| 生成新單品／Design for Me | **新接上（dry-run 模式）**：`fetchConceptImage()` 打 `POST /concept-image`（ENGINE01 新增的端點，重用 `bff/images/concept.py::generate_concepts()`），按鈕按下去鎖住對話輸入框、顯示組好的 prompt 跟六格各自的變化描述。目前固定 `dry_run: true`（Hermes Agent 裝在 WSL2，Windows 側的 ENGINE01 還在接橋接，見 [docs/status.md](status.md)「生成模組」一節），還沒有真的生圖。 |
| 試穿／收藏／讚踩（`/stylist`） | **仍是 mock**，而且落差比規格描述的更具體——完整落差表見 [docs/status.md](status.md)「前端」一節（單品收藏/不喜歡的元件是死碼、收藏跟打分不會存檔、整套 Like/NotLike 沒鎖住兩區都穿）。這份落差已經傳給前端負責人許綺文去修，下面代辦 4 保留原始規格，不在這裡重複。另外 main 上還有一份 Hermes app 專用的平行前端 `web/`（幾乎是 `frontend/` 的複本，指向 `bff/`）跟一個 `/dressing-room` 頁面，UI 上明寫「Prototype preview」，跟這裡是同一批還沒做完的功能。 |
| 收藏小屋 | 完全沒有（`/dressing-room` 頁面雖然存在但是純 mock，見上面試穿那列），見代辦 5 那節的規格。 |

## 技術棧（更新：實際是 Next.js，不是原規劃的 Vite）

Next.js 16（App Router）＋ React 19，Tailwind v4 ＋ shadcn 元件。語音輸入用瀏覽器原生 Web Speech API（跟原規劃一致，免費、不用後端）；另外還有兩支 Next.js API route（`app/api/transcribe/`、`app/api/virtual-you/extract/`）直接呼叫 OpenAI 自己的 key，這兩支不經過 ENGINE01/02/03 的後端，是前端獨立的功能，不在這份介面契約管轄範圍內。

## 畫面／元件（實際畫面，比原規劃豐富）

- **登入**（`/login`）：見上面「目前實際狀態」。
- **偏好調查**（`/onboarding`）：年齡／性別、風格（複選）、日常情境（複選）三步，**2026-09-19 起必填，不可略過**。
- **主要對話畫面**（`/stylist`）：文字輸入＋語音輸入、推薦商品卡片（含 like/dislike 按鈕、Try On 按鈕）、虛擬形象區塊。對話／推薦／Design for Me 已經接上 ENGINE01 的真實資料（見上面「串接狀態」）；卡片上的 like/dislike／打分／Try On／虛擬形象整套讚踩這些互動仍是前端 mock，細節落差見 [docs/status.md](status.md)。
- **個人檔案**（`/profile`）、**Insights 儀表板**（`/insights`）：目前也都是 mock 資料。

## 溝通對象

ENGINE01 的 FastAPI 後端，走 REST。目前只有登入／onboarding 兩條路徑真的串上；`/intent`、推薦、回饋、生圖都還沒有前端呼叫。確切的 JSON 格式見 [interface-contract.md](interface-contract.md)（`IntentRequest`/`IntentResponse`、`RetrievalResult`、`FeedbackInput`）。後端網址走 `NEXT_PUBLIC_API_BASE_URL`（`frontend/.env.local`，本機預設 `http://localhost:8000`，這個檔案不進 git）。

## 代辦事項 3：兩分區展示＋生圖按鈕＋「幫你搭」＋對話鎖定（規格已定案，待實作）

2026-09-19 使用者確認的規格（原本討論過三分區，後來修正為兩分區）：

- 推薦結果固定分**兩區：上衣、下身**（不是三區）。每區最多 6 件，可左右切換；每件都能各自試穿／收藏／打分。後端 `POST /recommend` 已經照這個形狀做好，見 [interface-contract.md](interface-contract.md) 第 6 節——問套裝兩區都給，問單品只有查到的那區是「使用者要的」（`requested: true`），另一區也會有東西（依風格等資訊代猜的預設，`requested: false`），不會是空的；唯一例外是連身裙，下身區真的留空。
- 每一輪預設**只用 ENGINE02 的資料集做推薦**，不會自動生圖。
- 生圖是前端一個獨立按鈕，**使用者主動按下去才觸發**一次生成，而且**也跟資料庫一樣拆成上衣／下身兩張獨立圖片**（不是生成一張統一的套裝合照），各自可以試穿——細節見 [pinterest-and-generation.md](pinterest-and-generation.md)。
- **新增「我們幫你搭」按鈕**：**2026-09-19 修正——不能隨機挑，要有理由**。按下去要帶著使用者已經看到的一件商品（錨點）呼叫後端新端點 `POST /style-me`，回傳錨點另一區一件有理由的搭配建議（`complement.reason`，有 ENGINE02 真的算出來的相容性理由，或退回 LLM 生的理由，見 [interface-contract.md](interface-contract.md) 第 6a 節），**已實作**。前端要做的是：按鈕觸發呼叫、把回傳的 `complement` 顯示在虛擬形象另一區、`reason` 顯示出來讓使用者知道為什麼這樣搭（不是只顯示圖片）。
- 生圖進行中，對話輸入框要**鎖定**（不能繼續打字送出新的一句話），圖片生成完成、顯示出來之後才解鎖對話框。
- 這跟目前 `docs/interface-contract.md` §5 `RetrievalResult.concept_image` 原本假設「每輪推薦跟生成同時並行、一起回傳」的模型不一樣——原本的假設是 ENGINE02 跟生成模組同一輪並行執行；這次改成生圖是額外、獨立、使用者觸發的動作，呼叫時機要跟 `/intent`／`/recommend` 分開，需要生成模組負責人／前端負責人一起確認怎麼调整這個假設（例如生圖是不是應該是獨立的一支端點，而不是掛在同一輪的 `RetrievalResult` 裡）。

## 代辦事項 4：每張圖片的回饋（收藏／不喜歡／細項打分／試穿讚踩）（規格已定案，待實作）

2026-09-19 使用者確認的規格：

- **衣服卡片本身有三個獨立功能：收藏、不喜歡、細項打分**（不管是推薦商品還是生成概念圖，每一張圖片底下都有這三個）——三者都是選填，使用者可以完全不理它，三個動作互不影響（收藏了不代表沒有機會被打低分，反之亦然）。
- **使用者對某張圖片完全沒有任何動作，這張圖片就不能算進 ENGINE03 的權重調整**（不能把「沒表態」當成「中立」或「不喜歡」）。這條規則同步補進了 [engine03-feedback.md](engine03-feedback.md)。
- 每張圖片下方有一個 **Try On** 按鈕：按下去讓畫面右側的虛擬形象「穿上」這件衣服，再按一次脫掉。
- **2026-09-19 補充規則：LIKE IT／NOT FOR ME 只有虛擬形象穿上「一整套」才能按**——也就是上衣區＋下身區都試穿上了（不管是資料庫商品還是生圖，也不管是不是透過「幫你搭」湊出來的），這兩個按鈕才會出現；**只穿單一單品（只有上衣或只有下身）沒有這兩個按鈕**，因為「喜不喜歡這個穿搭」需要看到完整的一套才有意義，看單一單品判斷不出搭配好不好看。前端要在虛擬形象區塊追蹤目前上衣／下身兩區各自的試穿狀態，兩者都有才顯示這兩個按鈕。
- 目前 `backend/shared/schemas.py` 的 `ProductCard`／`FeedbackInput` 都還沒有能標示「這是對哪一張卡片的哪一種動作」的欄位——`FeedbackInput` 現在是整輪一份，不是逐卡片一份；tryon 的讚踩至少要帶 `top_product_id`＋`bottom_product_id` 兩個 id（一整套的兩個組成部分），不是單一 `product_id`。欄位草案見 [interface-contract.md](interface-contract.md) 新增的「待其他負責人落地的規格」一節，正式命名要跟 ENGINE02／ENGINE03／前端負責人一起確認再落地到 `schemas.py`。

## 代辦事項 5：收藏小屋（規格已定案，待實作）

2026-09-19 使用者確認的規格：

- 使用者收藏過的衣服（含推薦商品跟生成的概念圖）都會放進「收藏小屋」。
- 入口有兩個：user profile 頭像那邊放一個按鈕，或右側虛擬形象區塊也放一個按鈕。
- 收藏小屋裡的衣服要**依分類陳列**（衣服／褲子／外套……）。分類可以直接沿用 ENGINE02 既有的 `category`/`subcategory`／12→89 節點 taxonomy（見 [engine02-design.md](engine02-design.md) §3.8），資料庫裡的商品本來就有這個欄位；**生成出來的概念圖沒有分類標籤，這塊需要額外設計**（例如生圖的時候順便把 ENGINE01 抽出來的 `item_type` 存一份當分類，或用其他方式打標籤）——這是待確認事項，不是已經有答案。
- 使用者可以用虛擬形象試穿收藏小屋裡的任何一件，**同一個分類一次只能穿一件**（例如上衣穿了另一件上衣會替換掉，但可以同時穿一件上衣＋一件褲子）。

## 延伸功能／待討論想法（使用者口頭提出，還沒定案，正式負責人接手時要評估要不要做）

- **對話關聯圖，可以跳回之前的對話**：把整個對話過程畫成一張關聯圖／樹狀圖，讓使用者點回去某一輪重新出發。成本最高的一個——現在 `backend/engine01_intent/session_store.py` 只存「目前這一輪」的 `Intent`，沒有存每一輪的歷史快照，要做這個得先改後端資料模型（每輪都要存下來，不能只存最新的那份），前端還要另外做一個圖狀導覽 UI。要不要做要衡量兩天時間夠不夠，建議排在其他核心線都穩了之後再評估。
- **前端只顯示部分歷史，其餘收在後端**：比較便宜的版本——後端本來每一輪都會回傳資料，只是前端自己選擇要不要一次全部畫出來，例如舊的幾輪自動收合成一行摘要，點開才展開細節。不用動後端資料模型，單純是前端顯示策略，風險低，比較適合先做。
- **虛擬形象點擊穿脫（像奇跡暖暖）**：搭配已經定案的虛擬形象試穿功能（見 [pinterest-and-generation.md](pinterest-and-generation.md#虛擬形象試穿延伸功能2026-09-18-使用者口頭補充不在原始簡報或-hackathon-briefmd-裡)）——畫面右側放虛擬形象，點一下圖片切換「穿上生成的衣服」跟「沒穿」兩種狀態。這個很划算：只要生成模組那邊把試穿後的圖跟原本（沒穿／預設）的圖都準備好，前端純粹是點擊切換顯示哪一張圖，不需要額外呼叫後端，是低成本、高互動感的小巧思。**這個構想現在已經被代辦事項 4 的正式規格取代／具體化**（Try On 按鈕＋LIKE IT/NOT FOR ME），實作時直接參考代辦事項 4 那節即可。
