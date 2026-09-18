# 驗證 — 離線模擬使用者迴圈

**負責人：待確認（提議跟 `backend/generation/` 合併，見 docs/pinterest-and-generation.md）。** 這是建 repo 骨架時順便建立的佔位資料夾，讓這條線可以馬上開始動工。

只在開發階段用，不會出現在正式 demo。從策展好的 Pinterest 圖庫挑一張隱藏目標圖，讓 GPT-4o 把它描述成一個隱藏人設，讓模擬 LLM 使用者對付*跟 live demo 完全相同*的 ENGINE01–03 程式碼跑 2–4 輪，每輪都用 FashionCLIP cosine similarity 把輸出結果（推薦圖＋生成圖）拿去跟目標圖比對。重複跑 30–50 張目標圖再取平均，畫成一張相似度隨輪數收斂的折線圖——這是簡報／README 裡「回饋迴圈量化可驗證」的實際證據，對應競賽評分裡的「量化可驗證」要求。

完整規格：[../docs/validation-plan.md](../docs/validation-plan.md)。

**生圖額度提醒**：這個迴圈需要 60–200 次生圖呼叫（30–50 張目標圖 × 2–4 輪 × 2 個分支）。依規劃文件，建議排在現場兩天的第一天跑完，不要留到第二天，免得擠掉 demo 當天要用的額度。
