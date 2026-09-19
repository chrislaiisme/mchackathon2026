"""ENGINE 02 main entry: Engine02Request → Engine02Response.

filter (with relaxation) → candidate retrieval (BM25 / dense / RRF / convex)
→ additive rerank (dense, bm25, design β·c, compat, trend, penalty, optional reranker)
→ optional MMR → reason selection (necessity / contrastive / sufficient)
→ template reasons → optional fact-checked LLM paraphrase.
"""

from __future__ import annotations

import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable, Collection, Protocol

import numpy as np

from . import fusion
from .catalog import Catalog
from .compat import CategoryCooccurrence, compat_scores
from .concepts import design_scores
from .config import ARMS, ArmConfig
from .constraints import filter_with_relaxation, satisfies, satisfies_positions
from .contracts import (
    ConstraintReport,
    Contribution,
    Engine02Request,
    Engine02Response,
    RankedItem,
    RoundMetrics,
)
from .encoders import Encoder, cached_image_embeddings, l2n
from .explain import LlmBudget, explain, template_reasons
from .kansei import KanseiTable
from .rerank import Term, additive_score, counterfactual_ranks, cutoff_explanations
from .sparse import BM25Index
from .taxonomy import filter_with_category_relaxation, load_taxonomy, resolve_category_values


class CrossReranker(Protocol):
    name: str

    def score(self, query: str, item_positions: list[int]) -> np.ndarray: ...


def build_retrieval_text(req: Engine02Request, catalog: str | None = None) -> str:
    if req.retrieval_text:
        return req.retrieval_text
    c = req.constraints
    parts: list[str] = []
    for slot in (c.gender, c.color, c.style_keywords, c.season):
        if slot.state.value in ("value", "inferred"):
            parts += slot.values
    tax = load_taxonomy()
    for v in c.category.values or ["clothing"]:
        # taxonomy ids / Chinese words → English label + catalog fine values (BM25 needs catalog words)
        ids = [i for i in resolve_category_values([v], tax) if i in tax.nodes]
        parts += [tax.retrieval_terms(i, catalog) for i in ids] if ids else [v]
    if c.occasion.values:
        parts += ["for"] + c.occasion.values
    return " ".join(parts)


def _stats(x: np.ndarray) -> tuple[float, float]:
    x = np.asarray(x, dtype=np.float64)
    return (float(x.mean()), float(x.std())) if x.size else (0.0, 1.0)


NEGATION_WORDS = (
    # en — NegBench (ICML 2025): CLIP-family encoders are near chance on negation, so a negated
    # retrieval_text silently retrieves the opposite of what the user meant
    "not", "no", "without", "avoid", "except", "n't", "don't", "doesn't", "never", "less",
    # zh
    "不要", "不想", "不能", "不", "沒有", "別", "避免", "除了", "以外",
)


def input_warnings(
    req: "Engine02Request",
    known_needs: "Collection[str] | None" = None,
    known_elements: "Collection[str] | None" = None,
) -> list[str]:
    """Input problems ENGINE 01 should fix. Warn, never silently rewrite the caller's text.

    `known_needs` / `known_elements` close the worst silent failure in the whole integration: a
    need_id or a design element that is not in the kansei table contributes **nothing**, and
    without a warning the response still looks perfect — HTTP 200, a faithful score decomposition,
    cards with reasons — except that half of what this engine is for (the implicit-need side) was
    switched off and nothing on the screen says so.
    """
    out: list[str] = []
    if known_needs is not None:
        unknown = sorted({n.need_id for n in req.needs} - set(known_needs))
        if unknown:
            out.append(
                f"needs 中有本引擎不認得的 need_id {unknown}：這些需求**完全沒有進入排序**（權重視為 0）。"
                f"可用的 need_id：{sorted(known_needs)}"
            )
    if known_elements is not None:
        asked = (set(req.feedback.design_adjust_steps) | set(req.design_weight_prior or {})
                 | set((req.profile.weights if req.profile else None) or {})
                 | set(req.stated_design_steps or {}))
        unknown_el = sorted(asked - set(known_elements))
        if unknown_el:
            out.append(
                f"design_adjust_steps／design_weight_prior／profile.weights 中有不存在的設計要素 {unknown_el}："
                f"這些調整被忽略。可用的要素：{sorted(known_elements)}"
            )
    text = (req.retrieval_text or "").lower()
    found = [w for w in NEGATION_WORDS if w in text]
    if found:
        out.append(
            f"retrieval_text 含否定詞 {found}：CLIP 系編碼器對否定接近隨機（NegBench, ICML 2025），"
            "否定請改放 constraints.excluded_values"
        )
    if req.retrieval_text and req.retrieval_text_normalized is False:
        out.append("retrieval_text_normalized=false：本輪只用 dense 檢索，BM25 權重設為 0")
    return out


class Engine02:
    def __init__(
        self,
        catalog: Catalog,
        encoder: Encoder,
        kansei: KanseiTable | None = None,
        cooccurrence: CategoryCooccurrence | None = None,
        cache_dir: str | Path | None = None,
        llm: Callable[[str], str] | None = None,
        cross_reranker: CrossReranker | None = None,
        compat_model=None,  # e.g. compat_ot.OutfitTransformerCompat; None → category NPMI
    ):
        t0 = time.perf_counter()
        self.catalog = catalog
        self.encoder = encoder
        self.kansei = kansei or KanseiTable.load()
        self.cooc = cooccurrence
        self.llm = llm
        self.cross_reranker = cross_reranker
        self.compat_model = compat_model
        self.cache = Path(cache_dir) if cache_dir else catalog.root / "index"
        self._safe = encoder.name.replace("/", "__")
        self.image_emb = cached_image_embeddings(encoder, catalog.image_paths(), self.cache / f"img_{self._safe}.npy")
        self._c: dict[tuple, np.ndarray] = {}
        self.bm25 = BM25Index(catalog.texts())
        self.trend_keywords: list[str] = []
        # catalogs with model-filled attributes (engine02/attribute_fill.py) filter those rows at
        # colour-family level and mark them on the card; metadata-only catalogs keep exact matching
        self._has_predicted = "attr_source" in catalog.items.columns and             catalog.items["attr_source"].astype(str).str.contains("predicted:").any()
        self._attr_filter = None
        if self._has_predicted:
            from .attribute_fill import provenance_filter

            self._attr_filter = provenance_filter("family")
        self.vocabulary = list(self.kansei.needs.values()) + [e.label for e in self.kansei.elements]
        self.init_ms = (time.perf_counter() - t0) * 1000

    def exposure_by_position(self, req: Engine02Request, arm: ArmConfig, decay: bool) -> dict[int, float]:
        """Position-weighted impressions per catalog position, from this session's rounds.

        `ε(rank)` is P(examined | rank) measured by eye tracking (Joachims et al., SIGIR 2005), so
        an item ignored at rank 5 counts far less than one ignored at rank 1 — "not chosen" and
        "not looked at" are different events and rank is the only evidence we have about which
        happened. A round where the user chose nothing is an outside-option event and counts
        `outside_option_kappa` (it used to count as the strongest evidence, which is backwards).

        decay=True applies `freshness_decay` per round of age for the score term; the frequency cap
        uses decay=False, because a cap that forgets is not a cap.
        """
        eps = arm.exposure_weights or (1.0,)
        n_rounds = len(req.feedback.choice_history)
        out: dict[int, float] = {}
        for r, rec in enumerate(req.feedback.choice_history):
            age = n_rounds - 1 - r
            gamma = (arm.freshness_decay ** age) if decay else 1.0
            kappa = 1.0 if rec.chosen_item_id else arm.outside_option_kappa
            ignored = [i for i in rec.shown_item_ids
                       if i and i != rec.chosen_item_id and i not in set(rec.rejected_item_ids)]
            for iid in ignored:
                p_ = self.catalog.pos(iid)
                if p_ is None:
                    continue
                rank = rec.shown_item_ids.index(iid)  # 0-based; the list is in display order
                e = eps[min(rank, len(eps) - 1)]
                out[int(p_)] = out.get(int(p_), 0.0) + gamma * kappa * e
        return out

    def _dense_scores(self, q: np.ndarray, pool: np.ndarray) -> np.ndarray:
        """Cosine of every pooled item against the query.

        `image_emb[pool] @ q` looks innocent but fancy-indexing copies the pool and, because the
        cache is float32 while the query is float64, the copy is upcast too: ~12 ms at 17.8k items
        and ~40 ms at 50k. One float32 matvec over the whole catalog is cheaper than the copy, and
        the pool is a slice of the result. ENGINE02_DENSE_F64=1 restores the float64 path for
        bit-comparable reproduction of earlier numbers.
        """
        if os.environ.get("ENGINE02_DENSE_F64") == "1":
            return self.image_emb[pool] @ q
        if getattr(self, "_emb32", None) is None:
            self._emb32 = np.ascontiguousarray(self.image_emb, dtype=np.float32)
        q32 = np.asarray(q, dtype=np.float32)
        # a narrow pool is cheaper to copy than the catalog is to multiply, and vice versa
        if len(pool) * 3 < len(self._emb32):
            return (self._emb32[pool] @ q32).astype(np.float64)
        return (self._emb32 @ q32)[pool].astype(np.float64)

    def attribute_notes(self, pos: int, c) -> list[str]:
        """Provenance notes for attributes the user constrained (before relaxation) that are model-filled."""
        if not self._has_predicted:
            return []
        from .attribute_fill import provenance_note

        used = {a for a in ("color", "gender", "occasion", "season") if getattr(c, a).is_hard() and getattr(c, a).values}
        used |= set(c.required_values) | set(c.excluded_values)
        return [note for attr, note in provenance_note(self.catalog.items, pos).items() if attr in used]

    def set_trends(self, keywords: list[str]) -> None:
        self.trend_keywords = keywords

    def design_matrix(self, arm: ArmConfig) -> np.ndarray:
        key = (arm.concept_mode, arm.concept_dn, arm.concept_applicability, arm.vlm_elements)
        if key in self._c:
            return self._c[key]
        f = self.cache / (
            f"design_{self._safe}_{self.kansei.version}_{arm.concept_mode}"
            f"_dn{int(arm.concept_dn)}_mask{int(arm.concept_applicability)}.npy"
        )
        shape = (len(self.catalog), len(self.kansei.elements))
        if arm.concept_mode in ("vlm", "hybrid"):
            from dataclasses import replace as _replace

            from .concepts import vlm_design_scores

            files = sorted(self.catalog.root.glob("vlm_attributes_*.parquet"))
            if not files:
                raise FileNotFoundError(f"run scripts/vlm_tag_attributes.py first (concept_mode={arm.concept_mode!r})")
            ids = self.catalog.items["item_id"].astype(str).tolist()
            if arm.concept_mode == "vlm":
                c = vlm_design_scores(ids, self.kansei, files[-1])
            else:
                c = self.design_matrix(_replace(arm, concept_mode="antonym")).copy()
                v, tagged = vlm_design_scores(ids, self.kansei, files[-1], return_mask=True)
                for j, el in enumerate(self.kansei.elements):
                    if el.id in arm.vlm_elements:
                        c[tagged[:, j], j] = v[tagged[:, j], j]
        elif f.exists() and np.load(f).shape == shape:
            c = np.load(f)
        else:
            cats = self.catalog.items["category"].tolist() if arm.concept_applicability else None
            c = design_scores(self.encoder, self.image_emb, self.kansei, arm.concept_mode, cats, arm.concept_dn)
            f.parent.mkdir(parents=True, exist_ok=True)
            np.save(f, c)
        self._c[key] = c
        return c

    # ------------------------------------------------------------------
    def query_embedding(self, req: Engine02Request, arm: ArmConfig, text: str) -> np.ndarray:
        q = self.encoder.encode_text([text])[0].astype(np.float64)
        fb = req.feedback
        if arm.use_rocchio:
            pos = self.catalog.positions(fb.chosen_item_ids)
            neg = self.catalog.positions(fb.rejected_item_ids)
            if pos:
                q = q + arm.rocchio_a * self.image_emb[pos].mean(axis=0)
            if neg:
                q = q - arm.rocchio_b * self.image_emb[neg].mean(axis=0)
        if arm.concept_image_weight > 0 and fb.concept_image_embedding:
            ci = np.asarray(fb.concept_image_embedding, dtype=np.float64)
            q = (1 - arm.concept_image_weight) * l2n(q) + arm.concept_image_weight * l2n(ci)
        return l2n(q).astype(np.float64)

    def run(self, req: Engine02Request, arm: ArmConfig | str | None = None) -> Engine02Response:
        arm = ARMS[arm] if isinstance(arm, str) else (arm or ARMS[req.options.arm])
        timings: dict[str, float] = {}
        t = time.perf_counter()

        def lap(name: str) -> None:
            nonlocal t
            now = time.perf_counter()
            timings[name] = round((now - t) * 1000, 2)
            t = now

        items = self.catalog.items
        k = req.options.top_k
        excluded = self.catalog.positions(req.feedback.excluded_item_ids)
        # A Chinese colour word ("藏青") matches nothing in an English catalog, so the hard filter
        # empties, the relaxation ladder drops the slot and the round reports satisfaction 0.0 with
        # no error anywhere — while a Chinese *category* works, because the taxonomy resolves it.
        # Normalise it to the catalog's vocabulary and say so in the response.
        # A stated exclusion has to bite in the SAME round. ENGINE 01 is supposed to move it into
        # excluded_values; when it does not, resolve it here rather than only warning about it —
        # a CLIP-family encoder is near chance on negation, so leaving it in the text means the
        # user sees exactly what they just rejected (§3.35).
        negations: list[dict[str, str]] = []
        if arm.parse_negations and req.retrieval_text:
            from .negation import catalog_vocabulary, expand_color_family, find_negated

            vocab = getattr(self, "_neg_vocab", None)
            if vocab is None:
                vocab = self._neg_vocab = catalog_vocabulary(self.catalog.items, self.kansei.elements)
            for attr, value, said in find_negated(req.retrieval_text, vocab):
                if attr == "design_element":
                    # this round's words, so it is attributed to the user, not to "last round"
                    steps = req.stated_design_steps
                    if value not in steps and value not in req.feedback.design_adjust_steps:
                        steps[value] = arm.negation_element_steps
                        negations.append({"said": said, "applied_to": f"design:{value}",
                                          "how": f"設計要素權重 {arm.negation_element_steps} 步"})
                elif attr == "category_id":
                    cur = req.constraints.excluded_values.setdefault("category", [])
                    if value not in cur:
                        cur.append(value)
                        negations.append({"said": said, "applied_to": "category", "how": f"排除 {value}"})
                else:
                    cur = req.constraints.excluded_values.setdefault(attr, [])
                    vals = (expand_color_family(value, self.catalog.items) if attr == "color"
                            else [value])
                    added = [v for v in vals if v not in cur]
                    if added:
                        cur.extend(added)
                        how = f"排除 {value}" + (f"（含同色系 {len(added) - 1} 個值）" if len(added) > 1 else "")
                        negations.append({"said": said, "applied_to": attr, "how": how})

        color_rewrites: list[tuple[str, str]] = []
        if req.constraints.color.values:
            from .attribute_fill import normalize_color_values

            new_vals, color_rewrites = normalize_color_values(req.constraints.color.values)
            if color_rewrites:
                req.constraints.color.values = new_vals
        # hierarchical category relaxation (L2 → L1) via the unified taxonomy; unresolvable category
        # values fall back to the legacy exact-match ladder (docs/research/taxonomy.md §5.2)
        fr = filter_with_category_relaxation(items, req.constraints, max(arm.min_results, k), excluded,
                                             catalog=self.catalog.name, base=self._attr_filter)
        pool = np.flatnonzero(fr.mask)
        # Position-weighted frequency cap. A score term cannot guarantee the top of the list
        # changes — the measured score gap from rank 1 to rank 6 is ≈0.5, so any weight big enough
        # to move it would outweigh "this matches what you asked for". Dropping items the user has
        # already effectively seen is a rule, so it needs no estimator; but it must never empty the
        # pool, and when it is skipped the response says so instead of quietly repeating cards.
        n_exposure_excluded, cap_skipped = 0, False
        if arm.use_freshness and arm.exposure_cap > 0 and req.feedback.choice_history:
            seen_enough = [p_ for p_, x in self.exposure_by_position(req, arm, decay=False).items()
                           if x >= arm.exposure_cap]
            if seen_enough:
                keep = ~np.isin(pool, np.asarray(seen_enough, dtype=int))
                if keep.sum() >= max(arm.min_results, k):
                    n_exposure_excluded = int((~keep).sum())
                    pool = pool[keep]
                else:
                    cap_skipped = True
        lap("filter")
        # one shared budget per request: cards after the budget (or after the first failure) use
        # templates instead of each waiting for its own timeout
        llm_for_request = (LlmBudget(self.llm, float(os.environ.get("ENGINE02_LLM_BUDGET_S", "1.5")))
                           if (self.llm is not None and req.options.explain_with_llm) else None)

        bm25_gate_note: dict | None = None
        text = build_retrieval_text(req, self.catalog.name)
        grounded_pairs: list[tuple[str, str]] = []
        bm25_text = text
        if arm.ground_query != "none":
            from .taxonomy import ground_query as _ground

            grounded, grounded_pairs = _ground(text, self.catalog.name)
            if grounded:
                # ground FIRST, then gate: if the translation restores real catalog words, the
                # lexical side is usable again and the gate below will not fire
                bm25_text = f"{text} {grounded}"
                if arm.ground_query == "both":
                    text = bm25_text
        q = self.query_embedding(req, arm, text)
        dense_all = self._dense_scores(q, pool)
        bm25_all = self.bm25.scores(bm25_text)[pool]
        if req.retrieval_text_normalized is False:
            timings["bm25_routed_off"] = 1.0
            arm = replace(arm, w_bm25=0.0, candidate_fusion="dense" if arm.candidate_fusion in ("rrf", "convex")
                          else arm.candidate_fusion)
        elif arm.bm25_gate == "docs_touched":
            # The lexical side does not fail by going quiet, it fails by getting loud about the
            # wrong thing: one word that appears in a single product title carries the highest idf
            # in the query and owns the ranking. So ask how much of the catalog the query's terms
            # touch at all, not how confident the top score looks.
            st = self.bm25.match_stats(bm25_text)
            timings["bm25_docs_touched"] = round(st["share_docs_touched"], 4)
            if st["share_docs_touched"] < arm.bm25_min_docs_touched:
                bm25_gate_note = st
                arm = replace(arm, w_bm25=0.0,
                              candidate_fusion="dense" if arm.candidate_fusion in ("rrf", "convex")
                              else arm.candidate_fusion)
        elif arm.bm25_adaptive or arm.bm25_gate == "coverage":
            cov = self.bm25.coverage(bm25_text)
            timings["bm25_coverage"] = round(cov, 3)
            bm25_scale = cov if cov >= arm.bm25_min_coverage else 0.0
            arm = replace(arm, w_bm25=arm.w_bm25 * bm25_scale)
            if bm25_scale == 0.0 and arm.candidate_fusion in ("rrf", "convex"):
                arm = replace(arm, candidate_fusion="dense")
        lap("retrieve")

        if arm.candidate_fusion == "bm25":
            fused = bm25_all
        elif arm.candidate_fusion == "dense":
            fused = dense_all
        elif arm.candidate_fusion == "convex":
            fused = fusion.convex(dense_all, bm25_all, arm.convex_alpha, arm.convex_norm)
        else:
            fused = fusion.rrf([dense_all, bm25_all], k=arm.rrf_k, depth=arm.rrf_depth)
        n_cand = min(req.options.n_candidates, len(pool))
        top = np.argsort(-fused, kind="stable")[:n_cand]
        cand = pool[top]
        lap("fuse")

        terms = self._terms(req, arm, pool, cand, dense_all, bm25_all, top, text)
        sc = additive_score(terms)
        order = sc.order()
        if arm.use_mmr and len(order) > 1:
            depth = min(len(order), max(4 * k, 20))
            sel = fusion.mmr(sc.scores[order[:depth]], self.image_emb[cand[order[:depth]]], k, arm.mmr_lambda)
            head = order[:depth][sel]
            order = np.concatenate([head, np.setdiff1d(order, head, assume_unique=True)])
        shown = [int(p) for p in order[:k]]
        lap("rerank")

        do_cf = arm.counterfactual and req.options.counterfactual_check
        cf = counterfactual_ranks(sc, shown) if do_cf else {}
        cut = cutoff_explanations(sc, order, k)
        lap("counterfactual")

        probs = {n.need_id: n.prob for n in req.needs}
        el_labels = {e.id: e.label for e in self.kansei.elements}
        c_mat = self.design_matrix(arm)
        out_items: list[RankedItem] = []
        for rank, p in enumerate(shown, start=1):
            pos = int(cand[p])
            ce = cut[p]
            contribs = []
            for j, term in enumerate(sc.terms):
                cval = float(sc.contrib[p, j])
                shares = {}
                if term.group == "design":
                    shares = {n: v * float(sc.norm[p, j]) for n, v in term.need_shares_per_unit.items()}
                rw = cf[p][j] if p in cf else None
                necessary = (rw > k) if rw is not None else None
                sufficient = j in ce.sufficient
                if arm.reason_mode == "necessity":
                    cited = bool(necessary) if do_cf else False
                elif arm.reason_mode == "contrastive":
                    cited = ce.diffs[j] > 0 and ce.margin - ce.diffs[j] < 0
                else:
                    cited = sufficient
                contribs.append(
                    Contribution(
                        term=term.name,
                        group=term.group,
                        raw=float(term.raw[p]),
                        normalized=float(sc.norm[p, j]),
                        weight=float(term.weight),
                        contribution=cval,
                        need_shares=shares,
                        rank_without=rw,
                        necessary=necessary,
                        diff_vs_cutoff=float(ce.diffs[j]),
                        sufficient=sufficient,
                        cited=bool(cited and cval > 0),
                    )
                )
            # display cap: the minimal sufficient set is shown whole (trimming it would break
            # the sufficiency guarantee); other modes show at most 3 reasons
            cap = None if arm.reason_mode == "sufficient" else 3
            if cap is not None:
                keep = sorted((cb for cb in contribs if cb.cited), key=lambda cb: -cb.contribution)[:cap]
                keep_ids = {id(cb) for cb in keep}
                for cb in contribs:
                    cb.cited = id(cb) in keep_ids
            need_contrib: dict[str, float] = {}
            for cb in contribs:
                for n, v in cb.need_shares.items():
                    need_contrib[n] = need_contrib.get(n, 0.0) + v
            reasons, facts = template_reasons(contribs, el_labels, self.kansei.needs, fr.relaxed)
            notes = self.attribute_notes(pos, req.constraints)
            reasons += [f"注意：{n}" for n in notes]
            use_llm = llm_for_request
            text_expl, src = explain(reasons, facts, self.vocabulary, use_llm)
            price = self.catalog.attr(pos, "price")
            out_items.append(
                RankedItem(
                    item_id=str(self.catalog.column("item_id")[pos]),
                    rank=rank,
                    title=str(self.catalog.column("title")[pos]),
                    image_path=str(self.catalog.column("image_path")[pos]),
                    category=self.catalog.attr(pos, "category"),
                    color=self.catalog.attr(pos, "color"),
                    price=float(price) if price is not None else None,
                    score=float(sc.scores[p]),
                    contributions=contribs,
                    need_contributions=need_contrib,
                    design_scores={e.id: float(c_mat[pos, j]) for j, e in enumerate(self.kansei.elements)},
                    margin_vs_cutoff=ce.margin if ce.cutoff_position is not None else None,
                    reason_mode=arm.reason_mode,
                    reasons=reasons,
                    attribute_notes=notes,
                    explanation=text_expl,
                    explanation_source=src,
                )
            )
        lap("explain")

        shown_pos = [int(cand[p]) for p in shown]
        # "and give me something instead": when an exclusion fired, name the item it cost the user
        # and the shown item closest to it. One dot product over the excluded rows, no re-ranking.
        substitutes = (self._substitutes(negations, req.constraints.excluded_values, q, shown_pos)
                       if negations and shown_pos else [])
        return Engine02Response(
            session_id=req.session_id,
            round=req.round,
            arm=arm.name,
            items=out_items,
            constraint_report=ConstraintReport(
                applied=fr.applied, relaxed=fr.relaxed, n_catalog=len(items), n_after_filter=int(len(pool)),
                exposure_excluded=n_exposure_excluded, exposure_cap_skipped=cap_skipped,
                grounded_terms=([{"your_words": a, "catalog_words": b} for a, b in grounded_pairs]
                                + [{"your_words": a, "catalog_words": b} for a, b in color_rewrites]),
                honoured_negations=negations, substitutes=substitutes,
                retracted_constraints=list(getattr(fr, 'retracted', []) or []),
                input_warnings=input_warnings(
                    req, known_needs=self.kansei.need_ids,
                    known_elements=[e.id for e in self.kansei.elements])
                + [r["why"] for r in (getattr(fr, "retracted", []) or [])]
                + ([f"預算 {fr.applied['budget_unavailable'][0]} 無法套用："
                    f"這個商品庫沒有價格資料，本輪未依預算過濾（其餘條件不受影響）"]
                   if "budget_unavailable" in fr.applied else [])
                + ([f"有 {fr.applied['budget_unpriced_excluded'][0]} 件商品沒有價格，"
                    f"依預算過濾時已被排除"]
                   if "budget_unpriced_excluded" in fr.applied else []) + (
                    [f"查詢用字與商品庫幾乎對不上（只觸及 {bm25_gate_note['share_docs_touched']:.1%} 的商品），"
                     f"本輪關閉關鍵字比對、只用語意檢索；請 ENGINE 01 把屬性值正規化成商品庫詞彙"]
                    if bm25_gate_note else []),
            ),
            metrics=self._metrics(req, shown_pos),
            kansei_version=self.kansei.version,
            encoder=self.encoder.name,
            query_embedding=[float(x) for x in q],
            timings_ms=timings,
        )

    # ------------------------------------------------------------------

    def _substitutes(self, negations, excluded_values, q, shown_pos) -> list[dict]:
        """What the exclusion cost, and what stands in for it.

        The best item the user would have seen without the exclusion, and the shown item closest to
        it in the encoder's space. A report, not a ranking decision: nothing here changes the order,
        and it is skipped entirely when nothing was excluded.
        """
        items = self.catalog.items
        img = np.asarray(self.image_emb, dtype=np.float32)
        qv = np.asarray(q, dtype=np.float32)
        shown = np.asarray(shown_pos, dtype=int)
        out: list[dict] = []
        for n in negations:
            attr = n.get("applied_to", "")
            # a design-axis aversion removes nothing from the pool, so it costs nothing to replace
            if attr not in items.columns or attr == "category_id":
                continue
            vals = [str(v).lower() for v in (excluded_values.get(attr) or [])]
            if not vals:
                continue
            col = items[attr].astype(str).str.lower().to_numpy()
            hit = np.flatnonzero(np.isin(col, vals))
            if not len(hit) or not len(shown):
                continue
            # compare like with like: the thing the exclusion cost should be the same kind of
            # garment as what is on screen, otherwise "we removed a pair of sunglasses for you"
            if "category" in items.columns:
                cat_col = items["category"].astype(str).str.lower().to_numpy()
                kinds = {cat_col[p] for p in shown}
                same_kind = hit[np.isin(cat_col[hit], list(kinds))]
                if len(same_kind):
                    hit = same_kind
            best = int(hit[int(np.argmax(img[hit] @ qv))])
            sims = img[shown] @ img[best]
            near = int(shown[int(np.argmax(sims))])
            out.append({
                "excluded_item_id": str(items.at[best, "item_id"]),
                "excluded_title": str(items.at[best, "title"]),
                "substitute_item_id": str(items.at[near, "item_id"]),
                "substitute_title": str(items.at[near, "title"]),
                "similarity": round(float(np.max(sims)), 4),
                "note": f"你說{n.get('said', '')}，這件是最接近被拿掉那一件的替代",
            })
        return out

    def _terms(self, req, arm: ArmConfig, pool, cand, dense_all, bm25_all, top, text) -> list[Term]:
        dense, bm25 = dense_all[top], bm25_all[top]
        if not arm.additive_rerank:
            if arm.candidate_fusion == "rrf":
                d = (1.0 / (arm.rrf_k + fusion.ranks_desc(dense_all)))[top]
                b = (1.0 / (arm.rrf_k + fusion.ranks_desc(bm25_all)))[top]
                return [Term("dense", "dense", d, 1.0, normalize=False), Term("bm25", "bm25", b, 1.0, normalize=False)]
            if arm.candidate_fusion == "convex":
                f = fusion.minmax if arm.convex_norm == "minmax" else fusion.zscore
                return [
                    Term("dense", "dense", f(dense_all)[top], arm.convex_alpha, normalize=False),
                    Term("bm25", "bm25", f(bm25_all)[top], 1 - arm.convex_alpha, normalize=False),
                ]
            single = dense if arm.candidate_fusion == "dense" else bm25
            return [Term(arm.candidate_fusion, arm.candidate_fusion, single, 1.0, normalize=False)]

        pool_scope = arm.norm_scope == "pool"
        terms = [
            Term("dense", "dense", dense, arm.w_dense, stats=_stats(dense_all) if pool_scope else None, clip=arm.z_clip),
            Term("bm25", "bm25", bm25, arm.w_bm25, stats=_stats(bm25_all) if pool_scope else None, clip=arm.z_clip),
        ]
        if arm.use_design and len(self.kansei.elements):
            c_mat = self.design_matrix(arm)
            probs = {n.need_id: n.prob for n in req.needs}
            beta_needs, beta_fb = self.kansei.beta(probs, req.feedback.design_adjust_steps)
            # learned Δβ (already in γ-scaled units, see engine02/preference.py) on canonical axes
            learned = np.zeros(len(self.kansei.elements))
            for d, v in req.feedback.design_weight_delta.items():
                canon = self.kansei.folded.get(d, d)
                if canon in self.kansei.element_ids:
                    learned[self.kansei.element_ids.index(canon)] += -v if d in self.kansei.folded else v
            # an external prior (merchandiser guidance, or a trend platform's output) enters the
            # same additive slot but is attributed separately and clipped to one user feedback
            # step, so the population can never outvote the person in front of us
            prior = np.zeros(len(self.kansei.elements))
            cap = float(self.kansei.step_size)
            for d, v in req.design_weight_prior.items():
                canon = self.kansei.folded.get(d, d)
                if canon in self.kansei.element_ids:
                    signed = -float(v) if d in self.kansei.folded else float(v)
                    j_ = self.kansei.element_ids.index(canon)
                    prior[j_] = float(np.clip(prior[j_] + signed, -cap, cap))
            # The profile the user built before round 1 is a prior MEAN, not evidence. Its weight
            # is kappa0 / (kappa0 + rounds of real feedback), so by the time the user has actually
            # reacted kappa0 times it is outvoted by what they did — a bounded, checkable property
            # rather than a promise that "it won't hijack later rounds".
            # what the user said in THIS request, on the same axes, attributed to them
            stated = np.zeros(len(self.kansei.elements))
            max_step = float(self.kansei.step_size) * float(self.kansei.max_steps)
            for d, v in (req.stated_design_steps or {}).items():
                canon = self.kansei.folded.get(d, d)
                if canon in self.kansei.element_ids and v:
                    j_ = self.kansei.element_ids.index(canon)
                    signed = float(v) * self.kansei.step_size * (-1.0 if d in self.kansei.folded else 1.0)
                    stated[j_] = float(np.clip(stated[j_] + signed, -max_step, max_step))
            profile = np.zeros(len(self.kansei.elements))
            profile_shrink = 0.0
            if req.profile and req.profile.weights:
                k0 = max(0.0, float(req.profile.kappa0))
                profile_shrink = k0 / (k0 + len(req.feedback.choice_history)) if k0 else 0.0
                for d, v in req.profile.weights.items():
                    canon = self.kansei.folded.get(d, d)
                    if canon in self.kansei.element_ids:
                        signed = -float(v) if d in self.kansei.folded else float(v)
                        j_ = self.kansei.element_ids.index(canon)
                        profile[j_] = float(np.clip(profile[j_] + signed * cap * profile_shrink, -cap, cap))
            for j, el in enumerate(self.kansei.elements):
                w = float(arm.need_scale * (beta_needs[j] + beta_fb[j]) + learned[j] + prior[j]
                          + profile[j] + stated[j])
                if abs(w) < 1e-9:
                    continue
                per_unit = {}
                for i, n in enumerate(self.kansei.need_ids):
                    v = arm.need_scale * probs.get(n, 0.0) * self.kansei.K[i, j]
                    if abs(v) > 1e-9:
                        per_unit[n] = float(v)
                fb_part = arm.need_scale * beta_fb[j] + learned[j]
                if abs(fb_part) > 1e-9:
                    per_unit["feedback_adjust"] = float(fb_part)
                if abs(prior[j]) > 1e-9:
                    per_unit["external_prior"] = float(prior[j])
                if abs(profile[j]) > 1e-9:
                    per_unit["profile_prior"] = float(profile[j])
                if abs(stated[j]) > 1e-9:
                    per_unit["stated_design"] = float(stated[j])
                # c(i,d) is already z-scored over the whole catalog → no re-normalisation in pool scope
                terms.append(Term(f"design:{el.id}", "design", c_mat[cand, j], w, per_unit, normalize=not pool_scope))
        if (arm.use_critique_roles and req.feedback.critique
                and req.feedback.reference_item_id is not None):
            # MulVec-style role split (arXiv:2608.25305, 2026): a critique is not one direction in
            # embedding space, it is three statements — what should appear, what should stay, what
            # should go. Fused into a single vector they are an opaque α; kept apart they are three
            # named, signed contributions that add up to the same score the user is shown.
            ref = self.catalog.pos(req.feedback.reference_item_id)
            if ref is None:
                bm25_gate_note = bm25_gate_note  # unknown reference: fall through, warned below
            else:
                # contracts.Critique is the wire format; composed.Critique is the resolver that
                # fills in "from" from the reference row and turns a direction into a value
                from .composed import Critique as _Crit
                from .composed import direction_phrases

                row = self.catalog.items.iloc[ref]
                c_in = req.feedback.critique
                crit = _Crit(attribute=c_in.attribute, to_value=c_in.to_value,
                             from_value=c_in.from_value, direction=c_in.direction).resolved(row)
                to_p, from_p = direction_phrases(row, crit)
                img = np.asarray(self.image_emb, dtype=np.float32)
                phr = self.encoder.encode_text([to_p, from_p])
                want = img[cand] @ np.asarray(phr[0], dtype=np.float32)
                avoid = img[cand] @ np.asarray(phr[1], dtype=np.float32)
                keep = img[cand] @ img[ref]
                if arm.w_role_desire:
                    terms.append(Term(f"critique:want:{to_p}", "critique", want, arm.w_role_desire))
                if arm.w_role_preserve:
                    terms.append(Term("critique:keep:reference", "critique", keep, arm.w_role_preserve))
                if arm.w_role_forbid:
                    terms.append(Term(f"critique:avoid:{from_p}", "critique", avoid, -arm.w_role_forbid))
        if arm.use_compat and req.feedback.anchor_item_ids:
            anchors = self.catalog.positions(req.feedback.anchor_item_ids)
            if self.compat_model is not None and anchors:
                # item-level: distinguishes items within a category (NPMI cannot)
                cs = self.compat_model.score(anchors, [int(p) for p in cand])
                terms.append(Term(f"compat:{self.compat_model.name}", "compat", cs, arm.w_compat))
            else:
                cs = compat_scores(
                    [self.catalog.attr(int(p), "category") for p in cand],
                    [self.catalog.attr(a, "category") for a in anchors],
                    self.cooc,
                )
                if cs is not None:  # NPMI is already on a fixed [-1, 1] scale
                    terms.append(Term("compat", "compat", cs, arm.w_compat, normalize=not pool_scope))
        if arm.use_trend and self.trend_keywords:
            tr_all = self.bm25.scores(" ".join(self.trend_keywords))[pool]
            terms.append(Term("trend", "trend", tr_all[top], arm.w_trend,
                               stats=_stats(tr_all) if pool_scope else None, clip=arm.z_clip))
        if arm.use_penalty and req.feedback.rejected_item_ids:
            neg = self.catalog.positions(req.feedback.rejected_item_ids)
            if neg:
                sim_all = (self.image_emb[pool] @ self.image_emb[neg].T).max(axis=1)
                terms.append(
                    Term("penalty:rejected_similarity", "penalty", sim_all[top], -arm.w_penalty,
                         stats=_stats(sim_all) if pool_scope else None, clip=arm.z_clip)
                )
        if arm.use_freshness and req.feedback.choice_history:
            exposure = self.exposure_by_position(req, arm, decay=True)
            if exposure:
                seen_all = np.zeros(len(pool), dtype=np.float64)
                pos_index = {int(p_): j for j, p_ in enumerate(pool)}
                for p_, x in exposure.items():
                    j = pos_index.get(int(p_))
                    if j is not None:
                        seen_all[j] = x
                if seen_all.any():
                    # Phrased as freshness, not blame: raw = 1 − exposure, so an item the user has
                    # not seen contributes +w (and the card may say so), one they have effectively
                    # seen once contributes 0, and a repeatedly shown one goes negative. This is
                    # rank-identical to a −w·exposure penalty but it is sayable: "因為你沒選它" is
                    # an accusation the data cannot support, "你還沒看過這件" is a fact.
                    # Deliberately NOT z-scored — normalising handed never-seen items a positive
                    # "fatigue" score in an earlier version, which was nonsense on a card.
                    terms.append(
                        Term("freshness:not_yet_seen", "freshness", 1.0 - seen_all[top],
                             arm.w_freshness, normalize=False)
                    )
        if arm.use_cross_reranker and self.cross_reranker is not None:
            rs = self.cross_reranker.score(text, [int(p) for p in cand])
            terms.append(Term(f"rerank:{self.cross_reranker.name}", "rerank", rs, arm.w_rerank))
        terms += self._context_terms(req, arm, cand)
        return terms

    def _context_terms(self, req, arm: ArmConfig, cand) -> list[Term]:
        """The shopper's situation (weather, festival, commute) and opt-in personal options, one
        un-normalised term per signal so "+0.30" on a card is exactly +0.30. No context -> no terms,
        so every request without it ranks exactly as before."""
        from .context.engine import CONTEXT_LABELS, build_signals, enriched, is_empty, item_scores

        ctx = getattr(req, "context", None)
        self._last_context = {"signals": [], "problems": []}
        if is_empty(ctx):
            CONTEXT_LABELS.set({})
            return []
        sigs, problems = build_signals(ctx)
        self._last_context = {"signals": sigs, "problems": problems}
        items = enriched(self.catalog.items)
        c_mat = self.design_matrix(arm)
        ids = list(self.kansei.element_ids)
        out: list[Term] = []
        labels: dict[str, str] = {}
        for i, s in enumerate(sigs):
            if not s.affects_ranking:
                continue
            raw = item_scores(s, items, cand, c_mat, ids)
            if not np.any(np.abs(raw) > 1e-12):
                continue
            name = f"context:{s.source}"
            if name in labels:
                name = f"{name}:{i}"
            out.append(Term(name, "context", raw, 1.0, normalize=False))
            labels[name] = s.label
        CONTEXT_LABELS.set(labels)
        return out

    def _metrics(self, req: Engine02Request, shown_pos: list[int]) -> RoundMetrics:
        items = self.catalog.items
        if not shown_pos:
            return RoundMetrics()
        c = req.constraints
        policy = "exact"
        prep = getattr(self._attr_filter, "prepare", None)
        if prep is not None:  # judge with the comparator the filter used, not a stricter one
            items, c = prep(items, c)
            policy = "color_family" if c.color.values != req.constraints.color.values else "exact"
        tax = load_taxonomy()
        ids = resolve_category_values(c.category.values, tax) if (c.category.is_hard() and c.category.values) else []
        roots = [tax.l1(i) or i for i in ids if i in tax.nodes] or ids
        pos = np.asarray(shown_pos, dtype=int)
        if ids and tax.category_mask(items, roots, self.catalog.name).any():
            # category judged through the taxonomy (the original, un-relaxed request); masks are
            # computed once over the whole frame and indexed, not per shown row
            cat_ok = tax.category_mask(items, ids, self.catalog.name)[pos]
            c_rest = c.model_copy(deep=True)
            c_rest.category.values = []
            sat = float(np.mean(cat_ok & satisfies_positions(items, pos, c_rest)))
        else:
            from .taxonomy import legacy_constraints

            c_eval = legacy_constraints(c, ids, tax) if ids else c
            sat = float(np.mean(satisfies_positions(items, pos, c_eval)))
        hits = 0
        for attr, vals in req.constraints.excluded_values.items():
            if attr in items.columns:
                lv = {v.lower() for v in vals}
                col = items[attr].to_numpy()
                hits += sum(str(col[p]).lower() in lv for p in shown_pos)
        bad_ids = set(req.feedback.excluded_item_ids) | set(req.feedback.rejected_item_ids)
        ids_col = self.catalog.column("item_id")
        id_hits = sum(str(ids_col[p]) in bad_ids for p in shown_pos)
        # cumulative over every earlier round (see RoundMetrics); the split is reported too
        return RoundMetrics(hard_constraint_satisfaction=float(sat), match_policy=policy,
                            excluded_value_hits=hits, rejected_item_hits=int(id_hits),
                            feedback_violations=hits + int(id_hits))
