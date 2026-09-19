# Consumer Intent Agent（一句話讀懂消費者）

> 這是 [README.md](README.md) 的中文版。根目錄的 README.md 依競賽交付項目要求維持英文，這份是給團隊內部看的中文對照版，內容異動時兩邊都要同步更新。

**勢在必得**團隊為 **2026 梅竹黑客松 x 聚陽實業（Makalot Industrial）** 打造的 prototype，題目是「一句話讀懂消費者」。

Consumer Intent Agent 把消費者的一句話服飾需求，轉成結構化、可解釋的意圖，用 hybrid search ＋ reranker 檢索出符合的商品，同時生成一張原創概念圖跟檢索結果並排呈現，再依使用者回饋讓兩者跨輪次一起變準——而且這個「變準」要秀出量化、可驗證的分數，不是嘴上說有進步。

## 系統概觀

整套系統是兩個引擎加一個生成模組，後面接 FastAPI 後端、前端用 React：

- **ENGINE 01 — 需求理解**：一句話 → 結構化 JSON 意圖（品項、顏色、場合、預算、風格關鍵字），用 GPT structured output 實作。模糊或推斷出來的欄位會標成系統推斷（絕不悄悄用猜的當成使用者原話），意圖不夠明確時會出澄清選擇題。
- **ENGINE 02 — 檢索與排序**（已實作，`engine02/` ＋ `backend/engine02_retrieval/`）：在 KAGL 服飾商品庫上做 hybrid search（dense embedding ＋ 自己寫的 BM25），用一個逐項加總的分數重新排序——每一項的貢獻都會回傳、加起來剛好等於總分，這個分數分解本身就是解釋，不是另外生成的。完整設計與實驗見 [docs/engine02-design.md](docs/engine02-design.md)，怎麼跑見 [docs/engine02-pipeline.md](docs/engine02-pipeline.md)。
- **ENGINE 03 — 偏好回饋迴圈**：把自由文字加上分項評分（顏色／版型／圖案／領子，資料集商品和生成概念圖分開打分）轉成結構化的權重／意圖修正，觸發下一輪。
- **生成模組**：用 OpenAI Responses API 的 `image_generation` tool，每輪產一張原創概念圖跟檢索結果並排；這張圖會轉成向量併回 ENGINE 02 的 dense 分數，讓檢索和生成互相加強。
- **Pinterest 趨勢訊號**：團隊自己策展的 Pinterest 板子（Trial API access）餵進 ENGINE 02 的排序權重。

兩條迴圈共用同一套 ENGINE 01–03 程式碼：**live 流程**（真人使用者／評審在瀏覽器上互動）和一條**離線驗證迴圈**（開發階段用的模擬 LLM 使用者，帶著隱藏目標圖片人設，只用來產生量化準確度數字，不會出現在正式 demo 畫面）。詳見 [docs/system-architecture.svg](docs/system-architecture.svg) 和 [docs/validation-flow.svg](docs/validation-flow.svg)。

完整背景、評分標準、設計理由：[docs/hackathon-brief.md](docs/hackathon-brief.md)。給 AI coding agent 看的專案規格：[CLAUDE.md](CLAUDE.md)。

## Repo 結構

```
docs/               所有專案 markdown 文件與架構圖
backend/
  shared/            跨引擎共用的 Pydantic schema（介面契約）
  engine01_intent/   需求理解（FastAPI service）
  engine02_retrieval/  ENGINE02 的 HTTP 介接層（Intent 進、RetrievalResult 出；完整 API 掛在 /engine02/*）
  engine03_feedback/   偏好回饋迴圈
  generation/          概念圖生成
  pinterest/           Pinterest 趨勢訊號串接
engine02/            ENGINE02 的實作套件（刻意放在 repo 根目錄，見 CLAUDE.md「Repo 結構」——
                     內部路徑解析與 40+ 支腳本都假設這個位置）
frontend/            React + Vite UI
validation/          離線模擬使用者驗證迴圈
scripts/             開發輔助／資料下載腳本，還有 ENGINE02 的評測腳本
```

## 快速開始

需求：Python 3.11+、Node.js 18+。

ENGINE01 跑在 OpenAI 的 Codex CLI 上，吃你的 ChatGPT Plus/Pro 訂閱額度（不用 API key）——先跑一次 `codex login`。其他模組（ENGINE03、生成模組）視負責人怎麼實作，可能還是需要 `OPENAI_API_KEY`，細節見 [CLAUDE.md](CLAUDE.md)。

```bash
cp .env.example .env   # 只有你要跑的模組需要 OPENAI_API_KEY 時才填
codex login             # 一次性設定，ENGINE01 需要

# ENGINE01
pip install -r backend/requirements.txt
uvicorn backend.engine01_intent.main:app --reload

# 前端
cd frontend && npm install && npm run dev
```

**ENGINE02 有自己獨立的環境**（repo 根目錄的 `pyproject.toml`，用 `uv` 安裝——確切指令跟為什麼不共用 `backend/requirements.txt` 見 [backend/engine02_retrieval/README.md](backend/engine02_retrieval/README.md)），跑在自己的獨立服務、另一個 port 上。

每個 `backend/` 底下的模組都有自己的 `README.md`，裡面有各自的執行／測試說明。

## 交付項目清單（依競賽簡報）

1. 可實際運作、可現場互動展示的 prototype。
2. 這個 GitHub repo ＋英文 README（可重現性）。
3. 2–3 分鐘的 demo 影片（MP4）。
4. 現場問答與臨場調整——賽後不需要繳交模型權重。

## 授權

非商業性質的黑客松 prototype，不適用於正式產品環境。
