# reports/ — 每個宣稱數字的出處

這份的用途只有一個：**把文件裡每一個數字，對到一個可以打開來看的檔案。**
如果一個數字在這裡找不到對應的檔案，那它就不該出現在簡報上。

`data/` 與大部分 `reports/` 子資料夾不進版控（體積），但**論述用到的證據檔刻意納入**，
總共約 4 MB。判準是：**別人重現不出來的，就附上去**。

---

## 對照表

| 宣稱 | 數字 | 證據檔 | 能否自行重現 |
|---|---|---|---|
| 尊重否定不犧牲品質 | violation@5 0.214 → **0.000**（p=5e-5）<br>NDCG@5 **+0.045**（p=0.0007） | `ablation/neg_smoke/negation_kagl_hash-256.{csv,json}` | ✅ `scripts/eval_negation.py` |
| critique 三角色有效 | NDCG@10 **+0.064**（p=5e-5, 600 triplet） | `ablation/roles_smoke/summary.{csv,json}`<br>`ablation/roles_smoke/triplets.csv` | ✅ |
| 三角色**單獨**使用會變差 | **−0.116** | 同上 `sweep.csv` | ✅ |
| 趨勢進排序一律變差 | 28 種 `w_trend` 設定，NDCG@5 **−0.16 ～ −0.38** | `trend_ablation/trends_*.csv`<br>（欄位 `w_trend, ndcg5, ndcg10`） | ⚠️ 需要趨勢資料，見 `data/trends/` |
| 預測勝過最強 baseline | Wikipedia 組合 **0.583** vs naive 0.693（p=0.0015） | `forecast/backtest_h8.json` | ✅ `scripts/eval_forecast.py` |
| Pinterest 來源**輸給** baseline | 組合 2.264 vs naive **2.132** | 同上 | ⚠️ 需要 Pinterest token，**歷史資料已附在 `data/trends/history/`** |
| BM25 idf 病理閘門 | `share_docs_touched < 0.12` | `ablation/bm25_gate_kagl_hash-256.{csv,json}` | ✅ `scripts/eval_bm25_gate.py` |
| 設計要素與人工標註的一致度 | AUROC | `ablation/visual_label_auroc_*.csv` | ⚠️ 需要人工標註，**已附在 `data/labels/`** |
| 感性表敏感度 | — | `ablation/kansei_sensitivity_hash.{csv,json}` | ✅ |
| 新鮮度 / 疲勞 / 缺口 | — | `ablation/{freshness,fatigue,gap}_kagl_hash-256.*` | ✅ |
| 主要 arm 比較（各編碼器） | — | `ablation/kagl_marqo-fashionSigLIP/`<br>`ablation/kagl_fashion-clip/` | ✅ |
| 延遲 | CPU `/rank` p50 111 ms | `latency/latency_kagl_hash-256.{csv,json}`<br>`latency/parity.json` | ✅ `scripts/bench_latency.py` |
| 模型驗證 | — | `model_verification.md`、`model_verification_cpu.json` | ✅ `scripts/verify_models.py` |
| 設計要素剖析不穩定 | 平均 \|Δz\| > 0.4，**9.7%** 正負反轉 | `engine02/resources/profile_stability_v1.json`（套件內，已追蹤） | — 已內建 |

---

## ⚠️ 目前**沒有**證據檔的宣稱

誠實列出來，簡報前要補或改口。

| 宣稱 | 狀態 |
|---|---|
| 60 位模擬購物者：gain 1 → 60.0%、gain 2 → **70.0% / −0.167 z**、gain 3 → 76.7% | **`reports/server/simulation/` 在本機是空的。** 這是在 GPU 伺服器上跑的，產出沒有帶回來。<br>重現方式：`python scripts/simulate_sessions.py`（需要商品庫；預設輸出 `reports/server/simulation/sessions.json`）。<br>**在檔案補上來之前，這三個數字不應該出現在簡報上。** |

---

## 沒有納入版控的（體積）

| 資料夾 | 大小 | 為什麼不附 |
|---|---|---|
| `server/` | 58 MB | 伺服器上各種掃描的原始輸出，結論已萃取到 `ablation/` |
| `agents/` | 61 MB | 子代理的稽核輸出；其中與趨勢相關的已抽到 `trend_ablation/` |
| `demo/` | 1.4 MB | demo 情境快取，可重跑 |
| `llm_paraphrase/` | 193 KB | LLM 改寫的中間產物 |

需要完整原始輸出的話，掛 GitHub Release 或雲端硬碟，不要 commit 進 repo——
二進位／大量檔案一旦進了 git 歷史就拿不掉，之後每個人 clone 都要付一次代價。

---

## 給其他組員的 Agent

要查證一個數字，照這個順序：

1. 在上面的對照表找那個宣稱 → 打開對應檔案
2. 找不到 → 看「目前沒有證據檔」那一節
3. 還是找不到 → **那個數字沒有出處，不要引用**

`data/` 底下附上的證據檔（人工標註、趨勢歷史、VLM 屬性）在 `data/README.md` 有逐項說明，
包含哪些重現得出來、哪些重現不出來、為什麼。
