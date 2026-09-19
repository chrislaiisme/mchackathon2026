# 推薦理由的「AI 口吻」：用團隊的 ChatGPT 帳號改寫（Codex CLI）

## 現在的理由怎麼來的

1. 排序是可加總的，每張卡的分數＝各項貢獻相加。
2. 撐得住這個名次的最少幾項（最小充分集合）被寫成**模板句**，例如
   「中秋節倒數 4 天｜中秋烤肉不怕髒：深色、好活動的休閒穿搭（+0.55）」。
3. 同時產生這些句子背後的**事實**（`reason_facts`：標籤、方向、貢獻值……）。

沒接任何 LLM 時，畫面顯示的就是模板句，永遠可用、永遠正確。

## 加上 AI 口吻

`/rank` 仍然即時回傳模板句（約 13 ms）。前端拿到卡片後，**另外**呼叫 `POST /explain/rewrite`，
由團隊的 ChatGPT 帳號透過 Codex CLI 把整批卡片改寫成口語句子，回來後把卡片上的文字換掉。

實測（H&M 商品庫、台北、機車通勤、中秋節）：

| 模板句 | AI 改寫後 |
|---|---|
| 中秋節就是今天｜中秋烤肉不怕髒：深色、好活動的休閒穿搭（+0.62）；機車族出門 → 擋風外套 + 合身版型…… | 今天中秋烤肉，推薦你朝深色、好活動的休閒穿搭挑選，騎車記得搭擋風外套、穿合身些，先收起飄逸長裙。 |

- 一批 4–5 張卡約 **13–20 秒**（ChatGPT 帳號走 Codex 的實測），所以**不能**放在 `/rank` 裡同步等。
- 同樣的卡第二次是 **0 秒**（快取，`data/cache/rewrites.json`）。demo 前把會用到的情境跑一遍，現場就全是快取。
- **每一句都會做事實查核**：出現卡片事實裡沒有的數字或商品庫詞彙（顏色、場合……）、超過 80 字，這一句就作廢，
  那張卡保留模板句，回應裡寫明原因。Codex 沒登入、逾時、失敗，全部卡片保留模板句，服務不會出錯。
- 每張卡回傳 `source`：`codex`（剛改寫）、`cache`（快取）、`template`（沿用模板）。

## 怎麼開

在跑 ENGINE 02 的那台電腦：

```bash
npm i -g @openai/codex        # 安裝 Codex CLI
codex login                   # 用團隊的 ChatGPT 帳號登入（選 Sign in with ChatGPT）
ENGINE02_REWRITER=codex python -m uvicorn engine02.api:app --port 8002
curl localhost:8002/explain/status     # {"backend":"codex","available":true,"detail":"Logged in using ChatGPT"}
```

呼叫次數會算在該 ChatGPT 方案的用量裡。可調的環境變數：`ENGINE02_CODEX_MODEL`、`ENGINE02_CODEX_EFFORT`（預設 low）、
`ENGINE02_CODEX_TIMEOUT`（預設 90 秒）、`ENGINE02_REWRITE_CACHE`、`ENGINE02_CODEX_BIN`。

## 前端怎麼接

```
1. POST /rank（或 /intent/rank、/retrieve）→ 立刻畫出卡片，理由用模板句
2. 背景呼叫 POST /explain/rewrite  {"session_id": <同一個 session>}
      /retrieve 的回應裡有 engine02.rewrite.session_id 與 endpoint，直接拿來用
      （/retrieve 服務上路徑是 /engine02/explain/rewrite）
3. 回來後逐張把 text 換上；source 為 template 的不用換
```

也可以不靠 session，直接送卡片：`{"session_id": "x", "cards": [{"item_id", "title", "reason_facts", "template"}]}`。
