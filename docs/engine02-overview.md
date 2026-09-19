# ENGINE 02 — 可解釋的檢索與排序

> 2026 梅竹黑客松 × 聚陽實業。這個分支（`engine02-research`）是 **ENGINE 02**：
> 把 ENGINE 01 的結構化需求變成**排序後的商品卡片**，而**每張卡片的理由就是分數分解本身**——
> 所有項加起來剛好等於總分，沒有事後生成的解釋模型。

```
ENGINE 01（意圖理解）→ 【ENGINE 02：檢索＋排序＋解釋】→ ENGINE 03（對話與回饋）
   Intent（中文）          POST /retrieve            RetrievalResult
                              ↑ 契約：docs/contract/（JSON Schema ＋ 兩輪真實範例）
```

**已經和 ENGINE 01 對接完成**：ENGINE 01 輸出的是繁體中文自由文字（`item_type: "連帽外套"`、
`occasion: "約會"`、`fit: "修身"`），我們的商品庫是英文 KAGL 詞彙。
轉接層在 [`engine02/intent_adapter.py`](engine02/intent_adapter.py)，
服務層有兩份、內容等價：`mcp_servers/catalog/`（Hermes 結構，demo 跑這個）與 `backend/engine02_retrieval/`（main 原有），
測試固定樣本直接取自 ENGINE 01 自己的 `test_cases.json`。細節見
[`mcp_servers/catalog/README.md`](mcp_servers/catalog/README.md)。

## 30 秒跑起來

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
.venv/bin/python scripts/integration_check.py --catalog data/catalog/kagl --encoder hash
# → PASS: an agent can drive this API     （22 項斷言，不需要 GPU、不需要下載模型、不需要網路）
```

現場 demo（真實商品庫 17,783 件）：

```bash
ENGINE02_CATALOG=data/catalog/kagl_polyvore_filled ENGINE02_ENCODER=marqo-fashionSigLIP \
ENGINE02_DEVICE=cuda ENGINE02_OT=1 ENGINE02_DEMO=1 \
python -m uvicorn engine02.api:app --host 0.0.0.0 --port 8002
```

`ENGINE02_DEMO=1` 保證**任何情況下都不會等 LLM 回應**：理由走模板，斷網照常出卡片。
上台前 60 秒：`curl localhost:8002/health` 看 `n_items` / `demo_mode` / `warm_ms`，
再跑一次 `scripts/integration_check.py`。完整清單在 [`docs/engine02-pipeline.md`](docs/engine02-pipeline.md)。

## 它怎麼算分

```
1. 硬條件過濾（品類／性別／排除值永不放寬；放寬了什麼會寫進理由）
2. 候選：BM25（自寫 postings，與 rank_bm25 逐分相同）＋ dense（Marqo-FashionSigLIP），RRF／凸組合融合
3. 可加總重排  S(i) = w·z(dense) + w·z(bm25) + Σ_d β_d·c(i,d) + 相容性 + 新鮮度 + 批評三角色 − 否決懲罰
        β_d = Σ_n p(n)·K[n,d] + step·Δ_d        （感性對照表 K：需求 × 可見設計要素，32 篇文獻編碼）
        c(i,d)：CLIP 反義詞成對打分，材質／光澤用 Qwen3-VL-8B 標註
4. 理由 = 最小充分集合（單靠這些項就足以讓這件留在前 k）
5. 模板句 → LLM 改寫（只有在每個標籤與數字都能在事實表裡查到時才採用）
```

**不變式**：`Σ contributions == score`，由測試釘住。任何新功能若破壞它就不上線。

## 主要端點

| Method | Path | 用途 |
|---|---|---|
| POST | `/retrieve` | **ENGINE 01 的 `Intent` → `RetrievalResult`**（團隊契約；`mcp_servers.catalog.main`，`backend.engine02_retrieval.main` 亦等價） |
| POST | `/rank` | `Engine02Request` → `Engine02Response`（卡片＋逐項貢獻＋理由） |
| POST | `/view` | 排序 ＋ 全部面板（說了／沒說、需求、Div@k、來源、與上一輪的差異） |
| POST | `/facets` | **同一份排序讀成 2–3 群**（「素面簡約 ↔ 強烈圖案」），2.7 ms，**排序零變動** |
| GET | `/profile/questions` → POST `/profile` | 開場三題（點真實服裝照）→ 第一輪的先驗 |
| POST | `/complete-look` | 搭配推薦（OutfitTransformer 互補頭） |
| POST | `/visual-search` | 上傳照片檢索 ＋ 設計要素側寫 |
| GET | `/gap/elements`、`/gap/cells`、`/needs/supply` | 給製造商：需求 vs 目錄供給的缺口 |
| GET | `/context` | 離線抓好的外部情境（天氣）；**服務路徑永不連網** |
| GET | `/vocabulary`、`/kansei`、`/arms`、`/health` | 給 ENGINE 01／03 對齊用 |

## 量過才敢講的結論

每一條都有對照組、配對排列檢定（10k–20k 次）與 bootstrap 信賴區間。完整表格在
[`docs/engine02-design.md`](docs/engine02-design.md)（§3.1–§3.35）。

| 結論 | 證據 |
|---|---|
| **換句話說的查詢原本會崩盤，根因是 idf 病理** | `everyday` 在 5,000 件裡只出現 1 次卻扛最高 idf。改用「碰到的商品比例」當閘門：0.111 → **0.308**（p<1e-5），用詞一致零代價（−0.002, p=0.50） |
| **使用者說「不要黑色」現在當輪生效** | 違反率 0.214 → **0.000**（p=5e-5），而且 NDCG@5 **+0.045**（p=0.0007）——遵守排除不用付代價 |
| **把批評拆成三個具名角色**（要出現／要保留／不要） | +0.064 NDCG@10（p=5e-5）；但**單獨用會 −0.116**，它取代不了硬條件 |
| **設計要素分數真的在量東西** | 反義詞成對 AUROC 0.98，**隨機字詞對照組只有 0.33–0.70** |
| **缺口盤是可否證的** | 遮掉表現某要素的商品，該要素 MRR 0.381 → 0.509（p<1e-4）；遮掉**同樣件數的隨機商品**完全不動（p=1.00） |
| **一輪感覺是即時的** | `/rank` p50 **12.8 ms**（17.8k）／15.7 ms（44k）、`/complete-look` 33 ms，且每一步都證明**不改變排序** |
| **可解釋性不用付排序代價** | Amazon ESCI 真人標註：可加總 rerank 勝過 RRF 與凸組合（4 項檢定 p≤0.011） |

**量了之後決定不做的（同樣重要）**：趨勢關鍵字進排序（28 組設定全變差）、KOL／社群訊號、
查詢端正規化、四個重排器、查詢接地、天氣加分項。理由都寫在設計文件裡，可以直接在台上講。

## 誠實清單

- 視覺標註目前是 **LLM 標註者**做的，所以那些 AUROC 是模型對模型；真人盲標的題本與計分腳本已備好。
- 開場三題側寫**通過**了自己的洗牌對照組，但真正來自「你答了什麼」的部分只有約四分之一，且 10 題明顯優於 3 題。
- 公開商品庫**沒有價格**；KAGL 缺外套／針織（已併入 Polyvore 服裝補救）。
- 模擬使用者是規則式的。
- 補值過的商品庫上，**絕不能拿模型自己填的欄位當標準答案**（`concept_labels()` 預設會丟掉那些列）。

## 檔案地圖

| 內容 | 路徑 |
|---|---|
| 完整管線說明、現場腳本、檢查清單 | [`docs/engine02-pipeline.md`](docs/engine02-pipeline.md) |
| 全部實驗與統計（§3.1–§3.35） | [`docs/engine02-design.md`](docs/engine02-design.md) |
| 文獻對照與查證 | [`docs/engine02-literature-review.md`](docs/engine02-literature-review.md) |
| 20+ 份研究筆記（延遲、業界做法、社群訊號、天氣、新穎度、2026 檢索機制…） | [`docs/research/`](docs/research/) |
| 介面契約（JSON Schema ＋ 兩輪真實範例） | [`docs/contract/`](docs/contract/) |
| 英文技術 README | [`engine02/README.md`](engine02/README.md) |
| 重跑實驗 | `python scripts/reproduce.py --list` / `--check-claims` |
