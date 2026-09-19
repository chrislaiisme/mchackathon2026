"""六宮格生圖的共用邏輯：ENGINE01 的 `Intent` → 每格關鍵字 → 一段 prompt，以及 manifest 的形狀。

這支模組不碰網路、不碰生圖，純粹是「把意圖翻成畫得出來的英文描述」＋「記帳」。
生圖在 generate_grid.py，切圖在 slice_grid.py，檢查在 check_cells.py。

為什麼要有這層翻譯：ENGINE01 吐的是繁體中文（`item_type: "裙子"`、`fit: "寬鬆"`），
而生圖模型對英文服裝術語的反應明顯比較準；更重要的是，中文字直接塞進 prompt 有機會
被模型「畫」進圖裡變成文字，而我們整張圖是禁止出現任何文字的。

**這裡的對照表不是給人擴充行業詞的地方。** 翻不出來的字（「華夫格」「韓系」「cleanfit」）
會被記進 manifest 的 `unresolved`，那是回報給線 1 的訊號——行業詞 → 屬性的對應是設計師詞表
（`agent/skills/shared/glossary.md`）的職責，由線 1 維護。這條線只負責「拿到的關鍵字怎麼畫」，
不負責「這個詞是什麼意思」；在這裡偷偷補詞等於把同一份詞表養成兩份，遲早漂移。

翻譯表刻意**重用 engine02 現成的**（`intent_adapter` 的 ZH_* 表、`taxonomy` 的
attribute_defs 與分類體系），不另外發明一套。理由是生成出來的概念圖最後會轉成向量併回
ENGINE02 的 dense 分數（見 docs/pinterest-and-generation.md），兩邊講同一套詞彙，
分數才有可比性；各自維護一份詞表遲早會漂移。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine02.intent_adapter import (  # noqa: E402
    DESIGN_PHRASES, ELEMENT_EN, ZH_COLOR_EXACT, ZH_OCCASION, ZH_SEASON, _zh_lookup)
from engine02.taxonomy import load_taxonomy, resolve_category_values  # noqa: E402

# ── 固定不動的攝影規格 ────────────────────────────────────────────────────────
# 這段是整個機制的地基：**每一輪、每一格都逐字相同**。只有它一字不改，跨輪的圖才有
# 可比性，使用者回饋「第 3 格的顏色不對」才真的只在講顏色，而不是在講模型這次換了打光。
# 2026-09-19 實測（evals/choice_images/）就是用這段的雛形，六格 gutter 誤差 ≤0.2%、
# 切出來的格子尺寸全等，所以改這段之前請先重跑一次驗證。
#
# 三件事是為了「切得動」而寫的，不是美術偏好：
#   1. 純白 gutter —— slice_grid.py 靠投影法找它，灰底上的白帶對比夠大才偵測得準。
#   2. 每格同樣的取景與比例 —— 切完六張卡片才會一樣大，前端不用再縮放。
#   3. 禁止文字 —— 生圖模型很愛自己加標號或標籤，一旦加了，切出來的卡片就毀了。
HOUSE_STYLE = """\
A studio photography contact sheet: exactly {n} photographs arranged in a strict grid of \
{cols} columns and {rows} rows.

GRID: {n} equal-sized cells separated by clean pure-white gutters of uniform width. Every cell \
uses the same framing, the same camera distance and the same garment scale, so the {n} garments \
can be compared side by side. No garment, shadow or background tone crosses a gutter.

IN EVERY CELL: one garment entirely on its own - no mannequin, no dress form, no body, no head, \
no hands, no skin, no hanger, no rail. The garment is laid out and photographed from directly \
above, sleeves and hem arranged naturally, the fabric softly filled so the piece reads as a \
three-dimensional object rather than crushed flat. Real cloth: visible fibre texture and weave \
grain, visible topstitching and seam allowance at the shoulders, armholes and hem, buttons and \
closures where the garment has them, slight natural creasing where the fabric folds, and gentle \
asymmetry - real cloth never lies perfectly symmetrical. Soft off-white studio background with a \
faint contact shadow under the garment. Soft diffused daylight from the upper left with gentle \
falloff. Shot on a full-frame camera with an 85mm lens at f/5.6. The whole garment visible with \
a small even margin.

FORBIDDEN anywhere in the image: mannequins, dress forms, bodies, hangers, clothing rails, \
3D renders, CGI, mockup templates, vector illustration, flat even lighting, plastic or glossy \
artificial surfaces, perfect mirror symmetry, text, letters, numbers, captions, labels, logos, \
watermarks, price tags, props, people, reflections."""

# ── 中文值 → 英文值的補充表 ──────────────────────────────────────────────────
# engine02 的表涵蓋場合、季節、顏色與設計語彙；花色與材質它是折成「有圖案／素面」這種
# 軸向的（給排序用），但生圖需要的是具體的字（striped 跟 floral 畫出來差很多），
# 所以這兩類在這裡補一張表。表沒中的字會被記進 manifest 的 unresolved，不會硬猜。
PATTERN_EN: dict[str, str] = {
    "素面": "solid", "純色": "solid", "無圖案": "unpatterned",
    "條紋": "striped", "直條紋": "vertical striped", "橫條紋": "horizontal striped",
    "格紋": "checked", "千鳥格": "houndstooth", "威爾斯格": "glen check",
    "印花": "printed", "花卉": "floral print", "碎花": "small floral print",
    "波點": "polka dot", "圓點": "polka dot", "豹紋": "leopard print",
    "幾何": "geometric print", "抽象": "abstract print", "迷彩": "camouflage print",
    "漸層": "gradient", "拼接": "colour-blocked", "刺繡": "embroidered",
    "百褶": "pleated", "壓褶": "pleated", "抓皺": "ruched",
}

MATERIAL_EN: dict[str, str] = {
    "棉": "cotton", "純棉": "cotton", "麻": "linen", "亞麻": "linen", "棉麻": "cotton linen",
    "絲": "silk", "真絲": "silk", "雪紡": "chiffon", "緞面": "satin", "蕾絲": "lace",
    "羊毛": "wool", "毛料": "wool", "毛呢": "wool tweed", "喀什米爾": "cashmere",
    "針織": "knit", "羅紋針織": "ribbed knit", "丹寧": "denim", "牛仔": "denim",
    "皮革": "leather", "麂皮": "suede", "燈芯絨": "corduroy", "斜紋": "twill",
    "聚酯": "polyester", "尼龍": "nylon", "太空棉": "scuba", "紗網": "mesh",
}

# 基本色。engine02 的 ZH_COLOR_EXACT 專收「深藍→Navy Blue」這種精確值，
# 日常的「藍色」「黑色」不在裡面，補一張最小的。
BASIC_COLOR_EN: dict[str, str] = {
    # 同一個色系的深淺要分得開，否則「中藍」跟「淺藍」都塌成 blue，
    # 畫出來兩格一樣。比對是長鍵優先，所以這幾個兩字的會贏過單字的「藍」。
    "中藍": "medium blue", "淺藍": "light blue", "水洗藍": "washed blue",
    "淺灰": "light grey", "淺粉": "light pink",
    "黑": "black", "白": "white", "灰": "grey", "紅": "red", "藍": "blue", "綠": "green",
    "黃": "yellow", "橘": "orange", "橙": "orange", "紫": "purple", "粉": "pink",
    "棕": "brown", "咖": "brown", "米": "beige", "裸": "nude", "銀": "silver", "金": "gold",
}

# 畫不出來的欄位：塞進 prompt 只會佔 token 又幫不上忙，而且會讓模型自己腦補出
# 「看起來很貴」這種它以為的視覺線索，反而污染單變因。
NOT_VISUALIZABLE = {"budget_min", "budget_max", "inferred_fields", "notes"}

# Intent 欄位 → attribute_defs 裡的軸名。attribute_defs 是 taxonomy 自帶的
# 「英文值 → 中文值」對照（fit: tight/regular/loose/oversized…），反查就能把
# ENGINE01 吐的中文值換回英文。
FIELD_TO_AXIS = {"fit": "fit", "collar": "neckline", "length": "length",
                 "sleeve_length": "sleeve_length"}


def _is_ascii(text: str) -> bool:
    """已經是英文就原樣用，不要再翻一次。"""
    return bool(text) and all(ord(c) < 128 for c in text)


def _reverse_axis_table(axis: str) -> dict[str, str]:
    """attribute_defs[axis] 是 en→zh，這裡反轉成 zh→en。

    中文值可能是「合身/緊身」這種一格多詞的寫法，拆開讓兩個詞都查得到。
    """
    tax = load_taxonomy()
    table = tax.attribute_defs.get(axis) or {}
    out: dict[str, str] = {}
    for en, zh in table.items():
        for piece in str(zh).split("/"):
            piece = piece.strip()
            if piece:
                out[piece] = en
    return out


def _lookup_contains(value: str, table: dict[str, str]) -> Optional[str]:
    """子字串比對，長的鍵優先（「深藍」要贏過「藍」）。"""
    for key in sorted(table, key=len, reverse=True):
        if key in value:
            return table[key]
    return None


def english_value(field_name: str, value: str) -> Optional[str]:
    """把 Intent 某個欄位的一個中文值翻成生圖用的英文片語；翻不出來回 None。

    回 None 是有意義的訊號，不是失敗——呼叫端要把它記進 manifest 的 unresolved，
    讓人知道這個字沒有進到圖裡，而不是默默當作有畫到。
    """
    value = (value or "").strip()
    if not value:
        return None
    if _is_ascii(value):
        return value.lower()

    # 1) 有對應軸的欄位（fit／collar／length…）先查 taxonomy 自帶的值表
    axis = FIELD_TO_AXIS.get(field_name)
    if axis:
        hit = _lookup_contains(value, _reverse_axis_table(axis))
        if hit:
            return hit.replace("-", " ")

    # 2) 各欄位自己的補充表
    if field_name == "pattern":
        hit = _lookup_contains(value, PATTERN_EN)
        if hit:
            return hit
    if field_name == "material":
        hit = _lookup_contains(value, MATERIAL_EN)
        if hit:
            return hit
    if field_name == "colors":
        hit = _zh_lookup(value, ZH_COLOR_EXACT) or _lookup_contains(value, ZH_COLOR_EXACT)
        if hit:
            return hit.lower()
        hit = _lookup_contains(value, BASIC_COLOR_EN)
        if hit:
            return hit
    if field_name == "occasion":
        hit = _zh_lookup(value, ZH_OCCASION)
        if hit:
            return hit.lower()
    if field_name == "season":
        hit = _zh_lookup(value, ZH_SEASON)
        if hit:
            return hit.lower()

    # 3) 最後退回 engine02 的設計語彙軸（「寬鬆」→ relaxed loose fit）
    low = value.lower()
    for phrase, element, _sign in DESIGN_PHRASES:
        if phrase in low and element in ELEMENT_EN:
            return ELEMENT_EN[element]
    return None


def english_item_type(item_type: str) -> tuple[Optional[str], Optional[str]]:
    """「裙子」→ ("skirt", "bottoms.skirts")。翻不出來回 (None, None)。

    走 engine02 的分類體系而不是自己寫一張表，是因為它已經收了大量同義詞
    （半身裙／窄裙／百褶裙／A字裙…都對到 bottoms.skirts），而且跟 ENGINE02 檢索時
    用的是同一個解析結果，兩條支線講的是同一件單品。
    """
    item_type = (item_type or "").strip()
    if not item_type:
        return None, None
    tax = load_taxonomy()
    ids = resolve_category_values([item_type], tax)
    if not ids:
        return (item_type.lower(), None) if _is_ascii(item_type) else (None, None)
    node_id = ids[0]
    node = tax.nodes.get(node_id, {})
    # synonyms_en 的第一個通常是最口語的單數名詞（"skirt"），label_en 是複數的分類名
    # （"Skirts"）。prompt 裡要講一件衣服，所以單數優先。
    syn = node.get("synonyms_en") or []
    noun = (syn[0] if syn else node.get("label_en", "")).lower()
    return (noun or None), node_id


def free_axes(node_id: Optional[str]) -> list[str]:
    """這個品項可以拿來發散的屬性軸（概念圖模式在用）。

    taxonomy 只有第一層節點掛了 attributes（tops 有 sleeve_length/neckline/fit/
    construction，bottoms 有 length/fit/construction），第二層的 bottoms.skirts 是 None，
    所以往上找最近的有值祖先。全找不到就退回最通用的兩軸。
    """
    if not node_id:
        return ["fit", "length"]
    tax = load_taxonomy()
    for nid in [node_id, *tax.ancestors(node_id)]:
        attrs = (tax.nodes.get(nid) or {}).get("attributes")
        if attrs:
            # construction 的值偏工藝術語（有無襯裡之類），畫面上看不太出來，不拿來出圖。
            return [a for a in attrs if a != "construction"]
    return ["fit", "length"]


def axis_values_en(axis: str) -> list[str]:
    """某個屬性軸所有可用的英文值，概念圖模式用它交叉出六格。"""
    tax = load_taxonomy()
    return [en.replace("-", " ") for en in (tax.attribute_defs.get(axis) or {})]


# ── manifest ────────────────────────────────────────────────────────────────
# 為什麼每格一定要帶著自己的關鍵字：ENGINE03 要把「我喜歡第 3 格」翻成
# WeightAdjustment.field / Critique.attribute，那是欄位層級的東西，不是一串描述文字；
# 自動檢查也要有每格的文字才能做指派。所以 keywords 存結構化的 field→value，
# 另外用 prompt_fragment 逐字保存「這格到底是用哪些字生出來的」。


# 每個關鍵字是從哪來的。這四種要分開，因為它們的性質不同：Intent 來的是使用者的需求
# （改了要有理由），skill 自己生的是我們提供的可能性（本來就是拿來被否決的）。
SOURCE_INTENT = "intent"                 # 使用者在句子裡明說的
SOURCE_INFERRED = "intent_inferred"      # ENGINE01 從上下文推論、列在 inferred_fields 的
SOURCE_QUESTION = "question"             # 來自 ClarifyingQuestion 的某個選項
SOURCE_AXIS = "axis"                     # 來自 taxonomy 的屬性軸，這支 skill 自己挑的值


def cell_sources(keywords: dict[str, str], locked_zh: dict[str, Any],
                 varied: Optional[str] = None, varied_zh: Any = None,
                 varied_source: str = SOURCE_QUESTION) -> dict[str, dict[str, Any]]:
    """每格逐欄位標出「這個字打哪來、原本的中文是什麼」。

    沒有這層，下游要回答「這格是用 Intent 的哪些關鍵字生的」就得自己去 join 整張圖的
    `locked_zh` 跟這格的 `varied_attribute`，join 錯了也不會有人發現。ENGINE03 尤其需要
    分得清楚：使用者否決的是他自己講過的條件，還是我們自己補上去的值——前者要回頭改意圖，
    後者只要換一個值再生一次。
    """
    varied_fields = set(str(varied).split(",")) if varied else set()
    out: dict[str, dict[str, Any]] = {}
    for field_name, value in keywords.items():
        if field_name in varied_fields:
            out[field_name] = {"en": value, "zh": varied_zh, "from": varied_source}
        elif field_name in locked_zh:
            meta = locked_zh[field_name]
            out[field_name] = {"en": value, "zh": meta["value"],
                               "from": SOURCE_INFERRED if meta["inferred"] else SOURCE_INTENT}
        else:
            # 鎖死清單裡沒有、又不是這格的變因：只可能是基準格把變因欄位的現值講回來，
            # 那個值同樣出自 Intent。
            out[field_name] = {"en": value, "zh": varied_zh, "from": SOURCE_INTENT}
    return out


@dataclass
class Cell:
    index: int                                   # 1 起算，row-major
    keywords: dict[str, str]                     # field → 英文值（畫進這格的東西）
    prompt_fragment: str                         # 這格在 prompt 裡逐字的那一句
    keyword_sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    """每個關鍵字的來源與中文原值，由 cell_sources() 產生。"""
    option_id: Optional[str] = None              # 對應 ClarifyingOption.id（選項圖模式）
    varied_attribute: Optional[str] = None       # 這格相對基準改了哪個屬性
    varied_label_zh: Optional[str] = None        # 同上，中文原字，前端直接顯示
    bbox: Optional[list[int]] = None             # 切圖後填：[x0, y0, x1, y1]
    image: Optional[str] = None                  # 切圖後填：單格 PNG 路徑
    check: dict[str, Any] = field(default_factory=dict)   # 檢查後填


@dataclass
class Manifest:
    session_id: str
    round: int
    mode: str                                    # "variants"（選項圖）／"concepts"（概念圖）
    cols: int
    rows: int
    locked: dict[str, str]                       # 六格都一樣的鎖死屬性
    locked_zh: dict[str, Any]                    # 同上的中文原值，給前端與人看
    unresolved: list[str]                        # 翻不成英文、沒進圖的字
    varied_field: Optional[str]                  # 選項圖模式：這題在問哪個欄位
    house_style_hash: str                        # 攝影規格有沒有被改過，一看就知道
    prompt: str                                  # 送出去的完整 prompt，逐字
    cells: list[Cell]
    grid_image: Optional[str] = None
    canvas: Optional[list[int]] = None
    source: dict[str, Any] = field(default_factory=dict)   # 這份意圖來自哪個引擎
    generation: dict[str, Any] = field(default_factory=dict)  # 模型、秒數、尺寸
    slicing: dict[str, Any] = field(default_factory=dict)     # 切線怎麼來的

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def house_style_hash() -> str:
    """攝影規格的指紋。跨輪比較圖片之前先比這個——不一樣就不該拿來比。"""
    return hashlib.sha256(HOUSE_STYLE.encode("utf-8")).hexdigest()[:12]


# ── Intent → 鎖死的屬性 ──────────────────────────────────────────────────────


def locked_from_intent(intent: dict[str, Any], *, exclude: Optional[set[str]] = None
                       ) -> tuple[dict[str, str], dict[str, Any], list[str]]:
    """把 `Intent` 翻成「六格都不准變」的英文屬性。

    回傳 (英文屬性, 中文原值, 翻不出來的字)。

    `exclude` 是這一輪要拿來當變因的欄位——它不能同時是鎖死條件，否則六格會互相打架。

    刻意不區分 inferred_fields：ENGINE02 那邊把系統推論的欄位當軟訊號是對的（不該縮小
    候選池），但生圖沒有「軟」這個選項——一張圖要嘛畫了要嘛沒畫。所以推論來的欄位一樣
    鎖死，只是在 locked_zh 裡標出來，讓前端能照 ENGINE01 的規則顯示成「系統推論」。
    """
    exclude = exclude or set()
    en: dict[str, str] = {}
    zh: dict[str, Any] = {}
    unresolved: list[str] = []
    inferred = set(intent.get("inferred_fields") or [])

    def put(field_name: str, value: Any) -> None:
        """翻得出來就用英文，翻不出來就原文直送——但兩種都要記帳。

        為什麼不丟掉翻不出來的字：那些往往正是使用者這句話的重點（「韓系」「華夫格」）。
        丟掉它等於生一張跟需求無關的圖，而且沒有人會發現。原文直送至少保留了使用者的意思，
        生圖模型本來就看得懂中文的服裝詞彙。

        為什麼翻得出來的還是要翻：生成的圖之後會轉成向量併回 ENGINE02 的 dense 分數，
        兩條支線講同一套英文詞彙，分數才有可比性。

        記進 `unresolved` 的是「沒有對照、原文直送」的字，那是回報給線 1 的訊號：
        該補的是設計師詞表，不是這裡的對照表。
        """
        if field_name in exclude or field_name in NOT_VISUALIZABLE or not value:
            return
        values = value if isinstance(value, list) else [value]
        words: list[str] = []
        for raw in values:
            translated = english_value(field_name, str(raw))
            if translated:
                words.append(translated)
            else:
                words.append(str(raw))
                unresolved.append(f"{field_name}:{raw}")
        if words:
            en[field_name] = ", ".join(dict.fromkeys(words))
            zh[field_name] = {"value": value, "inferred": field_name in inferred}

    for name in ("colors", "material", "fit", "pattern", "collar", "occasion", "season"):
        put(name, intent.get(name))
    # style_keywords 是一串形容詞，翻得出來幾個算幾個，翻不出來的不當失敗——但**一定要記帳**。
    # 默默丟掉等於騙人：使用者說了「韓系」，圖裡沒有韓系，manifest 卻一個字都沒提。
    # unresolved 是回報給線 1 的唯一訊號（該補的是設計師詞表，不是這裡的對照表）。
    put("style_keywords", intent.get("style_keywords"))
    return en, zh, unresolved


# 鎖死屬性在句子裡的角色不一樣：有些是名詞前的形容詞（米白的、針織的），有些是後綴的
# 子句（for smart casual、in a loose fit）。混在一起用逗號硬串會變成一串不像話的字，
# 生圖模型對這種清單的遵循度比完整句子差，所以分成兩組。
_ADJECTIVES = ("colors", "pattern", "material")          # 直接放在品項名前面
_CLAUSES = (("fit", "in {v} fit"), ("collar", "with {v} neckline"),
            ("length", "at {v} length"), ("occasion", "for {v} occasions"),
            ("season", "for the {v} season"), ("style_keywords", "styled {v}"))

# 結尾那句要列「不准變的東西」時用的人話。
_INVARIANT_LABEL = {"colors": "same colour", "pattern": "same print", "material": "same fabric",
                    "fit": "same fit", "collar": "same neckline", "length": "same length",
                    "occasion": "same occasion", "season": "same season",
                    "style_keywords": "same styling"}


# 這幾個品項在英文裡永遠是複數，"a denim jeans" 是壞句子，要寫成 "a pair of denim jeans"。
_PLURAL_ITEMS = {"jeans", "trousers", "pants", "shorts", "leggings", "tights",
                 "dungarees", "overalls", "joggers", "chinos"}


def _article(word: str) -> str:
    """a / an。小事，但 prompt 裡出現 "a oversized fit" 會讓句子讀起來像壞掉的模板，
    而模型對壞掉的模板本來就比較不買帳。"""
    return "an" if word[:1].lower() in "aeiou" else "a"


def _noun_phrase(head: str) -> str:
    """把整個名詞片語加上正確的冠詞（複數品項用 a pair of）。"""
    last = head.rsplit(" ", 1)[-1].lower()
    return f"a pair of {head}" if last in _PLURAL_ITEMS else f"{_article(head)} {head}"


def baseline_sentence(item_en: str, locked: dict[str, str]) -> str:
    """鎖死屬性串成一句話，六格共用的那句基準描述。

    欄位順序寫死，不依 dict 的插入順序——同一組意圖在不同輪次要生出一模一樣的句子，
    否則 prompt 變了、圖就變了，跨輪比較就失去意義。
    """
    adjectives = [locked[k] for k in _ADJECTIVES if locked.get(k)]
    head = " ".join([*adjectives, item_en])
    clauses = [tpl.format(v=locked[k]) for k, tpl in _CLAUSES if locked.get(k)]
    tail = (", " + ", ".join(clauses)) if clauses else ""
    return (f"BASELINE GARMENT, identical in every cell except where stated: "
            f"{_noun_phrase(head)}{tail}.")


def invariant_sentence(locked: dict[str, str]) -> str:
    """結尾重申「沒被點名的都不准變」。

    **只列這一輪真的鎖死的屬性**。早期版本寫死「same fit, same length」，在概念圖模式
    剛好就是在變動這兩軸，等於 prompt 自己跟自己打架——dry-run 才看得出來的錯。
    """
    named = [_INVARIANT_LABEL[k] for k in _INVARIANT_LABEL if locked.get(k)]
    named += ["same lighting", "same framing", "same scale"]
    return ("Anything not named as that cell's exception must stay exactly consistent with the "
            "baseline across every cell: " + ", ".join(named) + ".")


# 兩種模式只有這一句不同：選項圖要求「每格只差一個屬性」（單變因是它存在的理由），
# 概念圖則允許每格在幾個自由軸上一起變（它要的是發散）。其餘 prompt 完全共用。
DIFFER_LINE = {
    "variants": ("Each cell differs from the baseline in exactly ONE attribute, in this "
                 "reading order (left to right, top row first):"),
    "concepts": ("Each cell is a different variation of the same garment, in this reading "
                 "order (left to right, top row first). They differ from the baseline ONLY "
                 "in the attributes named below:"),
}


def build_prompt(*, item_en: str, locked: dict[str, str], cells: list[Cell],
                 cols: int, rows: int, mode: str = "variants") -> str:
    """把固定的攝影規格、基準描述、每格差異組成最終 prompt。

    順序是刻意的：規格 → 禁止事項 → 基準 → 每格差異 → 再強調一次「沒點名的都不准變」。
    最後那句重申在 2026-09-19 的實測裡是有效的，六格的水洗、腰線、口袋都守住了。
    """
    lines = [HOUSE_STYLE.format(n=len(cells), cols=cols, rows=rows), "",
             baseline_sentence(item_en, locked), "",
             DIFFER_LINE.get(mode, DIFFER_LINE["variants"])]
    for cell in cells:
        lines.append(f"Cell {cell.index}: {cell.prompt_fragment}")
    lines += ["", invariant_sentence(locked)]
    return "\n".join(lines)
