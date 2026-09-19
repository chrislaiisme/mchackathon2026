"""Build engine02/resources/taxonomy_v1.json and the per-source subcategory maps.

Usage (repo root):
    .venv/Scripts/python.exe scripts/build_taxonomy_v1.py \
        --counts reports/agents/taxonomy/subcategory_counts.json \
        --gpt reports/agents/taxonomy/gpt_en-US.txt --gpt-zh reports/agents/taxonomy/gpt_zh-CN.txt

--counts  JSON {catalog: {"n": int, "rows": [[subcategory, legacy_coarse, n], ...]}} produced with pandas
          value counts over data/catalog/{kagl,polyvore}/items.parquet (local) and
          /tmp/neil/mchackathon2026/data/catalog/{kagl_full,polyvore_big,kagl_polyvore}/items.parquet (nycu).
--gpt     Google Product Taxonomy "taxonomy-with-ids.en-US.txt" (version 2021-09-21); every GPT id used
          below is validated against it and its full path is stored in the JSON.

Design rationale and sources: docs/research/taxonomy.md. Every source subcategory value present in the
counts file must receive an explicit decision here; the script fails otherwise (no silent "other").
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

VERSION = "taxonomy_v1"

# ---------------------------------------------------------------------------------------------
# attribute vocabularies (values follow Fashionpedia's ontology attribute names, Jia et al. 2020;
# construction/HS follow WCO HS 2022 chapters 61 (knitted or crocheted) vs 62 (not knitted))
# ---------------------------------------------------------------------------------------------
ATTRIBUTE_DEFS = {
    "sleeve_length": {"sleeveless": "無袖", "short": "短袖", "elbow-length": "五分袖", "three-quarter": "七分袖",
                      "wrist-length": "長袖"},
    "neckline": {"crew": "圓領", "v-neck": "V領", "scoop": "大圓領", "boat": "船型領", "square": "方領",
                 "turtle": "高領", "cowl": "垂墜領", "halter": "繞頸", "shirt-collar": "襯衫領", "polo-collar": "POLO領",
                 "hood": "連帽"},
    "fit": {"tight": "合身/緊身", "regular": "標準", "loose": "寬鬆", "oversized": "oversized"},
    "length": {"mini": "迷你", "above-the-knee": "膝上", "knee": "及膝", "below-the-knee": "膝下", "midi": "中長",
               "maxi": "長版", "floor": "及地", "cropped": "短版/七分", "full": "全長"},
    "construction": {"knit": "針織 (HS 第61章)", "woven": "梭織 (HS 第62章)", "mixed": "兩者皆常見",
                     "non_textile": "非成衣紡織品 (HS 其他章, 未驗證)"},
    "heel_height": {"flat": "平底", "low": "低跟", "mid": "中跟", "high": "高跟"},
    "carry": {"hand": "手提", "shoulder": "肩背", "crossbody": "斜背", "back": "後背", "waist": "腰/胸"},
}
L1_ATTRS = {
    "tops": ["sleeve_length", "neckline", "fit", "construction"],
    "bottoms": ["length", "fit", "construction"],
    "dresses": ["sleeve_length", "neckline", "length", "fit", "construction"],
    "outerwear": ["length", "fit", "construction"],
    "sets": ["construction"],
    "intimates": ["construction"],
    "swimwear": ["construction"],
    "shoes": ["heel_height"],
    "bags": ["carry"],
    "accessories": [],
    "jewelry": [],
    "beauty": [],
}

NODES: list[dict] = []


def N(nid, zh, en, syn_zh=(), syn_en=(), gpt=None, construction=None, hs=None, note=None, **extra):
    """gpt = (id, match) with match in exact|broader (GPT node is broader than ours)|narrower."""
    level = nid.count(".") + 1
    parent = nid.rsplit(".", 1)[0] if level > 1 else None
    d = dict(id=nid, level=level, parent=parent, label_en=en, label_zh=zh, synonyms_zh=list(syn_zh),
             synonyms_en=list(syn_en), gpt=None if gpt is None else {"id": gpt[0], "match": gpt[1]})
    if construction:
        d["construction"] = construction
    if hs:
        d["hs_headings"] = hs
    if note:
        d["note"] = note
    d.update(extra)
    NODES.append(d)


K, W = "knit", "woven"
# ------------------------------------------------------------------ L1: tops
N("tops", "上衣", "Tops", ["上衣", "上身", "上著", "衣服上身"], ["top", "tops", "shirts & tops"], gpt=(212, "exact"),
  legacy_coarse="top", apparel=True)
N("tops.tshirts", "T恤", "T-shirts", ["T恤", "t-shirt", "短T", "長T", "短袖T", "長袖T", "素T", "圓領T", "印花T", "寬版T", "TEE", "體恤", "短袖上衣"],
  ["t-shirt", "t-shirts", "tshirt", "tshirts", "tee", "tees"], gpt=(212, "broader"), construction=K,
  hs={"knit": ["61.09"]})
N("tops.polos", "POLO衫", "Polo shirts", ["POLO衫", "polo衫", "POLO", "網眼衫"], ["polo", "polos", "polo shirt"],
  gpt=(212, "broader"), construction=K, hs={"knit": ["61.05", "61.06"]})
N("tops.shirts", "襯衫", "Shirts", ["襯衫", "襯衣", "恤衫", "牛津襯衫", "法蘭絨襯衫", "格紋襯衫", "正式襯衫", "商務襯衫", "白襯衫", "西裝襯衫"],
  ["shirt", "shirts", "dress shirt", "dress shirts", "casual shirt", "casual shirts", "button-down", "oxford shirt"],
  gpt=(212, "broader"), construction=W, hs={"woven": ["62.05", "62.06"], "knit": ["61.05", "61.06"]})
N("tops.blouses", "女衫/雪紡衫", "Blouses", ["雪紡衫", "雪紡上衣", "女衫", "罩衫", "荷葉邊上衣", "蕾絲上衣", "女襯衫", "襯衫/雪紡"],
  ["blouse", "blouses", "shirt-blouse"], gpt=(212, "broader"), construction=W, hs={"woven": ["62.06"], "knit": ["61.06"]})
N("tops.tanks_camis", "背心/小可愛", "Tank tops & camisoles", ["背心", "小可愛", "細肩帶", "細肩帶上衣", "坦克背心", "無袖上衣", "削肩上衣", "吊帶背心", "平口上衣", "bra top"],
  ["tank top", "tank tops", "tank", "camisole", "camisoles", "cami", "singlet", "tube top"],
  gpt=(212, "broader"), construction=K, hs={"knit": ["61.09"], "woven": ["62.06"]})
N("tops.sweaters", "毛衣/針織衫", "Sweaters", ["毛衣", "針織衫", "針織上衣", "線衫", "高領毛衣", "套頭毛衣", "羊毛衫", "喀什米爾毛衣", "麻花毛衣"],
  ["sweater", "sweaters", "jumper", "pullover", "knitwear", "turtleneck"], gpt=(212, "broader"), construction=K,
  hs={"knit": ["61.10"]})
N("tops.cardigans", "開襟針織衫", "Cardigans", ["開襟衫", "針織外套", "開襟毛衣", "罩衫外套", "針織開襟外套"],
  ["cardigan", "cardigans"], gpt=(212, "broader"), construction=K, hs={"knit": ["61.10"]},
  note="Fashionpedia 與 Polyvore 把 cardigan 放上衣；ModaNet 放 outer。沿用現行 coarse=top。")
N("tops.sweatshirts_hoodies", "大學T/帽T", "Sweatshirts & hoodies", ["大學T", "帽T", "連帽T", "連帽上衣", "衛衣", "刷毛上衣", "長袖大學T", "連帽衫"],
  ["sweatshirt", "sweatshirts", "hoodie", "hoodies", "hooded sweatshirt", "crewneck sweatshirt"],
  gpt=(212, "broader"), construction=K, hs={"knit": ["61.10"]})
N("tops.tunics", "長版上衣", "Tunics", ["長版上衣", "長版衫", "罩袍上衣"], ["tunic", "tunics"], gpt=(212, "broader"),
  construction="mixed", hs={"knit": ["61.06"], "woven": ["62.06"]})
N("tops.kurtas", "庫爾塔（印度長衫）", "Kurtas & kurtis", ["庫爾塔", "印度長衫", "印度上衣"], ["kurta", "kurtas", "kurti", "kurtis"],
  gpt=(212, "broader"), construction="mixed", hs={"knit": ["61.05", "61.06"], "woven": ["62.05", "62.06"]},
  note="民族服飾放在其服裝部位之下（庫爾塔＝長版上衣），另用 coll.ethnic 橫切集合；GPT 只把 Saris & Lehengas 列為 Traditional。")
N("tops.active_tops", "運動上衣", "Activewear tops", ["運動上衣", "運動T恤", "排汗衫", "機能上衣", "瑜珈上衣", "運動背心", "跑步上衣", "健身上衣", "緊身衣"],
  ["activewear top", "activewear tops", "activewear tank top", "activewear tank tops", "training top", "running top",
   "jersey", "compression top"], gpt=(5322, "broader"), construction=K, hs={"knit": ["61.09", "61.10", "61.14"]},
  collections=["coll.activewear"])

# ------------------------------------------------------------------ L1: bottoms
N("bottoms", "下身（褲/裙）", "Bottoms", ["下身", "下著", "褲裝", "褲子", "褲", "下半身"], ["bottom", "bottoms", "bottomwear"],
  gpt=None, legacy_coarse="bottom", apparel=True,
  note="GPT 沒有『下身』節點（Pants 204 / Shorts 207 / Skirts 1581 為平行節點）。")
N("bottoms.jeans", "牛仔褲", "Jeans", ["牛仔褲", "長褲", "丹寧褲", "直筒牛仔褲", "寬褲牛仔褲", "緊身牛仔褲", "男友褲", "喇叭牛仔褲", "靴型褲"],
  ["jeans", "denim jeans", "skinny jeans", "boyfriend jeans", "straight leg jeans", "flared jeans", "bootcut jeans",
   "wide leg jeans", "jeggings", "denim"], gpt=(204, "broader"), construction=W, hs={"woven": ["62.03", "62.04"]})
N("bottoms.trousers", "長褲/西裝褲/休閒褲", "Trousers", ["長褲", "西裝褲", "西褲", "休閒褲", "卡其褲", "寬褲", "闊腿褲", "直筒褲", "錐形褲", "工作褲", "工裝褲", "打褶褲", "紳士褲", "老爺褲", "九分褲", "寬版長褲"],
  ["trousers", "trouser", "pants", "chinos", "slacks", "casual pants", "dress pants", "wide leg pants", "cargo pants"],
  gpt=(204, "broader"), construction=W, hs={"woven": ["62.03", "62.04"], "knit": ["61.03", "61.04"]})
N("bottoms.track_pants", "運動褲/棉褲", "Track pants & joggers", ["運動褲", "長褲", "運動長褲", "棉褲", "慢跑褲", "束口褲", "縮口褲", "休閒運動褲", "刷毛褲", "訓練褲", "機能褲", "jogger"],
  ["track pants", "trackpants", "joggers", "jogger pants", "sweatpants", "activewear pants", "training pants"],
  gpt=(204, "broader"), construction=K, hs={"knit": ["61.03", "61.04"], "woven": ["62.03", "62.04"]},
  collections=["coll.activewear"])
N("bottoms.leggings", "內搭褲/瑜珈褲", "Leggings & tights", ["內搭褲", "瑜珈褲", "瑜伽褲", "緊身褲", "壓力褲", "韻律褲", "legging", "緊身運動褲"],
  ["leggings", "legging", "yoga pants", "running tights", "compression tights"], gpt=(204, "broader"), construction=K,
  hs={"knit": ["61.03", "61.04"]}, collections=["coll.activewear"],
  note="瑜珈褲同時屬 coll.activewear；KAGL 'Tights'（Nike 訓練緊身褲與 Happy Socks 褲襪混雜）歸此。")
N("bottoms.shorts", "短褲", "Shorts", ["短褲", "熱褲", "五分褲", "百慕達短褲", "牛仔短褲", "海灘褲"],
  ["shorts", "short", "bermuda shorts", "activewear shorts", "denim shorts"], gpt=(207, "exact"), construction="mixed",
  hs={"knit": ["61.03", "61.04"], "woven": ["62.03", "62.04"]})
N("bottoms.skirts", "裙子", "Skirts", ["裙子", "半身裙", "短裙", "長裙", "中長裙", "及膝裙", "窄裙", "百褶裙", "A字裙", "迷你裙", "牛仔裙", "魚尾裙", "褲裙", "包臀裙", "裙"],
  ["skirt", "skirts", "mini skirt", "mini skirts", "knee length skirts", "long skirts", "maxi skirt", "midi skirt",
   "pencil skirt", "skort"], gpt=(1581, "exact"), construction="mixed",
  hs={"knit": ["61.04"], "woven": ["62.04"]})
N("bottoms.capris", "七分褲/九分褲", "Capris & cropped pants", ["七分褲", "八分褲", "九分褲", "六分褲", "短版褲", "捲褲管長褲"],
  ["capris", "capri pants", "cropped pants", "capri & cropped pants", "three quarter pants"], gpt=(204, "broader"),
  construction="mixed", hs={"knit": ["61.03", "61.04"], "woven": ["62.03", "62.04"]})
N("bottoms.ethnic_bottoms", "印度傳統下著", "Ethnic bottoms (salwar, patiala, churidar)", ["紗瓦褲", "印度褲", "燈籠褲"],
  ["salwar", "patiala", "churidar"], gpt=(204, "broader"), construction="mixed",
  hs={"knit": ["61.04"], "woven": ["62.04"]}, collections=["coll.ethnic"])

# ------------------------------------------------------------------ L1: dresses & one-pieces
N("dresses", "洋裝/連身", "Dresses & one-pieces", ["連身款", "一件式"], ["one-piece", "one-pieces", "dresses & jumpsuits"],
  gpt=(2271, "narrower"), legacy_coarse="dress", apparel=True,
  note="GPT 的 Dresses(2271) 與 One-Pieces(5182) 是兩個兄弟節點；此 L1 合併兩者，因為對搭配而言是同一個『全身』槽位。")
N("dresses.dresses", "洋裝", "Dresses", ["洋裝", "連身裙", "連衣裙", "長洋裝", "短洋裝", "襯衫洋裝", "針織洋裝", "碎花洋裝", "背心裙", "吊帶裙", "無袖洋裝", "上班洋裝"],
  ["dress", "dresses", "day dress", "day dresses", "sundress", "shirt dress", "maxi dress", "midi dress"],
  gpt=(2271, "exact"), construction="mixed", hs={"knit": ["61.04"], "woven": ["62.04"]})
N("dresses.party_dresses", "小禮服/派對洋裝", "Cocktail & party dresses", ["小禮服", "派對洋裝", "宴會洋裝", "雞尾酒禮服", "婚禮賓客洋裝", "伴娘服", "洋裝", "連身裙"],
  ["cocktail dress", "cocktail dresses", "party dress", "party dresses", "bridesmaid dress"],
  gpt=(2271, "broader"), construction="mixed", hs={"knit": ["61.04"], "woven": ["62.04"]})
N("dresses.gowns", "晚禮服/婚紗", "Gowns & wedding dresses", ["晚禮服", "長禮服", "禮服", "婚紗", "新娘禮服", "白紗"],
  ["gown", "gowns", "evening gown", "wedding dress", "wedding dresses", "ball gown"], gpt=(5441, "broader"),
  construction="mixed", hs={"knit": ["61.04"], "woven": ["62.04"]})
N("dresses.jumpsuits_rompers", "連身褲", "Jumpsuits & rompers", ["連身褲", "連身衣褲", "吊帶褲", "連身短褲", "工作連身服"],
  ["jumpsuit", "jumpsuits", "romper", "rompers", "playsuit", "overalls", "dungarees"], gpt=(5250, "exact"),
  construction="mixed", hs={"knit": ["61.14"], "woven": ["62.11"]})
N("dresses.sarees_lehengas", "紗麗/蘭加裙", "Sarees & lehengas", ["紗麗", "沙麗", "蘭加裙", "印度紗麗"],
  ["saree", "sarees", "sari", "saris", "lehenga", "lehenga choli"], gpt=(8248, "exact"), construction="woven",
  collections=["coll.ethnic"], note="紗麗是整塊披掛的全身服裝，搭配槽位等同洋裝；HS 歸類視布料而定，未標。")

# ------------------------------------------------------------------ L1: outerwear
N("outerwear", "外套", "Outerwear", ["外套", "外搭", "外衣"], ["outerwear", "outer", "coats & jackets"], gpt=(203, "exact"),
  legacy_coarse="outerwear", apparel=True)
N("outerwear.jackets", "夾克", "Jackets", ["夾克", "飛行外套", "牛仔外套", "皮衣", "皮外套", "機車外套", "教練外套", "防風外套", "風衣外套", "衝鋒衣", "羽絨外套", "鋪棉外套", "運動外套", "連帽外套", "軍裝外套", "棒球外套", "外套夾克", "短外套", "薄外套", "防曬外套"],
  ["jacket", "jackets", "bomber", "denim jacket", "leather jacket", "windbreaker", "puffer jacket", "track jacket",
   "activewear jacket", "activewear jackets", "rain jacket", "shrug", "nehru jacket", "anorak"],
  gpt=(5598, "broader"), construction="mixed", hs={"knit": ["61.01", "61.02"], "woven": ["62.01", "62.02"]})
N("outerwear.coats", "大衣", "Coats", ["大衣", "長大衣", "風衣", "毛呢大衣", "羊毛大衣", "羽絨大衣", "長版外套", "雙排扣大衣", "派克大衣"],
  ["coat", "coats", "overcoat", "trench coat", "parka", "peacoat", "puffer coat"], gpt=(5598, "broader"),
  construction=W, hs={"woven": ["62.01", "62.02"], "knit": ["61.01", "61.02"]})
N("outerwear.blazers", "西裝外套", "Blazers & sport coats", ["西裝外套", "西外", "休閒西裝", "西裝上衣", "西裝"],
  ["blazer", "blazers", "sport coat", "sportcoat", "sportcoats & blazers", "suit jacket"], gpt=(5598, "broader"),
  construction=W, hs={"woven": ["62.03", "62.04"], "knit": ["61.03", "61.04"]})
N("outerwear.vests", "背心外套/西裝背心", "Vests & waistcoats", ["背心外套", "西裝背心", "羽絨背心", "鋪棉背心", "馬甲", "針織背心", "背心"],
  ["vest", "vests", "waistcoat", "gilet", "puffer vest"], gpt=(1831, "exact"), construction="mixed",
  hs={"knit": ["61.10"], "woven": ["62.11"]})
N("outerwear.rainwear", "雨衣", "Rainwear", ["雨衣", "雨褲", "雨衣褲", "輕便雨衣"], ["raincoat", "rain pants", "rain trousers", "rain suit"],
  gpt=(3066, "broader"), construction=W, hs={"woven": ["62.01", "62.02", "62.10"]})

# ------------------------------------------------------------------ L1: sets & suits
N("sets", "套裝", "Sets & suits", ["套裝", "成套", "兩件式", "多件式套裝", "兩件組"], ["set", "sets", "co-ord", "outfit set", "clothing set"],
  gpt=(7313, "broader"), legacy_coarse="other", apparel=True,
  note="成套商品不是單一搭配槽位；現行 coarse=other 保留，但 ENGINE 01 可以明確要求套裝。")
N("sets.suits", "西裝套裝", "Suits", ["西裝套裝", "西服", "整套西裝", "褲裝套裝", "裙裝套裝", "西裝"], ["suit", "suits", "pant suit", "skirt suit", "tuxedo"],
  gpt=(1594, "exact"), construction=W, hs={"woven": ["62.03", "62.04"], "knit": ["61.03", "61.04"]})
N("sets.tracksuits", "運動套裝", "Tracksuits", ["運動套裝", "運動服套裝", "休閒套裝", "棉質套裝"], ["tracksuit", "tracksuits", "track suit", "sweatsuit"],
  gpt=(7313, "broader"), construction=K, hs={"knit": ["61.12"], "woven": ["62.11"]}, collections=["coll.activewear"])
N("sets.ethnic_sets", "印度傳統套裝", "Ethnic sets (kurta sets, salwar suits)", ["庫爾塔套裝", "印度套裝"],
  ["kurta set", "kurta sets", "salwar suit", "salwar and dupatta", "churidar kurta"], gpt=(5388, "broader"),
  construction="mixed", collections=["coll.ethnic"])
N("sets.clothing_sets", "多件式套裝", "Clothing sets", ["多件式套裝", "上下套裝", "兩件式套裝"], ["clothing set", "co-ord set", "two-piece set"],
  gpt=(7313, "exact"), construction="mixed", hs={"knit": ["61.03", "61.04"], "woven": ["62.03", "62.04"]})

# ------------------------------------------------------------------ L1: intimates & sleepwear (Makalot: Sleepwear/Loungewear, Underwear)
N("intimates", "內著/睡衣", "Underwear, sleep & loungewear", ["內著", "貼身衣物", "內睡衣", "內衣褲"], ["intimates", "innerwear", "underwear", "lingerie", "nightwear"],
  gpt=(213, "broader"), legacy_coarse="other", apparel=True,
  note="聚陽 Fashion Apparel 產品線含 Sleepwear/Loungewear 與 Underwear（2026 法說簡報 p.5），故為 L1。")
N("intimates.bras", "內衣/胸罩", "Bras", ["內衣", "胸罩", "無鋼圈內衣", "集中內衣", "無痕內衣", "bra", "文胸", "隱形內衣"], ["bra", "bras", "bralette", "brassiere"],
  gpt=(214, "exact"), construction="mixed", hs={"any": ["62.12"]})
N("intimates.sports_bras", "運動內衣", "Sports bras", ["運動內衣", "運動胸罩", "運動bra", "瑜珈內衣"], ["sports bra", "sports bras"],
  gpt=(214, "broader"), construction=K, hs={"any": ["62.12"]}, collections=["coll.activewear"])
N("intimates.underwear", "內褲", "Underwear (briefs, boxers, trunks)", ["內褲", "三角褲", "四角褲", "平口褲", "丁字褲", "男內褲", "女內褲", "無痕內褲", "生理褲"],
  ["briefs", "brief", "boxers", "boxer", "trunks", "trunk", "panties", "thongs", "panties & thongs", "underpants"],
  gpt=(2562, "exact"), construction=K, hs={"knit": ["61.07", "61.08"], "woven": ["62.07", "62.08"]})
N("intimates.undershirts", "汗衫/內搭衣", "Undershirts, innerwear vests & slips", ["汗衫", "內搭衣", "衛生衣", "發熱衣", "吊帶內衣", "襯裙", "內搭背心"],
  ["undershirt", "innerwear vest", "innerwear vests", "slip", "chemise", "chemises", "thermal top"], gpt=(2745, "broader"),
  construction=K, hs={"knit": ["61.07", "61.08", "61.09"], "woven": ["62.07", "62.08"]})
N("intimates.shapewear", "塑身衣", "Shapewear", ["塑身衣", "塑身褲", "束腹", "束褲", "調整型內衣"], ["shapewear", "girdle", "corset"],
  gpt=(1578, "exact"), construction="mixed", hs={"any": ["62.12"]})
N("intimates.sleepwear", "睡衣", "Sleepwear", ["睡衣", "睡褲", "睡裙", "睡衣褲", "連身睡衣", "性感睡衣", "情侶睡衣"],
  ["sleepwear", "pajamas", "pyjamas", "night suit", "night suits", "nightdress", "nightgown", "baby dolls", "babydoll"],
  gpt=(208, "broader"), construction=K, hs={"knit": ["61.07", "61.08"], "woven": ["62.07", "62.08"]})
N("intimates.loungewear", "居家服", "Loungewear", ["居家服", "家居服", "休閒居家服", "居家褲"], ["loungewear", "lounge pants", "lounge shorts", "lounge top"],
  gpt=(5713, "exact"), construction=K, hs={"knit": ["61.07", "61.08"], "woven": ["62.07", "62.08"]})
N("intimates.robes", "睡袍/浴袍", "Robes", ["睡袍", "浴袍", "晨袍"], ["robe", "robes", "bath robe", "bathrobe", "dressing gown"],
  gpt=(2302, "exact"), construction="mixed", hs={"knit": ["61.07", "61.08"], "woven": ["62.07", "62.08"]})

# ------------------------------------------------------------------ L1: swimwear (Makalot "Others: Swimwear")
N("swimwear", "泳裝", "Swimwear", ["泳裝", "泳衣", "泳褲", "游泳衣"], ["swimwear", "swimsuit", "swimsuits", "bathing suit", "swim trunks"],
  gpt=(211, "exact"), legacy_coarse="other", apparel=True, construction=K, hs={"knit": ["61.12"], "woven": ["62.11"]})
N("swimwear.bikinis", "比基尼", "Bikinis", ["比基尼", "兩件式泳衣", "比基尼泳衣"], ["bikini", "bikinis", "bikini top", "bikini tops", "bikini bottoms"],
  gpt=(211, "broader"), construction=K, hs={"knit": ["61.12"], "woven": ["62.11"]})
N("swimwear.one_piece", "連身泳衣", "One-piece swimsuits", ["連身泳衣", "連身泳裝", "一件式泳衣"], ["one piece swimsuit", "one piece swimsuits", "one-piece swimsuit"],
  gpt=(211, "broader"), construction=K, hs={"knit": ["61.12"], "woven": ["62.11"]})
N("swimwear.cover_ups", "海灘罩衫", "Cover-ups", ["海灘罩衫", "泳裝罩衫", "沙灘罩衫", "罩衫"], ["cover-up", "cover-ups", "beach cover up", "kaftan"],
  gpt=(211, "broader"), construction="mixed")

# ------------------------------------------------------------------ L1: shoes
N("shoes", "鞋子", "Shoes", ["鞋子", "鞋款", "鞋"], ["shoe", "shoes", "footwear"], gpt=(187, "exact"), legacy_coarse="shoes",
  apparel=True, construction="non_textile")
N("shoes.athletic", "運動鞋/慢跑鞋", "Athletic shoes", ["運動鞋", "慢跑鞋", "跑鞋", "訓練鞋", "籃球鞋", "足球鞋", "網球鞋", "登山鞋", "健走鞋", "越野跑鞋"],
  ["sports shoes", "athletic shoes", "running shoes", "trainers", "training shoes", "basketball shoes"], gpt=(187, "broader"),
  collections=["coll.activewear"])
N("shoes.sneakers", "休閒鞋/球鞋", "Sneakers & casual shoes", ["休閒鞋", "球鞋", "板鞋", "帆布鞋", "小白鞋", "老爹鞋", "懶人鞋", "便鞋", "德訓鞋", "運動鞋"],
  ["sneakers", "sneaker", "casual shoes", "canvas shoes", "slip-ons", "plimsolls"], gpt=(187, "broader"))
N("shoes.dress_shoes", "皮鞋/紳士鞋", "Dress & formal shoes", ["皮鞋", "紳士鞋", "牛津鞋", "德比鞋", "正式皮鞋", "商務皮鞋", "雕花鞋"],
  ["formal shoes", "dress shoes", "oxfords", "oxford shoes", "derby shoes", "brogues"], gpt=(187, "broader"))
N("shoes.loafers", "樂福鞋", "Loafers & moccasins", ["樂福鞋", "莫卡辛鞋", "豆豆鞋", "帆船鞋", "穆勒鞋"], ["loafers", "loafer", "moccasins", "loafers & moccasins", "boat shoes", "mules"],
  gpt=(187, "broader"))
N("shoes.flats", "平底鞋/娃娃鞋", "Flats", ["平底鞋", "娃娃鞋", "芭蕾舞鞋", "瑪莉珍鞋"], ["flats", "ballet flats", "flat shoes"], gpt=(187, "broader"))
N("shoes.heels", "高跟鞋", "Heels & pumps", ["高跟鞋", "跟鞋", "細跟鞋", "粗跟鞋", "尖頭高跟鞋", "楔型鞋", "隱形增高鞋"], ["heels", "high heels", "pumps", "stilettos", "wedges"],
  gpt=(187, "broader"))
N("shoes.sandals", "涼鞋", "Sandals", ["涼鞋", "運動涼鞋", "羅馬涼鞋", "厚底涼鞋"], ["sandals", "sandal", "sports sandals", "gladiator sandals"], gpt=(187, "broader"))
N("shoes.slippers", "拖鞋/夾腳拖", "Slippers, flip-flops & clogs", ["拖鞋", "夾腳拖", "人字拖", "室內拖", "洞洞鞋", "涼拖鞋", "運動拖鞋"],
  ["flip flops", "flip-flops", "slippers", "slides", "clogs"], gpt=(187, "broader"))
N("shoes.boots", "靴子", "Boots", ["靴子", "短靴", "長靴", "踝靴", "馬丁靴", "雪靴", "過膝靴", "中筒靴", "雨靴", "切爾西靴", "工作靴", "靴"],
  ["boots", "boot", "ankle booties", "ankle boots", "knee high boots", "over-the-knee boots", "mid calf boots",
   "work boots", "chelsea boots"], gpt=(187, "broader"))

# ------------------------------------------------------------------ L1: bags & wallets
N("bags", "包包/皮夾", "Bags & wallets", ["包包", "包款", "提包", "=包"], ["bag", "bags", "bags & wallets", "bags & cases"],
  gpt=(6551, "broader"), legacy_coarse="bag", apparel=True, construction="non_textile",
  note="皮夾放在包包之下：GPT 'Handbags, Wallets & Cases'(6551)、蝦皮『包包>皮夾』、Yahoo『包包/皮夾』一致。")
N("bags.handbags", "手提包", "Handbags", ["手提包", "手提袋", "名牌包", "精品包"], ["handbag", "handbags", "purse", "top handle bag"], gpt=(3032, "exact"))
N("bags.shoulder_crossbody", "肩背包/斜背包", "Shoulder & crossbody bags", ["肩背包", "側背包", "斜背包", "郵差包", "單肩包", "斜肩包", "水桶包", "馬鞍包"],
  ["shoulder bag", "shoulder bags", "crossbody bag", "messenger bag", "messenger bags", "sling bag"], gpt=(106, "broader"))
N("bags.totes", "托特包", "Tote bags", ["托特包", "購物袋", "帆布袋", "環保袋"], ["tote", "tote bag", "tote bags", "shopper"], gpt=(5608, "broader"))
N("bags.clutches", "手拿包/晚宴包", "Clutches", ["手拿包", "晚宴包", "信封包"], ["clutch", "clutches", "evening bag"], gpt=(3032, "broader"))
N("bags.backpacks", "後背包", "Backpacks", ["後背包", "雙肩包", "背包", "書包", "登山包"], ["backpack", "backpacks", "rucksack", "rucksacks"], gpt=(100, "exact"))
N("bags.travel", "行李箱/旅行袋", "Luggage & travel bags", ["行李箱", "旅行袋", "登機箱", "行李袋", "旅行包", "健身包", "運動包"],
  ["luggage", "suitcase", "duffel bag", "duffle bag", "trolley bag", "travel bag", "gym bag"], gpt=(107, "broader"))
N("bags.work_laptop", "公事包/電腦包", "Briefcases & laptop bags", ["公事包", "電腦包", "筆電包", "商務包"], ["briefcase", "briefcases", "laptop bag", "tablet sleeve"],
  gpt=(101, "broader"))
N("bags.waist_pouches", "腰包/胸包/小包", "Waist bags & pouches", ["腰包", "胸包", "霹靂包", "手機包", "小包", "收納包"], ["waist pouch", "belt bag", "fanny pack", "mobile pouch", "pouch"],
  gpt=(104, "broader"))
N("bags.wallets", "皮夾/錢包", "Wallets", ["皮夾", "錢包", "長夾", "短夾", "零錢包", "卡夾", "名片夾", "鈔票夾"], ["wallet", "wallets", "money clip", "money clips", "card holder"],
  gpt=(2668, "exact"))

# ------------------------------------------------------------------ L1: accessories
N("accessories", "配件", "Accessories", ["配件", "配飾", "穿搭配件", "小物"], ["accessory", "accessories", "clothing accessories"], gpt=(167, "exact"),
  legacy_coarse="accessory", apparel=True)
N("accessories.watches", "手錶", "Watches", ["手錶", "腕錶", "錶", "機械錶", "石英錶", "智慧手錶"], ["watch", "watches", "wristwatch"], gpt=(201, "broader"),
  construction="non_textile", note="GPT 把 Watches 放在 Jewelry 之下；Fashionpedia、蝦皮、現行 coarse 皆當配件，沿用配件。")
N("accessories.eyewear", "眼鏡/太陽眼鏡", "Eyewear", ["眼鏡", "太陽眼鏡", "墨鏡", "太陽鏡", "鏡框", "光學眼鏡"], ["sunglasses", "eyeglasses", "eyewear", "glasses"],
  gpt=(178, "broader"), construction="non_textile")
N("accessories.belts", "皮帶/腰帶", "Belts & suspenders", ["皮帶", "腰帶", "吊帶", "腰封"], ["belt", "belts", "suspenders", "braces"], gpt=(169, "broader"),
  construction="non_textile")
N("accessories.hats", "帽子", "Hats & caps", ["帽子", "棒球帽", "鴨舌帽", "漁夫帽", "毛帽", "針織帽", "遮陽帽", "草帽", "貝雷帽", "紳士帽", "=帽"],
  ["hat", "hats", "cap", "caps", "beanie", "bucket hat"], gpt=(173, "exact"))
N("accessories.scarves", "圍巾/披肩", "Scarves, stoles & dupattas", ["圍巾", "披肩", "絲巾", "頸巾", "領巾", "脖圍", "方巾"],
  ["scarf", "scarves", "stole", "stoles", "muffler", "mufflers", "shawl", "dupatta"], gpt=(177, "exact"),
  construction="mixed", hs={"knit": ["61.17"], "woven": ["62.14"]})
N("accessories.gloves", "手套", "Gloves", ["手套", "袖套"], ["gloves", "glove", "mittens"], gpt=(170, "exact"), construction="mixed",
  hs={"knit": ["61.16"], "woven": ["62.16"]})
N("accessories.ties", "領帶/領結", "Ties & bow ties", ["領帶", "領結", "領片"], ["tie", "ties", "bow tie", "bow ties", "necktie"], gpt=(176, "exact"),
  construction=W, hs={"knit": ["61.17"], "woven": ["62.15"]})
N("accessories.hair", "髮飾", "Hair accessories", ["髮飾", "髮夾", "髮圈", "髮箍", "髮帶", "鯊魚夾", "頭巾"], ["hair accessories", "hair accessory", "headband", "hair clip", "scrunchie"],
  gpt=(171, "exact"))
N("accessories.socks", "襪子", "Socks", ["襪子", "短襪", "長襪", "船型襪", "中筒襪", "運動襪", "隱形襪", "=襪"], ["socks", "sock"], gpt=(209, "exact"), construction=K,
  hs={"knit": ["61.15"]})
N("accessories.hosiery", "絲襪/褲襪", "Hosiery & tights", ["絲襪", "褲襪", "膝上襪", "大腿襪", "網襪"], ["hosiery", "tights", "stockings", "pantyhose"], gpt=(215, "exact"),
  construction=K, hs={"knit": ["61.15"]})
N("accessories.tech", "手機殼/3C配件", "Tech accessories", ["手機殼", "手機套", "平板套", "耳機殼", "3C配件"], ["tech accessories", "phone case", "iphone case"],
  gpt=(2353, "broader"), construction="non_textile")
N("accessories.umbrellas", "雨傘/陽傘", "Umbrellas", ["雨傘", "陽傘", "晴雨傘", "折疊傘"], ["umbrella", "umbrellas"], gpt=(4358, "exact"), construction="non_textile")
N("accessories.keychains", "鑰匙圈/吊飾", "Key rings & chains", ["鑰匙圈", "吊飾", "鑰匙扣"], ["key chain", "keychain", "key rings & chains", "key ring"],
  gpt=(175, "exact"), construction="non_textile")

# ------------------------------------------------------------------ L1: jewelry
N("jewelry", "飾品/珠寶", "Jewelry", ["飾品", "首飾", "珠寶", "金飾", "銀飾"], ["jewelry", "jewellery"], gpt=(188, "exact"), legacy_coarse="jewelry",
  apparel=True, construction="non_textile")
N("jewelry.earrings", "耳環", "Earrings", ["耳環", "耳針", "耳夾", "耳骨夾", "耳扣"], ["earring", "earrings", "studs", "hoops"], gpt=(194, "exact"))
N("jewelry.necklaces", "項鍊/墜飾", "Necklaces & pendants", ["項鍊", "項鏈", "頸鍊", "鎖骨鍊", "墜子", "吊墜", "墜飾"], ["necklace", "necklaces", "pendant", "chain", "charms & pendants"],
  gpt=(196, "exact"))
N("jewelry.bracelets", "手環/手鍊", "Bracelets & bangles", ["手環", "手鍊", "手鐲", "手鏈"], ["bracelet", "bracelets", "bangle", "bangles"], gpt=(191, "exact"))
N("jewelry.rings", "戒指", "Rings", ["戒指", "對戒", "尾戒", "婚戒"], ["ring", "rings"], gpt=(200, "exact"))
N("jewelry.brooches", "胸針", "Brooches & pins", ["胸針", "別針", "胸花"], ["brooch", "brooches", "pin"], gpt=(197, "exact"))
N("jewelry.cufflinks", "袖扣", "Cufflinks", ["袖扣"], ["cufflinks", "cuff links"], gpt=(193, "broader"),
  note="GPT 把 Cufflinks 放在 Clothing Accessories；Polyvore 放 Watches & Jewelry、現行 coarse=jewelry，沿用飾品。")
N("jewelry.sets", "飾品組", "Jewellery sets", ["飾品組", "首飾套組", "珠寶套組"], ["jewellery set", "jewelry set"], gpt=(6463, "exact"))

# ------------------------------------------------------------------ L1: beauty & personal care (non-apparel)
N("beauty", "美妝保養", "Beauty & personal care", ["美妝", "美妝保養", "保養品", "化妝品", "彩妝保養"], ["beauty", "beauty products", "personal care", "makeup"],
  gpt=(2915, "exact"), legacy_coarse="other", apparel=False,
  note="非服飾。保留節點是為了能明確『排除』它們（KAGL 約 6%、Polyvore 約 12% 是美妝），而不是推薦。")
N("beauty.makeup", "彩妝", "Makeup", ["彩妝", "口紅", "唇膏", "唇蜜", "眼影", "眼線", "睫毛膏", "粉底", "腮紅", "遮瑕", "蜜粉", "修容", "打亮", "眉筆", "假睫毛"],
  ["lipstick", "lip gloss", "eyeliner", "eyeshadow", "mascara", "foundation", "blush", "concealer"], gpt=(477, "exact"))
N("beauty.nails", "美甲", "Nail care", ["指甲油", "美甲", "凝膠指甲"], ["nail polish", "nail care"], gpt=(478, "exact"))
N("beauty.skincare", "保養", "Skin care", ["乳液", "化妝水", "面膜", "防曬乳", "洗面乳", "精華液", "乳霜", "卸妝", "護唇膏"], ["skincare", "skin care", "moisturiser", "sunscreen", "toner"],
  gpt=(567, "exact"))
N("beauty.fragrance", "香水/體香", "Fragrance & deodorant", ["香水", "香氛", "體香劑", "止汗劑", "淡香水"], ["perfume", "fragrance", "deodorant", "body mist"],
  gpt=(479, "broader"))
N("beauty.haircare", "美髮", "Hair care & styling", ["洗髮精", "潤髮乳", "染髮劑", "吹風機", "離子夾", "髮蠟", "造型品"], ["haircare", "hair colour", "hair color", "shampoo", "conditioner"],
  gpt=(486, "exact"))
N("beauty.bath_body", "身體清潔保養", "Bath & body", ["沐浴乳", "身體乳", "身體清潔", "去角質"], ["body lotion", "body wash", "bath & body", "body cleanser"],
  gpt=(2915, "broader"))
N("beauty.tools", "美妝工具", "Beauty tools", ["化妝刷", "睫毛夾", "粉撲", "美妝蛋", "眉夾"], ["makeup brushes", "eyelash curler", "beauty accessory", "tweezers"],
  gpt=(2915, "broader"))

# ---------------------------------------------------------------------------------------------
# cross-cutting collections (not part of the relaxation ladder; applied as an intersection facet)
# ---------------------------------------------------------------------------------------------
COLLECTIONS = [
    dict(id="coll.activewear", label_en="Activewear / functional sportswear", label_zh="運動機能服飾",
         synonyms_zh=["運動服", "運動服飾", "運動風", "機能服", "機能", "運動休閒", "健身", "健身房", "瑜珈", "瑜伽", "慢跑", "跑步", "運動", "戶外機能", "排汗"],
         synonyms_en=["activewear", "sportswear", "athleisure", "athletic", "gym", "workout", "running", "training", "performance", "yoga"],
         gpt={"id": 5322, "match": "broader"},
         extra_source_values={
             "kagl": ["Sports Sandals", "Wristbands"],
             "polyvore": ["Activewear", "Activewear Shorts", "Activewear Skirts", "Activewear Jackets", "Men's Activewear Jackets",
                          "Men's Activewear Pants", "Men's Activewear Tops"]},
         note="聚陽 2025 營收 52% 為 Functional Sportswear；但『運動』是跨部位的橫切屬性（運動上衣/運動褲/運動內衣/運動鞋），"
              "若做成 L1 會讓『黑色短褲』放寬時找不到運動短褲，也會破壞 Kansei 適用遮罩與搭配槽位。"),
    dict(id="coll.ethnic", label_en="South-Asian ethnic wear", label_zh="印度傳統服飾",
         synonyms_zh=["印度傳統服飾", "印度服飾", "南亞傳統服飾"], synonyms_en=["ethnic wear", "indian wear", "traditional indian"],
         gpt={"id": 5388, "match": "broader"},
         extra_source_values={"kagl": ["Dupatta", "Nehru Jackets"], "polyvore": []},
         note="KAGL（Myntra）特有；台灣使用者極少查詢。服裝仍依部位掛在 tops/bottoms/dresses/sets。"),
]

# ---------------------------------------------------------------------------------------------
# source maps. value -> (target, status, reason). target: node id | collection id | None
#   status: mapped (L2) | mapped_l1 (generic source label, only L1 known) | collection | non_apparel | unmapped
# ---------------------------------------------------------------------------------------------
def m(t, reason=None):
    return (t, "mapped_l1" if "." not in t else "mapped", reason)


def na(reason):
    return (None, "non_apparel", reason)


def um(reason):
    return (None, "unmapped", reason)


KAGL = {
    # tops
    "Tshirts": m("tops.tshirts"), "Shirts": m("tops.shirts"), "Tops": m("tops", "KAGL 'Tops' = 女裝泛用上衣，無法再細分"),
    "Kurtas": m("tops.kurtas"), "Kurtis": m("tops.kurtas"), "Tunics": m("tops.tunics"), "Sweatshirts": m("tops.sweatshirts_hoodies"),
    "Sweaters": m("tops.sweaters"), "Rompers": um("KAGL Rompers 全是嬰兒包屁衣（標題 'Infant Boys ... Snapsuit Romper'）；童裝不在目錄受眾"),
    "Belts": m("accessories.belts"),
    # bottoms
    "Jeans": m("bottoms.jeans"), "Jeggings": m("bottoms.jeans", "jeggings = 牛仔感內搭褲；歸牛仔褲以對齊 Polyvore 的 jeans 細類"),
    "Trousers": m("bottoms.trousers"), "Track Pants": m("bottoms.track_pants"), "Shorts": m("bottoms.shorts"),
    "Skirts": m("bottoms.skirts"), "Capris": m("bottoms.capris"), "Leggings": m("bottoms.leggings"),
    "Tights": m("bottoms.leggings", "混雜：Nike 訓練緊身褲與 Happy Socks 褲襪；多數為運動緊身褲"),
    "Patiala": m("bottoms.ethnic_bottoms"), "Salwar": m("bottoms.ethnic_bottoms"), "Churidar": m("bottoms.ethnic_bottoms"),
    "Salwar and Dupatta": m("sets.ethnic_sets"), "Rain Trousers": m("outerwear.rainwear"),
    # dresses
    "Dresses": m("dresses.dresses"), "Jumpsuit": m("dresses.jumpsuits_rompers"), "Sarees": m("dresses.sarees_lehengas"),
    "Lehenga Choli": m("dresses.sarees_lehengas"),
    # outerwear
    "Jackets": m("outerwear.jackets"), "Blazers": m("outerwear.blazers"), "Rain Jacket": m("outerwear.jackets"),
    "Nehru Jackets": m("outerwear.jackets", "Fashionpedia 把 nehru 列為 jacket 的 nickname"), "Waistcoat": m("outerwear.vests"),
    "Shrug": m("outerwear.jackets", "Fashionpedia: bolero 屬 jacket"),
    # sets
    "Kurta Sets": m("sets.ethnic_sets"), "Tracksuits": m("sets.tracksuits"), "Clothing Set": m("sets.clothing_sets"),
    # intimates / sleep / lounge / swim
    "Briefs": m("intimates.underwear"), "Boxers": m("intimates.underwear"), "Trunk": m("intimates.underwear", "標題為 'Boxer ... Trunks'"),
    "Bra": m("intimates.bras"), "Innerwear Vests": m("intimates.undershirts"), "Camisoles": m("intimates.undershirts", "KAGL 的 Camisoles 在 Innerwear 下（Jockey 等內搭）"),
    "Shapewear": m("intimates.shapewear"), "Night suits": m("intimates.sleepwear"), "Nightdress": m("intimates.sleepwear"),
    "Baby Dolls": m("intimates.sleepwear"), "Lounge Pants": m("intimates.loungewear"), "Lounge Shorts": m("intimates.loungewear"),
    "Lounge Tshirts": m("intimates.loungewear"), "Robe": m("intimates.robes"), "Bath Robe": m("intimates.robes"),
    "Swimwear": m("swimwear", "泛用泳裝"),
    # shoes
    "Casual Shoes": m("shoes.sneakers"), "Sports Shoes": m("shoes.athletic"), "Formal Shoes": m("shoes.dress_shoes"),
    "Heels": m("shoes.heels"), "Flats": m("shoes.flats"), "Sandals": m("shoes.sandals"), "Sports Sandals": m("shoes.sandals"),
    "Flip Flops": m("shoes.slippers"), "Booties": um("KAGL Booties 全是嬰兒鞋（'Infant Boys ... Booties'）；童裝不在目錄受眾"),
    # bags
    "Handbags": m("bags.handbags"), "Backpacks": m("bags.backpacks"), "Rucksacks": m("bags.backpacks"), "Clutches": m("bags.clutches"),
    "Duffel Bag": m("bags.travel"), "Trolley Bag": m("bags.travel"), "Laptop Bag": m("bags.work_laptop"), "Tablet Sleeve": m("bags.work_laptop"),
    "Messenger Bag": m("bags.shoulder_crossbody"), "Mobile Pouch": m("bags.waist_pouches"), "Waist Pouch": m("bags.waist_pouches"),
    "Wallets": m("bags.wallets"), "Travel Accessory": m("bags", "標題實為 'United Colors of Benetton ... Bags'"),
    # accessories
    "Watches": m("accessories.watches"), "Sunglasses": m("accessories.eyewear"), "Socks": m("accessories.socks"),
    "Caps": m("accessories.hats"), "Hat": m("accessories.hats"), "Ties": m("accessories.ties"), "Scarves": m("accessories.scarves"),
    "Stoles": m("accessories.scarves"), "Mufflers": m("accessories.scarves"), "Dupatta": m("accessories.scarves"), "Gloves": m("accessories.gloves"),
    "Stockings": m("accessories.hosiery"), "Suspenders": m("accessories.belts"), "Umbrellas": m("accessories.umbrellas"),
    "Headband": m("accessories.hair"), "Hair Accessory": m("accessories.hair"), "Key chain": m("accessories.keychains"),
    "Wristbands": m("accessories", "運動腕帶（Nike/Puma）"), "Shoe Accessories": m("accessories", "鞋墊/鞋用品"),
    "Shoe Laces": m("accessories", "鞋帶"), "Accessory Gift Set": m("accessories", "領帶+袖扣+口袋巾組合"),
    "Ties and Cufflinks": m("accessories.ties", "領帶與袖扣組合，以主件領帶歸類"),
    # jewelry
    "Earrings": m("jewelry.earrings"), "Pendant": m("jewelry.necklaces"), "Necklace and Chains": m("jewelry.necklaces"),
    "Ring": m("jewelry.rings"), "Bangle": m("jewelry.bracelets"), "Bracelet": m("jewelry.bracelets"), "Jewellery Set": m("jewelry.sets"),
    "Cufflinks": m("jewelry.cufflinks"),
    # beauty
    **{v: m("beauty.makeup") for v in ["Lipstick", "Lip Gloss", "Lip Liner", "Kajal and Eyeliner", "Eyeshadow", "Mascara",
                                       "Foundation and Primer", "Highlighter and Blush", "Concealer", "Compact", "Lip Plumper"]},
    **{v: m("beauty.nails") for v in ["Nail Polish", "Nail Essentials"]},
    **{v: m("beauty.skincare") for v in ["Face Moisturisers", "Sunscreen", "Eye Cream", "Toner", "Face Wash and Cleanser", "Mask and Peel",
                                         "Lip Care", "Makeup Remover", "Face Serum and Gel", "Face Scrub and Exfoliator"]},
    **{v: m("beauty.fragrance") for v in ["Perfume and Body Mist", "Deodorant", "Fragrance Gift Set"]},
    "Hair Colour": m("beauty.haircare"), "Body Lotion": m("beauty.bath_body"), "Body Wash and Scrub": m("beauty.bath_body"),
    "Beauty Accessory": m("beauty.tools"), "Mens Grooming Kit": m("beauty", "男士理容組"),
    # non-apparel / unmapped
    "Free Gifts": um("贈品桶：手錶、球衣、包混雜，無單一類別"), "Water Bottle": na("運動水壺"), "Footballs": na("運動器材"),
    "Basketballs": na("運動器材"), "Ipad": na("電子產品"), "Cushion Covers": na("居家織品"),
}

POLY_HOME = ["Accent Tables", "Floral Decor", "Home Decor", "Accent Chairs", "Ceiling Lights", "Rugs", "Sofas", "Throw Pillows", "Blankets",
             "Drinkware", "Candles & Candleholders", "Table Lamps", "Mirrors", "Serveware", "Clocks", "Holiday Decorations", "Kitchen & Dining",
             "Floor Lamps", "Frames", "Small Storage", "Bath Accessories", "Bookcases", "Curtains", "Outdoor Lighting", "Sideboards", "Tables",
             "Vases", "Wall Lights", "Bar Cabinets", "Beach Towels", "Beds", "Benches", "Chairs", "Children's Bedding", "Dining Chairs",
             "Dressers", "Flatware", "Food Storage Containers", "Furniture", "Lighting", "Nightstands", "Ottomans", "Outdoor Benches",
             "Shower Curtains", "Standing Fans", "Storage & Shelves", "Table Linens", "Wallpaper", "Outdoor Decor", "Kitchen Gadgets & Tools",
             "Bar Tools", "Dining Tables", "Bath Towels", "Dinnerware", "Teapots", "Cabinets", "Cutlery", "Desks", "Kitchen Linens",
             "Outdoor Tables", "Patio Furniture", "Patio Umbrellas", "Sheets & Pillowcases", "Small Appliances", "Baby Bedding",
             "Bed Accessories", "Bed Pillows", "Children's Decor", "Children's Furniture", "Comforters", "Duvet Covers", "Hammocks & Swings",
             "Napkin Rings", "Outdoor Loungers & Day Beds", "Aprons", "Bakeware", "Bath Rugs & Mats", "Cleaning", "Cookware", "Curtain Rods",
             "Desk Lamps", "File Cabinets", "Fireplace Accessories", "Office Chairs", "Outdoor Stools", "Quilts & Coverlets", "Stools",
             "Storage & Organization", "Home Fragrance", "Jewelry Storage", "Home Improvement", "Cookbooks"]
POLY_OTHER_NA = {"Font": "Polyvore 拼貼用文字圖", "Electronics": "電子產品", "Stationery": "文具", "Food & Drink": "食品", "Toys": "玩具",
                 "Media": "媒體", "Books": "書籍", "Office Accessories": "辦公用品", "Pets": "寵物用品", "Sports & Outdoors": "運動戶外器材",
                 "Outdoors": "戶外用品", "Party Supplies": "派對用品", "Health": "保健", "Sharpeners": "文具",
                 "Sports Accessories": "運動器材（1 件）"}

POLYVORE_BASE = {  # keys are the label with any "Men's " prefix removed
    "Tops": m("tops", "Polyvore 'Tops' 為泛用上衣"), "Blouses": m("tops.blouses"), "T-Shirts": m("tops.tshirts"), "Tank Tops": m("tops.tanks_camis"),
    "Camisoles": m("tops.tanks_camis"), "Sweaters": m("tops.sweaters"), "Cardigans": m("tops.cardigans"), "Sweatshirts": m("tops.sweatshirts_hoodies"),
    "Hoodies": m("tops.sweatshirts_hoodies"), "Tunics": m("tops.tunics"), "Polos": m("tops.polos"), "Shirts": m("tops.shirts"),
    "Casual Shirts": m("tops.shirts"), "Dress Shirts": m("tops.shirts"), "Activewear Tops": m("tops.active_tops"),
    "Activewear Tank Tops": m("tops.active_tops"),
    "Pants": m("bottoms.trousers"), "Casual Pants": m("bottoms.trousers"), "Dress Pants": m("bottoms.trousers"), "Shorts": m("bottoms.shorts"),
    "Leggings": m("bottoms.leggings"), "Jeans": m("bottoms.jeans"), "Skinny Jeans": m("bottoms.jeans"), "Boyfriend Jeans": m("bottoms.jeans"),
    "Straight Leg Jeans": m("bottoms.jeans"), "Flared Jeans": m("bottoms.jeans"), "Bootcut Jeans": m("bottoms.jeans"),
    "Wide Leg Jeans": m("bottoms.jeans"), "Capri & Cropped Pants": m("bottoms.capris"), "Skirts": m("bottoms.skirts"),
    "Mini Skirts": m("bottoms.skirts"), "Knee Length Skirts": m("bottoms.skirts"), "Long Skirts": m("bottoms.skirts"),
    "Activewear Pants": m("bottoms.track_pants"), "Activewear Shorts": m("bottoms.shorts"), "Activewear Skirts": m("bottoms.skirts"),
    "Dresses": m("dresses.dresses"), "Day Dresses": m("dresses.dresses"), "Cocktail Dresses": m("dresses.party_dresses"),
    "Gowns": m("dresses.gowns"), "Wedding Dresses": m("dresses.gowns"), "Rompers": m("dresses.jumpsuits_rompers"),
    "Jumpsuits": m("dresses.jumpsuits_rompers"),
    "Jackets": m("outerwear.jackets"), "Coats": m("outerwear.coats"), "Blazers": m("outerwear.blazers"),
    "Sportcoats & Blazers": m("outerwear.blazers"), "Outerwear": m("outerwear", "泛用外套"), "Vests": m("outerwear.vests"),
    "Activewear Jackets": m("outerwear.jackets"), "Suits": m("sets.suits"),
    "Bras": m("intimates.bras"), "Sports Bras": m("intimates.sports_bras"), "Panties & Thongs": m("intimates.underwear"),
    "Underwear": m("intimates.underwear"), "Shapewear": m("intimates.shapewear"), "Chemises": m("intimates.undershirts"),
    "Pajamas": m("intimates.sleepwear"), "Robes": m("intimates.robes"), "Intimates": m("intimates", "泛用內著（抽樣標題含褲襪、cami，雜訊高）"),
    "Bikinis": m("swimwear.bikinis"), "Bikini Tops": m("swimwear.bikinis"), "Bikini Bottoms": m("swimwear.bikinis"),
    "One Piece Swimsuits": m("swimwear.one_piece"), "Cover-ups": m("swimwear.cover_ups"), "Swimwear": m("swimwear", "泛用泳裝"),
    "Shoes": m("shoes", "泛用鞋"), "Sandals": m("shoes.sandals"), "Pumps": m("shoes.heels"), "Ankle Booties": m("shoes.boots"),
    "Boots": m("shoes.boots"), "Knee High Boots": m("shoes.boots"), "Over-The-Knee Boots": m("shoes.boots"), "Mid Calf Boots": m("shoes.boots"),
    "Work Boots": m("shoes.boots"), "Sneakers": m("shoes.sneakers"), "Athletic Shoes": m("shoes.athletic"), "Flats": m("shoes.flats"),
    "Loafers & Moccasins": m("shoes.loafers"), "Oxfords": m("shoes.dress_shoes"), "Dress Shoes": m("shoes.dress_shoes"),
    "Slippers": m("shoes.slippers"), "Flip Flops": m("shoes.slippers"), "Clogs": m("shoes.slippers"),
    "Bags": m("bags", "泛用包"), "Shoulder Bags": m("bags.shoulder_crossbody"), "Clutches": m("bags.clutches"), "Handbags": m("bags.handbags"),
    "Tote Bags": m("bags.totes"), "Backpacks": m("bags.backpacks"), "Messenger Bags": m("bags.shoulder_crossbody"), "Luggage": m("bags.travel"),
    "Briefcases": m("bags.work_laptop"), "Bags & Cases": m("bags", "泛用包"), "Wallets": m("bags.wallets"), "Money Clips": m("bags.wallets"),
    "Jewelry": m("jewelry", "泛用飾品"), "Earrings": m("jewelry.earrings"), "Necklaces": m("jewelry.necklaces"),
    "Bracelets & Bangles": m("jewelry.bracelets"), "Bracelets": m("jewelry.bracelets"), "Rings": m("jewelry.rings"), "Brooches": m("jewelry.brooches"),
    "Charms & Pendants": m("jewelry.necklaces"), "Cuff Links": m("jewelry.cufflinks"), "Watches & Jewelry": m("jewelry", "手錶與飾品混合"),
    "Accessories": m("accessories", "泛用配件"), "Sunglasses": m("accessories.eyewear"), "Eyeglasses": m("accessories.eyewear"),
    "Eyewear": m("accessories.eyewear"), "Hats": m("accessories.hats"), "Scarves": m("accessories.scarves"), "Belts": m("accessories.belts"),
    "Gloves": m("accessories.gloves"), "Hair Accessories": m("accessories.hair"), "Socks": m("accessories.socks"), "Tights": m("accessories.hosiery"),
    "Hosiery": m("accessories.hosiery"), "Ties": m("accessories.ties"), "Bow Ties": m("accessories.ties"), "Suspenders": m("accessories.belts"),
    "Umbrellas": m("accessories.umbrellas"), "Watches": m("accessories.watches"), "Tech Accessories": m("accessories.tech"),
    "Key Rings & Chains": m("accessories.keychains"), "Handkerchiefs": m("accessories", "手帕"),
    "Activewear": ("coll.activewear", "collection", "Polyvore 泛用運動類（運動內衣、跑步背心、慢跑褲混雜）只能對到橫切集合"),
    # beauty
    **{v: m("beauty.makeup") for v in ["Lipstick", "Eyeshadow", "Mascara", "Eyeliner", "Lip Gloss", "Blush", "Eye Makeup", "Face Powder",
                                       "Lip Makeup", "Foundation", "False Eyelashes", "Face Makeup", "Cheek Bronzer", "Concealer",
                                       "Makeup Primer", "Lip Pencils", "Lip Stain", "Tinted Moisturizer", "Cheek Makeup"]},
    **{v: m("beauty.nails") for v in ["Nail Polish", "Nail Treatments", "Nail Care", "Manicure Tools"]},
    **{v: m("beauty.skincare") for v in ["Lip Treatments", "Sun Care", "Face Care", "Face Masks", "Face Moisturizers", "Face Cleansers",
                                         "Eye Care", "Skincare", "Makeup Remover"]},
    **{v: m("beauty.fragrance") for v in ["Fragrance", "Deodorant"]},
    **{v: m("beauty.haircare") for v in ["Hair Styling Tools", "Haircare", "Styling Products", "Brushes & Combs", "Hair Color",
                                         "Blow Dryers & Irons", "Hair Shampoo", "Hair Conditioner", "Hair Care"]},
    **{v: m("beauty.bath_body") for v in ["Body Cleansers", "Body Moisturizers", "Bath & Body"]},
    **{v: m("beauty.tools") for v in ["Makeup Brushes", "Eyelash Curlers", "Makeup Tools", "Tweezers & Brow Tools", "Beauty Accessories"]},
    "Beauty Products": m("beauty", "泛用美妝"), "Makeup": m("beauty.makeup"), "Gift Sets & Kits": m("beauty", "美妝禮盒"),
    "Grooming": m("beauty", "男士理容"), "Body Art": m("beauty", "紋身貼"),
    # unmapped: generic or audience buckets
    "Clothing": um("泛用『服飾』：抽樣標題含西裝外套、毛衣洋裝、跑步外套、背心，無單一部位"),
    "Fashion": um("泛用 Men's Fashion"), "Kids": um("童裝/年齡層桶，非部位（抽樣含太陽眼鏡、後背包）"),
    "Girls": um("童裝年齡層桶"), "Boys": um("童裝年齡層桶"), "Baby": um("嬰兒桶"), "Juniors": um("青少年尺碼桶"),
    "Maternity": um("孕婦裝桶，非部位"), "Costumes": um("變裝服"),
    **{v: na("居家/家具/廚房") for v in POLY_HOME},
    **{k: na(v) for k, v in POLY_OTHER_NA.items()},
}


def polyvore_decision(value: str):
    key = re.sub(r"^Men's\s+", "", value)
    if key in POLYVORE_BASE:
        return POLYVORE_BASE[key]
    if value in POLYVORE_BASE:
        return POLYVORE_BASE[value]
    return None


# ---------------------------------------------------------------------------------------------
def _source_of(catalog: str, row: list) -> str:
    """Rows of merged catalogs carry the parquet `source` column as 4th element."""
    if len(row) > 3 and row[3]:
        return "kagl" if "kagl" in row[3].lower() or "fashion-product" in row[3].lower() else "polyvore"
    return "kagl" if catalog.startswith("kagl") else "polyvore"


def load_gpt(path):
    out = {}
    if not path:
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        mm = re.match(r"^(\d+) - (.+)$", line)
        if mm:
            out[int(mm.group(1))] = mm.group(2)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", required=True)
    ap.add_argument("--gpt", default=None)
    ap.add_argument("--gpt-zh", default=None)
    ap.add_argument("--out-dir", default="engine02/resources")
    ap.add_argument("--report", default="reports/agents/taxonomy/build_report.json")
    args = ap.parse_args(argv)

    gpt, gpt_zh = load_gpt(args.gpt), load_gpt(args.gpt_zh)
    ids = {n["id"] for n in NODES}
    assert len(ids) == len(NODES), "duplicate node id"
    for n in NODES:
        if n["parent"]:
            assert n["parent"] in ids, n
        if n["level"] == 1:
            n["attributes"] = L1_ATTRS[n["id"]]
        root = NODES[[x["id"] for x in NODES].index(n["id"].split(".")[0])]
        n.setdefault("apparel", root["apparel"])
        n.setdefault("legacy_coarse", root["legacy_coarse"])
        if n["gpt"] and gpt:
            gid = n["gpt"]["id"]
            if gid not in gpt:
                sys.exit(f"GPT id {gid} for {n['id']} not in taxonomy file")
            n["gpt"]["path_en"] = gpt[gid]
            if gid in gpt_zh:
                n["gpt"]["path_zh_cn"] = gpt_zh[gid]
    for c in COLLECTIONS:
        if gpt and c["gpt"]["id"] in gpt:
            c["gpt"]["path_en"] = gpt[c["gpt"]["id"]]
        c["members"] = [n["id"] for n in NODES if c["id"] in n.get("collections", [])]

    counts = json.loads(Path(args.counts).read_text(encoding="utf-8"))
    catalogs_of = {"kagl": ["kagl", "kagl_full"], "polyvore": ["polyvore", "polyvore_big"]}
    # kagl_polyvore rows carry both vocabularies; each row is attributed via its `source` column
    tax = dict(
        version=VERSION, created="2026-09-17",
        description="ENGINE 02 category taxonomy: L1 garment slot -> L2 garment type; cross-cutting collections; "
                    "per-source subcategory maps in taxonomy_map_{kagl,polyvore}.json. See docs/research/taxonomy.md.",
        sources={
            "google_product_taxonomy": "https://www.google.com/basepages/producttype/taxonomy-with-ids.en-US.txt (Version 2021-09-21; zh-TW file 404, zh-CN used for reference)",
            "fashionpedia": "Jia et al., ECCV 2020, arXiv:2004.12276; categories from instances_attributes_val2020.json",
            "hs2022": "WCO HS Nomenclature 2022, Chapters 61 and 62 (wcoomd.org PDFs 1161_2022e / 1162_2022e)",
            "makalot": "Makalot 2026 investor presentation (product lines p.5, revenue mix p.8)",
            "shopee_tw": "https://shopee.tw/api/v4/pages/get_category_tree (fetched 2026-09-17)",
            "yahoo_shopping_tw": "https://tw.buy.yahoo.com/ category menu (fetched 2026-09-17)",
        },
        relaxation="L2 -> L1 -> (none). Collections are intersections and are dropped, never generalised.",
        attribute_defs=ATTRIBUTE_DEFS, nodes=NODES, collections=COLLECTIONS,
    )

    all_values = defaultdict(lambda: defaultdict(dict))  # source -> value -> {catalog: {coarse: n}}
    for cat, blob in counts.items():
        for row in blob["rows"]:
            sub, coarse, n = row[:3]
            if sub is None:
                continue
            s = _source_of(cat, row)
            all_values[s][sub].setdefault(cat, {})
            all_values[s][sub][cat][coarse or "null"] = all_values[s][sub][cat].get(coarse or "null", 0) + n

    report = {"missing_decisions": {}, "coverage": {}, "disagreements": [], "cross_source_conflicts": []}
    for source in ("kagl", "polyvore"):
        entries = {}
        missing = []
        for value in sorted(all_values[source]):
            dec = KAGL.get(value) if source == "kagl" else polyvore_decision(value)
            if dec is None:
                missing.append(value)
                continue
            target, status, reason = dec
            if target and target not in ids and target not in {c["id"] for c in COLLECTIONS}:
                sys.exit(f"{source}:{value} -> unknown target {target}")
            node = next((n for n in NODES if n["id"] == target), None)
            implied = node["legacy_coarse"] if node else None
            e = dict(node=target, status=status, counts=all_values[source][value])
            if reason:
                e["reason"] = reason
            e["implied_coarse"] = implied
            entries[value] = e
            for cat, by_coarse in all_values[source][value].items():
                for coarse, n in by_coarse.items():
                    if status in ("non_apparel", "unmapped", "collection"):
                        agree = coarse in ("other",)  # legacy 'other' is the honest bucket for these
                    else:
                        agree = coarse == implied
                    if not agree:
                        report["disagreements"].append(dict(source=source, value=value, catalog=cat, legacy=coarse,
                                                            taxonomy=target or status, implied_coarse=implied, n=n))
        report["missing_decisions"][source] = missing
        payload = dict(taxonomy_version=VERSION, source=source,
                       field="subcategory" + (" (= KAGL category3 / articleType)" if source == "kagl" else " (= Polyvore site category)"),
                       catalogs=catalogs_of[source] + ["kagl_polyvore"],
                       statuses={"mapped": "L2 node", "mapped_l1": "generic source label; L1 node only",
                                 "collection": "cross-cutting collection only", "non_apparel": "not clothing/accessory/beauty",
                                 "unmapped": "clothing-related but no garment type (generic or age-group bucket)"},
                       entries=entries)
        Path(args.out_dir, f"taxonomy_map_{source}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if any(report["missing_decisions"].values()):
        sys.exit(f"missing decisions: {report['missing_decisions']}")

    kv = {v: KAGL[v][0] for v in all_values["kagl"]}
    pv = {v: polyvore_decision(v)[0] for v in all_values["polyvore"]}
    for v in sorted(set(kv) & set(pv)):
        if kv[v] != pv[v]:
            report["cross_source_conflicts"].append(dict(value=v, kagl=kv[v], polyvore=pv[v]))

    for cat, blob in counts.items():
        tot = blob["n"]
        agg = defaultdict(int)
        for row in blob["rows"]:
            sub, coarse, n = row[:3]
            if sub is None:
                agg["null_subcategory"] += n
                continue
            dec = KAGL.get(sub) if _source_of(cat, row) == "kagl" else polyvore_decision(sub)
            agg[dec[1]] += n
        report["coverage"][cat] = dict(n=tot, **{k: v for k, v in sorted(agg.items())},
                                       share_mapped_l2=round(agg["mapped"] / tot, 4),
                                       share_mapped_any=round((agg["mapped"] + agg["mapped_l1"] + agg["collection"]) / tot, 4),
                                       share_decided=round((tot - agg.get("null_subcategory", 0)) / tot, 4))
    Path(args.out_dir, "taxonomy_v1.json").write_text(json.dumps(tax, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report["coverage"], indent=1))
    print("disagreement rows:", len(report["disagreements"]), "cross-source conflicts:", report["cross_source_conflicts"])


if __name__ == "__main__":
    main()
