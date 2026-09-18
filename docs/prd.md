# PRD — Consumer Intent Agent

骨架依照簡報自己的「PRD 撰寫指南」（hackathon-brief.md）寫成，那份文件說直接抄裡面的段落就好，不用重新想。標成 **待確認** 的段落還需要團隊補齊才算定案。

## 1. 產品目標與範圍

2026 梅竹黑客松 x 聚陽實業（Makalot Industrial），題目「一句話讀懂消費者」。聚陽替品牌客戶代工生產，已經有收集消費後回饋（VOC）的能力，但缺的是消費者購買前的意圖訊號——這正是這個專案要補上的缺口。目標：把消費者的一句話轉成結構化、可解釋的意圖，讓這個訊號能回流設計流程（趨勢 → 設計師 → 材料／生產 → 品牌商店）。詳見 [hackathon-brief.md](hackathon-brief.md) 的「基本資訊」／「交付項目」／「企業背景與痛點」／「題目核心要求」。

## 2. 系統架構

![Live 流程](system-architecture.svg)
![驗證流程](validation-flow.svg)

兩條迴圈共用同一套 ENGINE01–03 程式碼——live（真人使用者／評審）和離線驗證（模擬使用者，只在開發階段用）。完整說明見 [hackathon-brief.md](hackathon-brief.md) 的「整體怎麼運作：兩條迴圈，共用一套引擎」，CLAUDE.md 裡有濃縮版。

## 3. 模組規格

- [ENGINE01 — 需求理解](engine01-intent.md)
- [ENGINE02 — 檢索與排序](engine02-retrieval.md)
- [ENGINE03 — 偏好回饋迴圈](engine03-feedback.md)
- [前端](frontend.md)
- [Pinterest ＋ 生成模組](pinterest-and-generation.md)

## 4. 介面契約

[interface-contract.md](interface-contract.md) — **draft v1，需要所有引擎負責人簽核確認。** 這是六條線能真的平行開發的前提，ENGINE02/03／前端動工前務必先確認欄位，不要照著這份草稿直接開始寫。

## 5. 驗證與量化指標

[validation-plan.md](validation-plan.md) — 離線（ENGINE01 準確率、ENGINE02 ablation）、現場即時符合度分數、開發階段模擬使用者收斂研究。

## 6. 時程與分工 — 待確認

5 人、6 條線（ENGINE01/02/03、前端、Pinterest＋生成模組合併）。依簡報建議的分法：ENGINE01/02/03／前端各配一人，Pinterest＋生成模組合併給第五人。目前確認的部分：

| 線 | 負責人 |
|---|---|
| ENGINE01 | 這個 repo 骨架的建立者 |
| Pinterest 板子策展 | 品諭 |
| ENGINE02 | 待確認 |
| ENGINE03 | 待確認 |
| 前端 | 待確認 |
| 生成模組 | 待確認 |

實際動手寫 code 集中在比賽現場兩天（2026-09-19 起）；賽前時間拿來把架構、分工、介面契約定案，不是拿來寫功能。

## 7. 這份 PRD 定案前還要關掉的項目

抄自 [hackathon-brief.md](hackathon-brief.md) 的「寫 PRD 前還要定案的事項」，加上建這個 repo 骨架時實際發現的狀況：

- **ENGINE01 已解決：** 團隊希望不要花錢，所以 ENGINE01 改用 `codex exec`（吃 ChatGPT Plus/Pro，每次呼叫 $0，但實測約 8–17 秒、吃掉團隊共用 Codex 額度約 14–20K token——見根目錄 `CLAUDE.md` 的「ENGINE01 執行方式：codex exec」）。**ENGINE02/03／生成模組仍待確認：** 團隊還沒有人申請 platform.openai.com 的 API key，這幾個模組的負責人要自己決定是要申請一把，還是找其他不花錢的路。
- 商品庫資料集：**已定案**，Polyvore Outfits Dataset。
- Pinterest 板子要存哪些具體的目標圖（品諭負責）。
- Demo 腳本：第一輪、第二輪具體要示範的題目和回饋內容。
- 驗證迴圈的圖片生成：簡報原本的計畫（Hermes Agent ＋ Codex auth 跑批次生圖）在這個 repo 裡還沒實測過——負責生成／驗證線的人應該比照 ENGINE01 的 `codex exec` 那樣，自己實際跑一次、量出真實的延遲和額度消耗，不要直接假設簡報裡寫的還成立。
