"""search_engine — deterministic source-bound engine for the week4 SEARCH track.

The Agent reads the ACTUAL organizer-provided local materials (9 scientific
documents, real Crossref/EuropePMC/publisher responses, a retained reference
graph, organizer-local incremental import states, USPTO facsimiles, ...) and
fills an IR. This engine then validates the IR and performs REAL computation:

  * record normalization + dedup (w4kit.dedup_records, DOI exact + fuzzy title)
  * relevance ranking with recorded per-feature rationale + tie-breaking
  * inclusion/exclusion screening with per-record reason codes + evidence
  * citation-graph BFS (forward/backward) with per-hop direction + source path
  * coverage/recall vs an INDEPENDENT reference set + miss attribution + rounds
  * multi-database field normalization, merge priority, per-field provenance,
    coverage matrix and explicit gaps
  * incremental snapshot diff (new / version-update / retracted), window checks
  * PRISMA-style count closure + dual-reviewer disagreement + adjudication
  * quality appraisal scale: dimension -> judgment -> evidence locator -> grade,
    with abstain (insufficient_evidence) instead of fabricated judgments
  * cross-language work/view identity: language/version preserved, exact
    duplicates flagged, term alignment table validated
  * patent number normalization, observed-link family union, claim versions,
    legal status defaults to UNKNOWN unless source-located

NO live remote search is performed or claimed. Every candidate record carries
provenance (source database/document, original query, response snippet,
field-level source). Reported vs inferred vs missing are distinguished.

API:  validate_ir(ir) -> {ok, errors, warnings}
      build(ir, case, out_dir) -> [{name, path, format, role}, ...]
"""
from __future__ import annotations

import csv
import re
from collections import deque
from pathlib import Path

import w4kit as kit

IR_VERSION = kit.IR_VERSION

KINDS = {
    "query_planning",        # challenge-a2909a72 学术文献检索
    "question_driven",       # challenge-e7598a44 科研问题驱动检索
    "screen_rank",           # challenge-2dd1f64c 文献筛选与智能排序
    "citation_tracking",     # challenge-60a8202d 引文追踪与关联文献发现
    "multi_db_merge",        # challenge-5c918ff0 多数据库联合检索
    "incremental_tracking",  # challenge-1e85736f 最新文献发现与追踪
    "coverage_analysis",     # challenge-0467f5db 检索覆盖率与遗漏分析
    "systematic_screening",  # challenge-5b90f5e9 系统性文献检索与纳排筛选
    "quality_appraisal",     # challenge-bace1c46 文献研究质量评价
    "cross_language",        # challenge-802a7115 跨语言文献检索
    "patent_search",         # challenge-ad3e9357 专利与技术文献检索
}

CORE_FIELDS = ("title", "authors", "year", "journal", "doi")
DECISIONS = {"include", "exclude", "maybe"}
LABELS = {"keep", "maybe", "exclude"}
JUDGMENTS = {"yes", "partial", "no", "insufficient_evidence"}
MISS_CATEGORIES = {"term_not_covered", "field_too_narrow", "time_window",
                   "source_not_indexed", "identifier_anomaly", "other"}
VIEW_VERSIONS = {"original", "publisher_translation", "abstract_only",
                 "exact_duplicate", "bilingual"}
GRADE_ORDER = ["low", "some_concerns", "high", "unclear"]

DEFAULT_WEIGHTS = {
    "question_match": 0.35, "method_match": 0.20, "population_match": 0.15,
    "evidence_quality": 0.15, "recency": 0.10, "facet_coverage": 0.05,
}


# ── shared helpers ──────────────────────────────────────────────────────────

def _title_sim(a, b) -> float:
    ta, tb = set(kit.normalize_title(a).split()), set(kit.normalize_title(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _year(v):
    if v is None:
        return None
    m = re.search(r"(18|19|20)\d{2}", str(v))
    return int(m.group(0)) if m else None


def norm_record(r: dict) -> dict:
    """Normalize core bibliographic fields; keep originals; list missing."""
    n = dict(r)
    n["doi_norm"] = kit.normalize_doi(r.get("doi"))
    n["title_norm"] = kit.normalize_title(r.get("title"))
    n["year_norm"] = _year(r.get("year"))
    au = r.get("authors")
    if isinstance(au, str):
        n["authors_list"] = [a.strip() for a in re.split(r";|,| and ", au) if a.strip()]
    elif isinstance(au, list):
        n["authors_list"] = [str(a).strip() for a in au if str(a).strip()]
    else:
        n["authors_list"] = []
    n["missing_fields"] = [f for f in CORE_FIELDS
                           if not r.get(f) and not (f == "year" and n["year_norm"])]
    return n


def _records(ir):
    return ir.get("records", [])


def _by_id(items):
    return {x.get("id"): x for x in items if x.get("id")}


def _dedup(records):
    """w4kit dedup over normalized records; returns clusters + id->cluster map."""
    res = kit.dedup_records(records)
    loc = {}
    for c in res["clusters"]:
        for rid in c["members"]:
            loc[rid] = c["cluster_id"]
    return res, loc


def _version_groups(records, dedup_loc):
    """Merge dedup clusters with explicit version_of links (preprint/published).
    Returns groups: {group_id: {members, kind, basis}} — never drops records."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    ids = [r.get("id") for r in records]
    for i in ids:
        find(i)
    for c in kit.dedup_records(records)["clusters"]:
        for m in c["members"][1:]:
            union(c["members"][0], m)
    for r in records:
        v = r.get("version_of")
        if v and v in parent:
            union(r.get("id"), v)
    groups = {}
    for r in records:
        root = find(r.get("id"))
        g = groups.setdefault(root, {"members": [], "version_links": []})
        g["members"].append(r.get("id"))
        if r.get("version_of"):
            g["version_links"].append({"from": r.get("id"), "to": r["version_of"]})
    out = []
    for i, (root, g) in enumerate(sorted(groups.items(), key=lambda kv: str(kv[0]))):
        out.append({"group_id": f"G{i+1:03d}", "representative": root,
                    "members": g["members"], "version_links": g["version_links"],
                    "n_members": len(g["members"])})
    return out


def _score_record(r, weights):
    feats = r.get("features") or {}
    if not feats:
        return None, []
    total_w = sum(weights.get(k, 0.0) for k in feats)
    if total_w <= 0:
        return None, []
    score = 0.0
    rationale = []
    for k, v in feats.items():
        w = weights.get(k, 0.0)
        fv = kit.to_float(v)
        if fv is None:
            continue
        fv = max(0.0, min(1.0, fv))
        contrib = w * fv / total_w
        score += contrib
        rationale.append({"feature": k, "value": fv, "weight": w,
                          "contribution": round(contrib, 4)})
    return round(score, 4), rationale


def _rank(records, ir, label_field="label"):
    """Deterministic ranking: tier first, then weighted feature score, then
    year desc, then id. Records without features are NOT scored (human queue)."""
    weights = dict(DEFAULT_WEIGHTS)
    weights.update((ir.get("ranking") or {}).get("weights") or {})
    tier_order = {"keep": 0, "include": 0, "maybe": 1, "exclude": 2}
    ranked, unscored = [], []
    for r in records:
        n = norm_record(r)
        score, rationale = _score_record(r, weights)
        n["score"] = score
        n["score_rationale"] = rationale
        n["weights_used"] = {k: weights.get(k, 0.0) for k in (r.get("features") or {})}
        if score is None:
            n["rank_status"] = "unscored_needs_features"
            unscored.append(n)
        else:
            ranked.append(n)
    ranked.sort(key=lambda n: (tier_order.get(n.get(label_field), 1),
                               -(n["score"] or 0.0),
                               -(n["year_norm"] or 0), str(n.get("id"))))
    for i, n in enumerate(ranked):
        n["rank"] = i + 1
    ranked.extend(unscored)
    return ranked, weights


def _metrics_at_k(ranked, k, label_field="graded_relevance"):
    """Precision@k / nDCG@k over AGENT-JUDGED graded labels (0..3) if present.
    Never presented as organizer ground truth."""
    labeled = [r for r in ranked if r.get(label_field) is not None]
    if not labeled:
        return None
    top = ranked[:k]
    rel = [max(0, int(kit.to_float(r.get(label_field)) or 0)) for r in top]
    hits = sum(1 for x in rel if x >= 2)
    import math
    dcg = sum((2 ** x - 1) / math.log2(i + 2) for i, x in enumerate(rel))
    ideal = sorted([max(0, int(kit.to_float(r.get(label_field)) or 0))
                    for r in labeled], reverse=True)[:k]
    idcg = sum((2 ** x - 1) / math.log2(i + 2) for i, x in enumerate(ideal))
    return {"k": k, "precision_at_k": round(hits / k, 4) if k else None,
            "ndcg_at_k": round(dcg / idcg, 4) if idcg else None,
            "labels": "agent_judged_not_ground_truth",
            "n_labeled": len(labeled)}


def _match(ref, records):
    """Hit test: DOI exact first, then fuzzy title (+year compatibility)."""
    rd = kit.normalize_doi(ref.get("doi"))
    if rd:
        hits = [r["id"] for r in records if r.get("doi_norm") == rd]
        if hits:
            return hits, "doi_exact"
    best, best_sim = [], 0.0
    for r in records:
        sim = _title_sim(ref.get("title", ""), r.get("title", ""))
        ry, fy = _year(ref.get("year")), r.get("year_norm")
        year_ok = (ry is None or fy is None or abs(ry - fy) <= 1)
        if sim >= 0.85 and year_ok and sim > best_sim:
            best, best_sim = [r["id"]], sim
        elif sim >= 0.85 and year_ok and sim == best_sim:
            best.append(r["id"])
    if best:
        return best, f"fuzzy_title_year(sim={best_sim:.2f})"
    return [], "no_match"


def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["-"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ")
                                     for c in row) + " |")
    return "\n".join(out)


def _loc_str(ev):
    if not isinstance(ev, dict):
        return str(ev)
    bits = [ev.get("source_id", "?")]
    for k in ("page", "paragraph_id", "table", "field"):
        if ev.get(k) is not None:
            bits.append(f"{k}={ev[k]}")
    if ev.get("quote"):
        q = str(ev["quote"])
        bits.append('"' + (q[:80] + ("..." if len(q) > 80 else "")) + '"')
    return " ".join(bits)


# ── validation ──────────────────────────────────────────────────────────────

def validate_ir(ir: dict) -> dict:
    errors, warnings = [], []
    if ir.get("ir_version") != IR_VERSION:
        errors.append(f"ir_version must be {IR_VERSION}")
    if not ir.get("case_id"):
        errors.append("case_id required")
    kind = ir.get("kind")
    if kind not in KINDS:
        errors.append(f"unknown kind '{kind}'; expected one of {sorted(KINDS)}")
    srcs = ir.get("sources", [])
    sids = [s.get("id") for s in srcs]
    if not srcs:
        errors.append("no sources registered; every record needs a source locator")
    if len(set(sids)) != len(sids):
        errors.append("duplicate source ids")
    for s in srcs:
        if not s.get("id"):
            errors.append("source without id")
        if not s.get("name") and not s.get("path"):
            warnings.append(f"source {s.get('id')}: no name/path (hard to re-verify)")
    errors.extend(kit.check_sources(ir))

    records = _records(ir)
    rids = [r.get("id") for r in records]
    if len(set(rids)) != len(rids):
        errors.append("duplicate record ids")
    queries = _by_id(ir.get("queries", []))
    for r in records:
        rid = r.get("id", "?")
        if not r.get("id"):
            errors.append("record without id")
        if not r.get("title") and not r.get("doi") and kind != "patent_search":
            errors.append(f"record {rid}: needs title or doi (no fabricated records)")
        if not r.get("source_id"):
            errors.append(f"record {rid}: missing source_id (provenance required)")
        if r.get("status") and r["status"] not in kit.RECORD_STATUS:
            errors.append(f"record {rid}: invalid status '{r['status']}'")
        if r.get("query_id") and queries and r["query_id"] not in queries:
            errors.append(f"record {rid}: query_id '{r['query_id']}' not in queries")
        if r.get("query_id") and not queries:
            warnings.append(f"record {rid}: query_id given but no queries registered")
        if not r.get("snippet") and kind in ("multi_db_merge", "query_planning",
                                             "question_driven", "coverage_analysis"):
            warnings.append(f"record {rid}: no raw response snippet kept")
        for f, loc in (r.get("field_sources") or {}).items():
            if isinstance(loc, dict) and loc.get("source_id") and loc["source_id"] not in set(sids):
                errors.append(f"record {rid}: field_sources[{f}] unknown source")
    for q in ir.get("queries", []):
        if not q.get("id") or not q.get("query_string"):
            errors.append("query needs id + query_string (original query must be kept)")
    for u in ir.get("uncertainty", []):
        if not u.get("item") or not u.get("reason"):
            warnings.append("uncertainty entry should have item + reason")

    if kind in KINDS:
        v = _VALIDATORS[kind](ir, set(sids), _by_id(records), queries)
        errors.extend(v[0])
        warnings.extend(v[1])
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _v_query_planning(ir, sids, rmap, queries):
    e, w = [], []
    rq = ir.get("research_question")
    if not rq or not rq.get("text"):
        e.append("research_question.text required")
    facets = _by_id(ir.get("facets", []))
    if not facets:
        w.append("no facets: keyword expansion structure not recorded")
    for q in ir.get("queries", []):
        if q.get("facet_id") and q["facet_id"] not in facets:
            e.append(f"query {q.get('id')}: unknown facet_id")
        if not q.get("database"):
            w.append(f"query {q.get('id')}: database not recorded")
        if not q.get("round"):
            w.append(f"query {q.get('id')}: round not recorded (multi-round planning)")
    for r in _records(ir):
        if not r.get("matched_queries"):
            w.append(f"record {r.get('id')}: matched_queries empty (recall path unclear)")
        for mq in r.get("matched_queries", []):
            if queries and mq not in queries:
                e.append(f"record {r.get('id')}: matched query '{mq}' not registered")
        if not r.get("features") and not r.get("relevance_rationale"):
            w.append(f"record {r.get('id')}: no relevance features/rationale")
    return e, w


def _v_question_driven(ir, sids, rmap, queries):
    e, w = [], []
    qs = ir.get("questions", [])
    if not qs:
        e.append("questions[] required (fixed research questions)")
    sqids = set()
    for q in qs:
        if not q.get("id") or not q.get("text"):
            e.append("question needs id + text")
        for sq in q.get("subquestions", []):
            if not sq.get("id") or not sq.get("text"):
                e.append(f"question {q.get('id')}: subquestion needs id + text")
            sqids.add(sq.get("id"))
    for q in ir.get("queries", []):
        if not q.get("subquestion_id"):
            w.append(f"query {q.get('id')}: not linked to a subquestion")
        elif q["subquestion_id"] not in sqids:
            e.append(f"query {q.get('id')}: unknown subquestion_id")
    for r in _records(ir):
        if not r.get("decision"):
            e.append(f"record {r.get('id')}: all-record screening requires a decision")
        elif r["decision"] not in DECISIONS:
            e.append(f"record {r.get('id')}: invalid decision")
        if r.get("decision") in ("include", "exclude") and not r.get("evidence") \
                and r.get("status") != "insufficient_evidence":
            w.append(f"record {r.get('id')}: decision without evidence locator")
        for sq in r.get("subquestion_ids", []):
            if sq not in sqids:
                e.append(f"record {r.get('id')}: unknown subquestion '{sq}'")
    if not ir.get("stopping", {}).get("reason"):
        w.append("stopping.reason not recorded (when/why search stopped)")
    return e, w


def _v_screen_rank(ir, sids, rmap, queries):
    e, w = [], []
    crit = _by_id(ir.get("criteria", []))
    if not crit:
        e.append("criteria[] required (label system must be checkable)")
    for c in ir.get("criteria", []):
        if c.get("type") not in ("include", "exclude"):
            e.append(f"criterion {c.get('id')}: type must be include/exclude")
    for r in _records(ir):
        rid = r.get("id")
        if r.get("label") not in LABELS:
            e.append(f"record {rid}: label must be keep/maybe/exclude")
        if not r.get("reason_code"):
            e.append(f"record {rid}: reason_code required (per-record rationale)")
        elif crit and r["reason_code"] not in crit:
            e.append(f"record {rid}: reason_code '{r['reason_code']}' not in criteria")
        if r.get("label") != "maybe" and not r.get("evidence"):
            w.append(f"record {rid}: keep/exclude without evidence snippet")
        if not r.get("features"):
            w.append(f"record {rid}: no features -> unscored, goes to human queue")
        if r.get("version_of") and r["version_of"] not in rmap:
            e.append(f"record {rid}: version_of '{r['version_of']}' unknown")
    return e, w


def _v_citation_tracking(ir, sids, rmap, queries):
    e, w = [], []
    seeds = ir.get("seeds", [])
    if not seeds:
        e.append("seeds[] required (record ids)")
    for s in seeds:
        if s not in rmap:
            e.append(f"seed '{s}' not in records")
    edges = ir.get("edges", [])
    if not edges:
        e.append("edges[] required (retained reference graph)")
    for i, ed in enumerate(edges):
        if ed.get("direction") not in ("forward", "backward"):
            e.append(f"edge {i}: direction must be forward/backward (got {ed.get('direction')})")
        if not ed.get("from") or not ed.get("to"):
            e.append(f"edge {i}: from/to required")
        if not ed.get("source_id"):
            e.append(f"edge {i}: source_id required (every citation edge needs a source)")
        for end in ("from", "to"):
            if ed.get(end) and ed[end] not in rmap:
                w.append(f"edge {i}: {end} '{ed[end]}' has no record metadata (stub kept)")
    md = ir.get("max_depth", 2)
    if not isinstance(md, int) or md < 1 or md > 5:
        e.append("max_depth must be int 1..5")
    return e, w


def _v_multi_db(ir, sids, rmap, queries):
    e, w = [], []
    dbs = _by_id(ir.get("databases", []))
    if not dbs:
        e.append("databases[] required")
    for d in ir.get("databases", []):
        if d.get("priority") is None:
            w.append(f"database {d.get('id')}: no merge priority (default 99)")
    for q in ir.get("queries", []):
        if q.get("database_id") and q["database_id"] not in dbs:
            e.append(f"query {q.get('id')}: unknown database_id")
    for r in _records(ir):
        rid = r.get("id")
        if not r.get("database_id"):
            e.append(f"record {rid}: database_id required")
        elif r["database_id"] not in dbs:
            e.append(f"record {rid}: unknown database_id")
        if not r.get("field_sources"):
            w.append(f"record {rid}: no field-level sources (per-field provenance)")
    if not ir.get("field_mapping"):
        w.append("field_mapping empty: raw field names used as-is")
    return e, w


def _v_incremental(ir, sids, rmap, queries):
    e, w = [], []
    snaps = ir.get("snapshots", [])
    if not snaps:
        e.append("snapshots[] required (organizer-local import states)")
    seen = set()
    for s in snaps:
        if not s.get("id"):
            e.append("snapshot needs id")
        if s.get("id") in seen:
            e.append(f"duplicate snapshot id {s.get('id')}")
        seen.add(s.get("id"))
        win = s.get("window") or {}
        if not win.get("start") or not win.get("end"):
            e.append(f"snapshot {s.get('id')}: window.start/end required")
        if not s.get("imported_at"):
            w.append(f"snapshot {s.get('id')}: imported_at not recorded")
        for rid in s.get("record_ids", []):
            if rid not in rmap:
                e.append(f"snapshot {s.get('id')}: unknown record '{rid}'")
    for r in _records(ir):
        if r.get("version_of") and r["version_of"] not in rmap:
            e.append(f"record {r.get('id')}: version_of unknown")
    if ir.get("live_claim"):
        e.append("live_claim forbidden: only organizer-local import states, no live/latest claim")
    return e, w


def _v_coverage(ir, sids, rmap, queries):
    e, w = [], []
    refs = ir.get("reference_set", [])
    if not refs:
        e.append("reference_set[] required (independent denominator, not derived from results)")
    refids = [x.get("id") for x in refs]
    if len(set(refids)) != len(refids):
        e.append("duplicate reference_set ids")
    for x in refs:
        if not x.get("id") or not x.get("title"):
            e.append("reference item needs id + title")
        if not x.get("source_id"):
            e.append(f"reference {x.get('id')}: source_id required (frozen known set)")
        if not x.get("inclusion_reason"):
            w.append(f"reference {x.get('id')}: inclusion_reason not recorded")
        if x.get("unusable"):
            w.append(f"reference {x.get('id')}: marked unusable ({x.get('unusable')})")
    for x in ir.get("miss_attributions", []):
        if x.get("reference_id") not in set(refids):
            e.append(f"miss attribution: unknown reference_id {x.get('reference_id')}")
        if x.get("category") not in MISS_CATEGORIES:
            e.append(f"miss attribution {x.get('reference_id')}: category must be one of {sorted(MISS_CATEGORIES)}")
        if not x.get("explanation"):
            e.append(f"miss attribution {x.get('reference_id')}: explanation required (specific query/field/source)")
    for rnd in ir.get("supplementary_rounds", []):
        if not rnd.get("id") or not rnd.get("query_ids"):
            e.append("supplementary round needs id + query_ids")
        for q in rnd.get("query_ids", []):
            if queries and q not in queries:
                e.append(f"round {rnd.get('id')}: unknown query '{q}'")
    return e, w


def _v_systematic(ir, sids, rmap, queries):
    e, w = [], []
    proto = ir.get("protocol") or {}
    for k in ("databases", "search_date"):
        if not proto.get(k):
            w.append(f"protocol.{k} not recorded")
    crit = _by_id(ir.get("criteria", []))
    if not crit:
        e.append("criteria[] with reason codes required")
    reviewers = set()
    for r in _records(ir):
        rid = r.get("id")
        revs = r.get("reviewers", [])
        if not revs:
            e.append(f"record {rid}: reviewers[] required (dual independent screening)")
        for rv in revs:
            reviewers.add(rv.get("reviewer"))
            if rv.get("decision") not in DECISIONS:
                e.append(f"record {rid}: reviewer decision invalid")
            if not rv.get("reason_code"):
                e.append(f"record {rid}: reviewer reason_code required")
            elif crit and rv["reason_code"] not in crit:
                e.append(f"record {rid}: reason_code '{rv['reason_code']}' not in criteria")
            if rv.get("decision") != "maybe" and not rv.get("evidence"):
                w.append(f"record {rid}: reviewer {rv.get('reviewer')} no evidence snippet")
        if len(revs) >= 2:
            ds = {rv.get("decision") for rv in revs}
            if len(ds) > 1 and not r.get("adjudication"):
                e.append(f"record {rid}: reviewer disagreement without adjudication")
        if r.get("adjudication"):
            adj = r["adjudication"]
            if adj.get("decision") not in DECISIONS:
                e.append(f"record {rid}: adjudication decision invalid")
            if not adj.get("rationale"):
                e.append(f"record {rid}: adjudication rationale required")
    if len(reviewers) < 2 and _records(ir):
        w.append("fewer than 2 distinct reviewers (single-reviewer screening flagged)")
    return e, w


def _v_appraisal(ir, sids, rmap, queries):
    e, w = [], []
    tool = ir.get("appraisal_tool") or {}
    dims = _by_id(tool.get("dimensions", []))
    if not dims:
        e.append("appraisal_tool.dimensions[] required (the scale)")
    if not tool.get("name"):
        w.append("appraisal_tool.name not recorded")
    for r in _records(ir):
        rid = r.get("id")
        if not r.get("study_type"):
            w.append(f"record {rid}: study_type not recorded (dimension applicability)")
        rdims = r.get("dimensions", [])
        if not rdims:
            e.append(f"record {rid}: dimensions[] required (per-dimension judgments)")
        seen = set()
        for d in rdims:
            did = d.get("dimension_id")
            if did not in dims:
                e.append(f"record {rid}: unknown dimension '{did}'")
            if did in seen:
                e.append(f"record {rid}: duplicate dimension '{did}'")
            seen.add(did)
            j = d.get("judgment")
            if j not in JUDGMENTS:
                e.append(f"record {rid}/{did}: judgment must be one of {sorted(JUDGMENTS)}")
            if j != "insufficient_evidence":
                ev = d.get("evidence") or []
                if not ev:
                    e.append(f"record {rid}/{did}: judgment '{j}' requires evidence locator (or abstain)")
                for evx in ev:
                    if not evx.get("quote") and not evx.get("paragraph_id") \
                            and not evx.get("page") and not evx.get("table"):
                        w.append(f"record {rid}/{did}: evidence has no quote/page/paragraph locator")
            else:
                if d.get("grade") not in (None, "unclear", "not_assessable"):
                    e.append(f"record {rid}/{did}: abstain must not carry a confident grade")
            if j != "insufficient_evidence" and not d.get("grade"):
                e.append(f"record {rid}/{did}: grade required for non-abstain judgment")
            if not d.get("rationale"):
                w.append(f"record {rid}/{did}: rationale missing")
        applicable = [did for did, dd in dims.items()
                      if not dd.get("applies_to") or r.get("study_type") in dd.get("applies_to", [])]
        missing = [d for d in applicable if d not in seen]
        if missing:
            w.append(f"record {rid}: applicable dimensions not judged: {missing} (flag, do not fabricate)")
    return e, w


def _v_cross_language(ir, sids, rmap, queries):
    e, w = [], []
    works = _by_id(ir.get("works", []))
    if not works:
        e.append("works[] required (work-level identity)")
    views = ir.get("views", [])
    if not views:
        e.append("views[] required (language/version views of works)")
    vids = [v.get("id") for v in views]
    if len(set(vids)) != len(vids):
        e.append("duplicate view ids")
    for v in views:
        vid = v.get("id")
        if v.get("work_id") not in works:
            e.append(f"view {vid}: unknown work_id")
        if not v.get("language"):
            e.append(f"view {vid}: language required")
        if not v.get("body_language"):
            w.append(f"view {vid}: body_language not recorded")
        if v.get("version") not in VIEW_VERSIONS:
            e.append(f"view {vid}: version must be one of {sorted(VIEW_VERSIONS)}")
        if not v.get("source_id"):
            e.append(f"view {vid}: source_id required")
    for t in ir.get("term_alignments", []):
        if not t.get("term") or not t.get("language") or not t.get("render"):
            e.append("term alignment needs term + language + render")
        if not t.get("source_id"):
            e.append(f"term '{t.get('term')}': source_id required (alignment must be checkable)")
    return e, w


def _v_patent(ir, sids, rmap, queries):
    e, w = [], []
    pats = ir.get("patents", [])
    if not pats:
        e.append("patents[] required")
    pids = {p.get("id") for p in pats}
    for p in pats:
        pid = p.get("id")
        nums = p.get("numbers") or {}
        if not any(nums.get(k) for k in ("publication", "application", "grant")):
            e.append(f"patent {pid}: at least one number (publication/application/grant)")
        if not p.get("source_id"):
            e.append(f"patent {pid}: source_id required (authorized source only)")
        if p.get("authorization") not in (None, "green", "yellow", "red"):
            e.append(f"patent {pid}: authorization must be green/yellow/red")
        if p.get("authorization") == "red":
            w.append(f"patent {pid}: red-tier source; do not display restricted content")
        for fl in p.get("family_links", []):
            if fl.get("to") not in pids:
                e.append(f"patent {pid}: family link to unknown patent '{fl.get('to')}'")
            if not fl.get("basis") or not fl.get("source_id"):
                e.append(f"patent {pid}: family link needs basis + source_id (observed links only)")
        for cl in p.get("claims", []):
            if not cl.get("version"):
                e.append(f"patent {pid}: claim version label required")
            loc = cl.get("locator") or {}
            if not loc.get("source_id"):
                e.append(f"patent {pid}: claim {cl.get('version')} needs source locator")
        ls = p.get("legal_status")
        if ls and not ls.get("source_id"):
            e.append(f"patent {pid}: legal_status needs source_id + as_of (else UNKNOWN)")
        if ls and not ls.get("as_of"):
            w.append(f"patent {pid}: legal_status without as_of date (lag risk)")
    return e, w


_VALIDATORS = {
    "query_planning": _v_query_planning,
    "question_driven": _v_question_driven,
    "screen_rank": _v_screen_rank,
    "citation_tracking": _v_citation_tracking,
    "multi_db_merge": _v_multi_db,
    "incremental_tracking": _v_incremental,
    "coverage_analysis": _v_coverage,
    "systematic_screening": _v_systematic,
    "quality_appraisal": _v_appraisal,
    "cross_language": _v_cross_language,
    "patent_search": _v_patent,
}


# ── builders (real computation) ─────────────────────────────────────────────

def _b_query_planning(ir, out_dir):
    records = [norm_record(r) for r in _records(ir)]
    dedup, loc = _dedup(records)
    ranked, weights = _rank(records, ir, label_field="label")
    queries = ir.get("queries", [])
    facets = ir.get("facets", [])
    # per-facet / per-round recall of the candidate set
    facet_hits = {f["id"]: [] for f in facets}
    round_counts = {}
    for r in records:
        for mq in r.get("matched_queries", []):
            q = queries and next((x for x in queries if x.get("id") == mq), None)
            if q:
                if q.get("facet_id") in facet_hits:
                    facet_hits[q["facet_id"]].append(r["id"])
                round_counts[q.get("round")] = round_counts.get(q.get("round"), 0) + 1
    uncovered = [f["id"] for f in facets if not facet_hits.get(f["id"])]
    k = (ir.get("ranking") or {}).get("k", 10)
    metrics = _metrics_at_k(ranked, k)
    payload = {
        "research_question": ir.get("research_question"),
        "facets": [{"id": f.get("id"), "text": f.get("text"),
                    "terms": f.get("terms", []),
                    "expanded_terms": f.get("expanded_terms", []),
                    "n_hits": len(facet_hits.get(f.get("id"), [])),
                    "hit_record_ids": facet_hits.get(f.get("id"), [])} for f in facets],
        "queries": queries,
        "n_candidates_raw": len(records),
        "dedup": {kk: dedup[kk] for kk in ("n_input", "n_clusters", "n_duplicates_removed")},
        "dedup_clusters": dedup["clusters"],
        "ranked_records": ranked,
        "weights": weights,
        "metrics_at_k": metrics,
        "uncovered_facets": uncovered,
        "gaps": ir.get("gaps", []),
    }
    sections = [
        ("Research question & facets",
         f"**Question:** {(ir.get('research_question') or {}).get('text', '-')}\n\n" +
         _md_table(["facet", "terms", "expanded", "hits"],
                   [[f.get("id"), ", ".join(f.get("terms", [])),
                     ", ".join(f.get("expanded_terms", [])),
                     len(facet_hits.get(f.get("id"), []))] for f in facets])),
        ("Query plan (original queries preserved)",
         _md_table(["id", "round", "facet", "database", "query"],
                   [[q.get("id"), q.get("round"), q.get("facet_id"),
                     q.get("database"), q.get("query_string")] for q in queries])),
        ("Dedup", f"{dedup['n_input']} raw records -> {dedup['n_clusters']} unique "
                  f"({dedup['n_duplicates_removed']} duplicates merged, provenance kept)."),
        ("Ranked candidates (score = weighted features; ties: tier, year, id)",
         _md_table(["rank", "id", "title", "year", "score", "label", "top rationale"],
                   [[r.get("rank", "-"), r["id"], (r.get("title") or "")[:70],
                     r.get("year_norm"), r.get("score"), r.get("label", "-"),
                     "; ".join(f"{x['feature']}={x['value']}*{x['weight']}"
                               for x in (r.get("score_rationale") or [])[:3])]
                    for r in ranked])),
        ("Coverage gaps / uncovered facets",
         ("Uncovered facets: " + ", ".join(uncovered)) if uncovered else
         "All facets have at least one hit. See gaps[] for missing metadata/sources."),
    ]
    if metrics:
        sections.append(("Ranking metrics (agent-judged labels, NOT ground truth)",
                         f"Precision@{k}={metrics['precision_at_k']}, nDCG@{k}={metrics['ndcg_at_k']}"))
    summary = {"n_raw": len(records), "n_unique": dedup["n_clusters"],
               "n_ranked": sum(1 for r in ranked if r.get("score") is not None),
               "uncovered_facets": uncovered, "metrics_at_k": metrics}
    return payload, sections, summary


def _b_question_driven(ir, out_dir):
    records = [norm_record(r) for r in _records(ir)]
    dedup, _ = _dedup(records)
    sq_map = {}
    for q in ir.get("questions", []):
        for sq in q.get("subquestions", []):
            sq_map[sq["id"]] = {"question_id": q.get("id"), "text": sq.get("text"),
                                "queries": [], "evidence_records": []}
    for q in ir.get("queries", []):
        if q.get("subquestion_id") in sq_map:
            sq_map[q["subquestion_id"]]["queries"].append(q.get("id"))
    screened = []
    for r in records:
        n = dict(r)
        n.setdefault("status", "reported" if r.get("evidence") else "insufficient_evidence")
        screened.append(n)
        for sq in r.get("subquestion_ids", []):
            if sq in sq_map and r.get("decision") == "include":
                sq_map[sq]["evidence_records"].append(r["id"])
    sufficiency = []
    for sqid, sq in sq_map.items():
        n_ev = len(sq["evidence_records"])
        sufficiency.append({"subquestion_id": sqid, "text": sq["text"],
                            "n_queries": len(sq["queries"]),
                            "n_included_evidence": n_ev,
                            "evidence_sufficient": "yes" if n_ev >= 1 else "no_gap",
                            "basis": "included records mapped to this subquestion (agent judgment)"})
    gaps = [s["subquestion_id"] for s in sufficiency if s["evidence_sufficient"] == "no_gap"]
    counts = {d: sum(1 for r in screened if r.get("decision") == d) for d in DECISIONS}
    payload = {"questions": ir.get("questions"), "queries": ir.get("queries"),
               "subquestion_evidence_map": sq_map, "sufficiency": sufficiency,
               "screened_records": screened, "screening_counts": counts,
               "dedup": {kk: dedup[kk] for kk in ("n_input", "n_clusters", "n_duplicates_removed")},
               "dedup_clusters": dedup["clusters"],
               "stopping": ir.get("stopping", {}),
               "evidence_gaps": gaps}
    sections = [
        ("Question decomposition -> queries -> evidence",
         _md_table(["subquestion", "text", "queries", "included evidence", "sufficient"],
                   [[s["subquestion_id"], s["text"][:60], s["n_queries"],
                     s["n_included_evidence"], s["evidence_sufficient"]] for s in sufficiency])),
        ("All-record screening (every candidate decided)",
         _md_table(["id", "title", "decision", "reason", "evidence"],
                   [[r["id"], (r.get("title") or "")[:60], r.get("decision"),
                     r.get("reason_code", r.get("rationale", "-")),
                     "; ".join(_loc_str(e) for e in (r.get("evidence") or [])[:2])]
                    for r in screened])),
        ("Screening counts", ", ".join(f"{k}={v}" for k, v in counts.items()) +
         f"; dedup {dedup['n_input']}->{dedup['n_clusters']}"),
        ("Stopping decision",
         f"reason: {ir.get('stopping', {}).get('reason', 'NOT RECORDED')}; "
         f"open gaps: {', '.join(gaps) if gaps else 'none'}"),
    ]
    summary = {"n_records": len(records), "screening_counts": counts,
               "subquestions": len(sq_map), "evidence_gaps": gaps}
    return payload, sections, summary


def _b_screen_rank(ir, out_dir):
    records = [norm_record(r) for r in _records(ir)]
    dedup, _ = _dedup(records)
    groups = _version_groups(records, None)
    ranked, weights = _rank(records, ir)
    k = (ir.get("ranking") or {}).get("k", 10)
    metrics = _metrics_at_k(ranked, k)
    label_counts = {l: sum(1 for r in records if r.get("label") == l) for l in LABELS}
    reason_counts = {}
    for r in records:
        rc = r.get("reason_code", "?")
        reason_counts[rc] = reason_counts.get(rc, 0) + 1
    human_queue = [r["id"] for r in ranked
                   if r.get("label") == "maybe" or r.get("score") is None]
    payload = {"criteria": ir.get("criteria", []),
               "label_counts": label_counts, "reason_code_counts": reason_counts,
               "dedup": {kk: dedup[kk] for kk in ("n_input", "n_clusters", "n_duplicates_removed")},
               "dedup_clusters": dedup["clusters"],
               "version_groups": groups,
               "ranked_records": ranked, "weights": weights,
               "metrics_at_k": metrics, "human_review_queue": human_queue,
               "tie_break_rule": "tier(keep<maybe<exclude) -> score desc -> year desc -> id asc"}
    sections = [
        ("Label system (criteria)",
         _md_table(["code", "type", "criterion"],
                   [[c.get("id"), c.get("type"), c.get("text")] for c in ir.get("criteria", [])])),
        ("Screening result",
         ", ".join(f"{k2}={v}" for k2, v in label_counts.items()) +
         f"; duplicates merged: {dedup['n_duplicates_removed']}; "
         f"version groups (preprint/published kept linked): {sum(1 for g in groups if g['n_members']>1)}"),
        ("Ranked list (explainable score)",
         _md_table(["rank", "id", "title", "label", "score", "reason_code", "feature contributions"],
                   [[r.get("rank", "-"), r["id"], (r.get("title") or "")[:60],
                     r.get("label"), r.get("score"), r.get("reason_code"),
                     "; ".join(f"{x['feature']}:{x['contribution']}"
                               for x in (r.get("score_rationale") or []))]
                    for r in ranked])),
        ("Human review queue (maybe / unscored)",
         ", ".join(human_queue) if human_queue else "empty"),
    ]
    if metrics:
        sections.append(("Metrics (agent-judged labels)",
                         f"Precision@{k}={metrics['precision_at_k']}, nDCG@{k}={metrics['ndcg_at_k']}"))
    summary = {"n_records": len(records), "label_counts": label_counts,
               "n_unique": dedup["n_clusters"], "human_queue": len(human_queue),
               "metrics_at_k": metrics}
    return payload, sections, summary


def _b_citation_tracking(ir, out_dir):
    records = [norm_record(r) for r in _records(ir)]
    rmap = _by_id(records)
    dedup, loc = _dedup(records)
    edges = ir.get("edges", [])
    max_depth = ir.get("max_depth", 2)
    # adjacency: traversing from node x,
    #   backward edge (x -> ref) means ref is a reference OF x  => reach ref
    #   forward edge (x -> citer) means citer CITES x           => reach citer
    adj = {}
    for ed in edges:
        adj.setdefault(ed["from"], []).append(ed)
    reached = {}   # rid -> {depth, path, directions}
    frontier = deque()
    for s in ir.get("seeds", []):
        reached[s] = {"depth": 0, "path": [], "seed": s}
        frontier.append((s, 0))
    stubs = []
    while frontier:
        node, depth = frontier.popleft()
        if depth >= max_depth:
            continue
        for ed in adj.get(node, []):
            tgt = ed["to"]
            if tgt in reached:
                continue
            hop = {"from": ed["from"], "to": tgt, "direction": ed["direction"],
                   "source_id": ed.get("source_id"), "context": ed.get("context")}
            reached[tgt] = {"depth": depth + 1,
                            "path": reached[node]["path"] + [hop], "seed": reached[node]["seed"]}
            if tgt not in rmap:
                stubs.append(tgt)
            frontier.append((tgt, depth + 1))
    expanded = []
    for rid, info in sorted(reached.items(), key=lambda kv: (kv[1]["depth"], str(kv[0]))):
        r = rmap.get(rid)
        item = {"id": rid, "depth": info["depth"], "seed": info["seed"],
                "path": info["path"],
                "directions": [h["direction"] for h in info["path"]],
                "metadata": "reported" if r else "not_reported_stub"}
        if r:
            item.update({k2: r.get(k2) for k2 in ("title", "year_norm", "doi_norm", "source_id")})
        expanded.append(item)
    fwd = sum(1 for e in edges if e["direction"] == "forward")
    bwd = sum(1 for e in edges if e["direction"] == "backward")
    per_depth = {}
    for it in expanded:
        d = it["depth"]
        per_depth[d] = per_depth.get(d, 0) + 1
    seeds_no_edges = [s for s in ir.get("seeds", []) if not adj.get(s)]
    payload = {"seeds": ir.get("seeds", []), "max_depth": max_depth,
               "n_edges": len(edges), "n_forward": fwd, "n_backward": bwd,
               "edges": edges, "expanded": expanded,
               "per_depth_counts": per_depth,
               "stub_nodes_no_metadata": sorted(set(stubs)),
               "seeds_without_outgoing_edges": seeds_no_edges,
               "dedup": {kk: dedup[kk] for kk in ("n_input", "n_clusters", "n_duplicates_removed")},
               "dedup_clusters": dedup["clusters"],
               "scope_note": "traversal over the organizer-retained reference graph only; "
                             "no live citation coverage claimed"}
    sections = [
        ("Graph scope",
         f"{len(edges)} retained edges ({fwd} forward / {bwd} backward), "
         f"seeds={ir.get('seeds')}, max_depth={max_depth}. "
         "Finite snapshot; edges without record metadata are kept as labelled stubs."),
        ("BFS expansion (path = per-hop direction + source)",
         _md_table(["id", "depth", "seed", "title", "path (direction@source)"],
                   [[it["id"], it["depth"], it["seed"],
                     (it.get("title") or "(stub: metadata not_reported)")[:55],
                     " -> ".join(f"{h['to']}[{h['direction']}@{h['source_id']}]"
                                 for h in it["path"]) or "(seed)"] for it in expanded])),
        ("Identity merge",
         f"{dedup['n_input']} records -> {dedup['n_clusters']} identities "
         f"({dedup['n_duplicates_removed']} merged; conflicts kept in clusters)."),
        ("Gaps",
         ("Seeds with no outgoing edges: " + ", ".join(seeds_no_edges) + ". ") if seeds_no_edges else "" +
         ("Stub nodes lacking metadata: " + ", ".join(sorted(set(stubs)))) if stubs else
         "No stub nodes; all reached nodes have record metadata."),
    ]
    summary = {"n_expanded": len(expanded), "per_depth": per_depth,
               "n_forward": fwd, "n_backward": bwd,
               "stubs": sorted(set(stubs)), "n_unique_identities": dedup["n_clusters"]}
    return payload, sections, summary


def _b_multi_db(ir, out_dir):
    dbs = _by_id(ir.get("databases", []))
    fmap = {k.lower(): v for k, v in (ir.get("field_mapping") or {}).items()}
    records = []
    for r in _records(ir):
        n = norm_record(r)
        raw = r.get("raw_fields") or {f: r.get(f) for f in CORE_FIELDS if r.get(f) is not None}
        n["canonical_fields"] = {fmap.get(k.lower(), k.lower()): v for k, v in raw.items()}
        records.append(n)
    dedup, loc = _dedup(records)
    # merge with per-field priority + provenance
    merged = []
    for c in dedup["clusters"]:
        members = c["records"]
        def prio(r):
            return dbs.get(r.get("database_id"), {}).get("priority", 99)
        ordered = sorted(members, key=lambda r: (prio(r), str(r.get("id"))))
        m = {"cluster_id": c["cluster_id"], "members": c["members"],
             "match": c["match"], "fields": {}, "field_provenance": {},
             "conflicts": c["conflicts"]}
        all_fields = set()
        for r in members:
            all_fields.update(r.get("canonical_fields", {}).keys())
            all_fields.update(f for f in CORE_FIELDS if r.get(f) is not None)
        for f in sorted(all_fields):
            candidates = []
            for r in ordered:
                v = r.get("canonical_fields", {}).get(f, r.get(f))
                if v is not None and v != "":
                    candidates.append((r, v))
            if not candidates:
                m["fields"][f] = None
                m["field_provenance"][f] = {"status": "not_reported_by_any_source"}
                continue
            win_r, win_v = candidates[0]
            m["fields"][f] = win_v
            m["field_provenance"][f] = {
                "status": "reported", "value": win_v,
                "database_id": win_r.get("database_id"),
                "record_id": win_r.get("id"), "query_id": win_r.get("query_id"),
                "source_id": win_r.get("source_id"),
                "snippet": win_r.get("snippet"),
                "field_source": (win_r.get("field_sources") or {}).get(f),
                "priority": prio(win_r),
                "alternatives": [{"record_id": r.get("id"), "database_id": r.get("database_id"),
                                  "value": v} for r, v in candidates[1:] if str(v) != str(win_v)],
            }
        merged.append(m)
    # coverage matrix db x field
    core = sorted({f for m2 in merged for f in m2["fields"]})
    coverage = {}
    for did, d in dbs.items():
        recs = [r for r in records if r.get("database_id") == did]
        coverage[did] = {"name": d.get("name"), "n_records": len(recs),
                         "fields_present": {f: sum(1 for r in recs
                                                   if r.get("canonical_fields", {}).get(f, r.get(f)) not in (None, ""))
                                            for f in core},
                         "status": "ok" if recs else "empty_or_unavailable"}
    gaps = []
    for did, cv in coverage.items():
        if cv["n_records"] == 0:
            gaps.append({"type": "database_no_results", "database_id": did,
                         "handling": "human_confirm: source unavailable or query mismatch; not silently dropped"})
    for f in core:
        covering = [did for did, cv in coverage.items() if cv["fields_present"].get(f, 0) > 0]
        if not covering:
            gaps.append({"type": "field_missing_everywhere", "field": f,
                         "handling": "human_confirm"})
        elif len(covering) == 1:
            gaps.append({"type": "field_single_source", "field": f, "database_id": covering[0],
                         "handling": "note single-source dependence"})
    single_db = [m2["cluster_id"] for m2 in merged
                 if len({next((r.get("database_id") for r in records if r.get("id") == mid), None)
                         for mid in m2["members"]}) == 1]
    payload = {"databases": ir.get("databases", []), "queries": ir.get("queries", []),
               "field_mapping": fmap,
               "n_raw": len(records), "n_merged": len(merged),
               "n_duplicates_removed": dedup["n_duplicates_removed"],
               "merged_records": merged, "coverage_matrix": coverage,
               "gaps": gaps, "single_database_records": single_db,
               "dedup_clusters": dedup["clusters"]}
    sections = [
        ("Per-database coverage (fields present / records)",
         _md_table(["database", "n_records"] + core,
                   [[did, cv["n_records"]] + [cv["fields_present"].get(f, 0) for f in core]
                    for did, cv in coverage.items()])),
        ("Merged records (field value <- highest-priority source; alternatives kept)",
         _md_table(["cluster", "members", "title", "year", "doi", "conflicts"],
                   [[m2["cluster_id"], ",".join(m2["members"]),
                     str(m2["fields"].get("title"))[:55], m2["fields"].get("year"),
                     m2["fields"].get("doi"),
                     "; ".join(x["field"] for x in m2["conflicts"])] for m2 in merged])),
        ("Field-level provenance example (first cluster)",
         "```json\n" + __import__("json").dumps(
             merged[0]["field_provenance"] if merged else {}, ensure_ascii=False, indent=1)[:1500] + "\n```"),
        ("Coverage gaps (explicit, never silently swallowed)",
         _md_table(["type", "detail", "handling"],
                   [[g["type"], g.get("database_id") or g.get("field"), g["handling"]] for g in gaps])
         if gaps else "none"),
    ]
    summary = {"n_raw": len(records), "n_merged": len(merged),
               "n_duplicates_removed": dedup["n_duplicates_removed"],
               "n_gaps": len(gaps), "single_db_records": len(single_db)}
    return payload, sections, summary


def _b_incremental(ir, out_dir):
    records = [norm_record(r) for r in _records(ir)]
    rmap = _by_id(records)
    snaps = ir.get("snapshots", [])
    def key_of(r):
        return r.get("doi_norm") or f"t:{r.get('title_norm')}|y:{r.get('year_norm')}"
    seen_keys = {}
    increments = []
    prev_end = None
    window_issues = []
    for s in snaps:
        win = s.get("window") or {}
        if prev_end is not None and win.get("start") != prev_end:
            window_issues.append({"snapshot": s.get("id"),
                                  "issue": "window not contiguous with previous",
                                  "prev_end": prev_end, "start": win.get("start"),
                                  "handling": "human_confirm: gap or overlap"})
        prev_end = win.get("end")
        new_ids, updated, retracted = [], [], []
        for rid in s.get("record_ids", []):
            r = rmap.get(rid)
            if not r:
                continue
            k = key_of(r)
            if r.get("retracted"):
                retracted.append(rid)
            if k not in seen_keys:
                new_ids.append(rid)
                seen_keys[k] = {"first_snapshot": s.get("id"), "record_id": rid}
            else:
                first = seen_keys[k]["record_id"]
                if rid != first:
                    updated.append({"record_id": rid, "version_of": first,
                                    "basis": "same dedup key, later import"})
                else:
                    changed = [f for f in CORE_FIELDS
                               if r.get(f) != rmap[first].get(f)] if first != rid else []
                    if changed:
                        updated.append({"record_id": rid, "changed_fields": changed})
        increments.append({"snapshot_id": s.get("id"), "window": win,
                           "imported_at": s.get("imported_at"),
                           "n_records": len(s.get("record_ids", [])),
                           "new": new_ids, "version_updates": updated,
                           "retracted": retracted,
                           "n_new": len(new_ids)})
    groups = _version_groups(records, None)
    payload = {"subscription": ir.get("subscription", {}),
               "snapshots": snaps, "increments": increments,
               "window_issues": window_issues,
               "dedup_key_rule": "normalized DOI, else normalized title + year",
               "seen_keys": seen_keys, "version_groups": groups,
               "watermark": {"last_window_end": prev_end,
                             "n_seen_keys": len(seen_keys)},
               "idempotent": True,
               "scope_note": "organizer-local import states only; NO live or latest-publication claim"}
    sections = [
        ("Incremental diff per import state (replayable)",
         _md_table(["snapshot", "window", "n_records", "new", "version_updates", "retracted"],
                   [[i["snapshot_id"], f"{i['window'].get('start')}..{i['window'].get('end')}",
                     i["n_records"], ",".join(i["new"]) or "-",
                     len(i["version_updates"]), ",".join(i["retracted"]) or "-"]
                    for i in increments])),
        ("Version chains (preprint -> published kept linked, not double-counted)",
         _md_table(["group", "members", "links"],
                   [[g["group_id"], ",".join(g["members"]),
                     "; ".join(f"{l['from']}->{l['to']}" for l in g["version_links"])]
                    for g in groups if g["n_members"] > 1]) or "none"),
        ("Window continuity",
         _md_table(["snapshot", "issue", "handling"],
                   [[w["snapshot"], w["issue"], w["handling"]] for w in window_issues])
         if window_issues else "contiguous windows; no drift detected"),
        ("Watermark / replay",
         f"last_window_end={prev_end}, seen_keys={len(seen_keys)}. "
         "Re-running the same snapshots yields identical increments (idempotent). "
         "No live/latest-publication claim is made."),
    ]
    summary = {"n_snapshots": len(snaps),
               "total_new": sum(i["n_new"] for i in increments),
               "window_issues": len(window_issues),
               "n_version_groups": sum(1 for g in groups if g["n_members"] > 1)}
    return payload, sections, summary


def _b_coverage(ir, out_dir):
    records = [norm_record(r) for r in _records(ir)]
    refs = ir.get("reference_set", [])
    usable = [x for x in refs if not x.get("unusable")]
    attrib = {a.get("reference_id"): a for a in ir.get("miss_attributions", [])}
    hit_rows, misses = [], []
    hit_ref_ids = set()
    for x in usable:
        hits, method = _match(x, records)
        row = {"reference_id": x["id"], "title": x.get("title"),
               "doi": kit.normalize_doi(x.get("doi")), "hit": bool(hits),
               "matched_record_ids": hits, "match_method": method,
               "source_id": x.get("source_id")}
        hit_rows.append(row)
        if hits:
            hit_ref_ids.add(x["id"])
        else:
            a = attrib.get(x["id"])
            misses.append({"reference_id": x["id"], "title": x.get("title"),
                           "attribution": a or {"category": "unattributed",
                                                "explanation": "NOT ATTRIBUTED — human_confirm required"},
                           "attributed": bool(a)})
    n_ref = len(usable)
    recall = len(hit_ref_ids) / n_ref if n_ref else None
    rounds = []
    remaining = {m["reference_id"] for m in misses}
    cumulative_hits = set(hit_ref_ids)
    for rnd in ir.get("supplementary_rounds", []):
        new_hits = []
        for rid in rnd.get("new_record_ids", []):
            r = next((x for x in records if x.get("id") == rid), None)
            if not r:
                continue
            for ref in usable:
                if ref["id"] in remaining:
                    hs, _ = _match(ref, [r])
                    if hs:
                        new_hits.append(ref["id"])
                        remaining.discard(ref["id"])
                        cumulative_hits.add(ref["id"])
        rounds.append({"round_id": rnd.get("id"), "query_ids": rnd.get("query_ids", []),
                       "new_reference_hits": sorted(set(new_hits)),
                       "n_new_hits": len(set(new_hits)),
                       "recall_after": round(len(cumulative_hits) / n_ref, 4) if n_ref else None,
                       "marginal_gain": "positive" if new_hits else "zero_stop_candidate"})
    unattributed = [m["reference_id"] for m in misses if not m["attributed"]]
    cat_counts = {}
    for m in misses:
        c = m["attribution"].get("category", "unattributed")
        cat_counts[c] = cat_counts.get(c, 0) + 1
    payload = {"reference_set": refs, "n_reference_total": len(refs),
               "n_reference_usable": n_ref,
               "n_unusable": len(refs) - n_ref,
               "denominator_note": "reference set is an independent frozen known-item list; "
                                   "NOT derived from the retrieved results",
               "hit_table": hit_rows, "recall": round(recall, 4) if recall is not None else None,
               "misses": misses, "miss_category_counts": cat_counts,
               "supplementary_rounds": rounds,
               "residual_misses": sorted(remaining),
               "unattributed_misses": unattributed,
               "retrieved_records": records}
    sections = [
        ("Coverage (independent denominator)",
         f"usable reference items: {n_ref} (of {len(refs)}; {len(refs)-n_ref} marked unusable). "
         f"hits: {len(hit_ref_ids)}; **recall = {recall:.4f}**" if recall is not None else "no usable references"),
        ("Per-reference hit status",
         _md_table(["reference", "title", "hit", "method", "matched records"],
                   [[h["reference_id"], (h["title"] or "")[:55], "Y" if h["hit"] else "N",
                     h["match_method"], ",".join(h["matched_record_ids"])] for h in hit_rows])),
        ("Miss attribution (specific query/field/source, not generic)",
         _md_table(["reference", "category", "explanation"],
                   [[m["reference_id"], m["attribution"].get("category"),
                     m["attribution"].get("explanation", "")[:90]] for m in misses])
         if misses else "no misses"),
        ("Supplementary rounds (real marginal gain)",
         _md_table(["round", "queries", "new hits", "recall after", "gain"],
                   [[r["round_id"], ",".join(r["query_ids"]), r["n_new_hits"],
                     r["recall_after"], r["marginal_gain"]] for r in rounds])
         if rounds else "none run"),
        ("Residual gaps",
         f"residual misses: {', '.join(sorted(remaining)) or 'none'}; "
         f"unattributed (human_confirm): {', '.join(unattributed) or 'none'}"),
    ]
    summary = {"n_reference_usable": n_ref, "recall": payload["recall"],
               "n_misses": len(misses), "unattributed": unattributed,
               "rounds": len(rounds), "residual": sorted(remaining)}
    return payload, sections, summary


def _b_systematic(ir, out_dir):
    records = [norm_record(r) for r in _records(ir)]
    dedup, loc = _dedup(records)
    final = []
    disagreements = []
    for r in records:
        revs = r.get("reviewers", [])
        ds = [rv.get("decision") for rv in revs]
        disagree = len(set(ds)) > 1
        adj = r.get("adjudication")
        if adj:
            decision = adj.get("decision")
            decided_by = "adjudication"
        elif not disagree and ds:
            decision = ds[0]
            decided_by = "reviewer_agreement"
        else:
            decision = "maybe"
            decided_by = "pending_adjudication"
        if disagree:
            disagreements.append({"record_id": r["id"],
                                  "reviewer_decisions": {rv.get("reviewer"): rv.get("decision") for rv in revs},
                                  "adjudicated": bool(adj),
                                  "final": decision})
        final.append({**r, "final_decision": decision, "decided_by": decided_by,
                      "cluster_id": loc.get(r["id"])})
    # PRISMA-style flow over dedup clusters (count closure)
    n_identified = len(records)
    n_dup = dedup["n_duplicates_removed"]
    n_unique = dedup["n_clusters"]
    cluster_decision = {}
    for r in final:
        cid = r["cluster_id"]
        prev = cluster_decision.get(cid)
        order = {"include": 0, "maybe": 1, "exclude": 2}
        if prev is None or order.get(r["final_decision"], 1) < order.get(prev, 1):
            cluster_decision[cid] = r["final_decision"]
    n_incl = sum(1 for d in cluster_decision.values() if d == "include")
    n_excl = sum(1 for d in cluster_decision.values() if d == "exclude")
    n_maybe = sum(1 for d in cluster_decision.values() if d == "maybe")
    closure_ok = (n_identified - n_dup == n_unique) and (n_incl + n_excl + n_maybe == n_unique)
    reason_counts = {}
    for r in final:
        if r["final_decision"] == "exclude":
            rc = (r.get("adjudication") or {}).get("reason_code") or \
                 next((rv.get("reason_code") for rv in r.get("reviewers", [])
                       if rv.get("decision") == "exclude"), "?")
            reason_counts[rc] = reason_counts.get(rc, 0) + 1
    flow = {"identification": n_identified, "duplicates_removed": n_dup,
            "unique_screened": n_unique, "included": n_incl,
            "excluded": n_excl, "pending_human": n_maybe,
            "count_closure_ok": closure_ok,
            "exclusion_reason_counts": reason_counts}
    payload = {"protocol": ir.get("protocol", {}), "criteria": ir.get("criteria", []),
               "prisma_flow": flow, "records": final,
               "disagreements": disagreements,
               "dedup_clusters": dedup["clusters"],
               "human_confirm_queue": [r["id"] for r in final if r["final_decision"] == "maybe"]}
    sections = [
        ("Protocol",
         "```json\n" + __import__("json").dumps(ir.get("protocol", {}), ensure_ascii=False, indent=1) + "\n```"),
        ("PRISMA-style flow (counts must close)",
         _md_table(["stage", "n"],
                   [["identified", n_identified], ["duplicates removed", n_dup],
                    ["unique screened", n_unique], ["included", n_incl],
                    ["excluded", n_excl], ["pending human", n_maybe],
                    ["closure ok", closure_ok]])),
        ("Exclusion reasons (code-level, auditable)",
         _md_table(["reason_code", "n"], [[k2, v] for k2, v in sorted(reason_counts.items())])
         if reason_counts else "none"),
        ("Per-record decisions (dual reviewer + adjudication)",
         _md_table(["id", "title", "reviewers", "final", "decided_by", "reason"],
                   [[r["id"], (r.get("title") or "")[:50],
                     "; ".join(f"{rv.get('reviewer')}:{rv.get('decision')}({rv.get('reason_code')})"
                               for rv in r.get("reviewers", [])),
                     r["final_decision"], r["decided_by"],
                     (r.get("adjudication") or {}).get("reason_code",
                      next((rv.get("reason_code") for rv in r.get("reviewers", [])), "-"))]
                    for r in final])),
        ("Disagreements & adjudication",
         _md_table(["record", "decisions", "adjudicated", "final"],
                   [[d["record_id"], d["reviewer_decisions"], d["adjudicated"], d["final"]]
                    for d in disagreements]) if disagreements else "no disagreements"),
    ]
    summary = {"prisma_flow": flow, "n_disagreements": len(disagreements),
               "human_confirm": len(payload["human_confirm_queue"])}
    return payload, sections, summary


def _b_appraisal(ir, out_dir):
    tool = ir.get("appraisal_tool") or {}
    dims = _by_id(tool.get("dimensions", []))
    papers = []
    for r in _records(ir):
        judgments = []
        grades = []
        abstains = []
        for d in r.get("dimensions", []):
            did = d.get("dimension_id")
            j = d.get("judgment")
            g = d.get("grade")
            item = {"dimension_id": did,
                    "dimension_name": dims.get(did, {}).get("name", did),
                    "judgment": j, "grade": g if j != "insufficient_evidence" else "unclear",
                    "rationale": d.get("rationale"),
                    "evidence": d.get("evidence", []),
                    "evidence_locators": [_loc_str(e) for e in d.get("evidence", [])],
                    "abstain": j == "insufficient_evidence"}
            judgments.append(item)
            if j == "insufficient_evidence":
                abstains.append(did)
            elif g in GRADE_ORDER:
                grades.append(g)
        # aggregation: worst non-abstain domain; abstain on critical -> unclear
        rule = tool.get("aggregation", "worst_domain")
        critical = set(tool.get("critical_dimensions", []))
        if grades:
            overall = max(grades, key=lambda g: GRADE_ORDER.index(g))
        else:
            overall = "unclear"
        if critical & set(abstains):
            overall = "unclear"
            overall_reason = "critical dimension(s) abstained (insufficient evidence); no fabricated grade"
        elif abstains:
            overall_reason = f"worst_domain over {len(grades)} judged dimensions; {len(abstains)} abstained"
        else:
            overall_reason = "worst_domain over all judged dimensions"
        papers.append({"id": r.get("id"), "title": r.get("title"),
                       "study_type": r.get("study_type"), "source_id": r.get("source_id"),
                       "dimensions": judgments, "overall_grade": overall,
                       "overall_reason": overall_reason,
                       "n_abstain": len(abstains), "abstained_dimensions": abstains,
                       "aggregation_rule": rule})
    payload = {"appraisal_tool": tool, "papers": papers,
               "grade_scale": GRADE_ORDER,
               "abstain_policy": "insufficient_evidence -> grade 'unclear', never a fabricated judgment",
               "scope_note": "appraisal of the provided documents only; not peer review or clinical advice"}
    sections = [
        ("Appraisal scale",
         f"tool: {tool.get('name', '-')}; aggregation: {tool.get('aggregation', 'worst_domain')}; "
         f"grades: {GRADE_ORDER}\n\n" +
         _md_table(["dimension", "name", "applies_to"],
                   [[d.get("id"), d.get("name"), ",".join(d.get("applies_to", [])) or "all"]
                    for d in tool.get("dimensions", [])])),
        ("Per-paper appraisal (dimension -> judgment -> evidence -> grade)",
         "\n\n".join(
             f"### {p['id']} — {(p['title'] or '')[:70]}\n"
             f"study_type={p['study_type']}; **overall={p['overall_grade']}** ({p['overall_reason']})\n\n" +
             _md_table(["dimension", "judgment", "grade", "evidence locator", "rationale"],
                       [[d["dimension_id"], d["judgment"], d["grade"],
                        "; ".join(d["evidence_locators"]) or "(abstain: no evidence)",
                        (d["rationale"] or "")[:70]] for d in p["dimensions"]])
             for p in papers)),
        ("Abstentions (evidence insufficient — explicit, not filled in)",
         _md_table(["paper", "abstained dimensions"],
                   [[p["id"], ", ".join(p["abstained_dimensions"])]
                    for p in papers if p["n_abstain"]]) or "none"),
    ]
    summary = {"n_papers": len(papers),
               "overall_grades": {p["id"]: p["overall_grade"] for p in papers},
               "total_abstains": sum(p["n_abstain"] for p in papers)}
    return payload, sections, summary


def _b_cross_language(ir, out_dir):
    works = _by_id(ir.get("works", []))
    views = ir.get("views", [])
    groups = {wid: [] for wid in works}
    for v in views:
        groups.setdefault(v.get("work_id"), []).append(v)
    work_rows = []
    exact_dups = []
    for wid, w in works.items():
        vs = groups.get(wid, [])
        # exact duplicate detection within a work: same language+version+title/doi
        seen = {}
        flags = []
        for v in vs:
            k = (v.get("language"), v.get("version"),
                 kit.normalize_doi(v.get("doi")) or kit.normalize_title(v.get("title")))
            if k in seen:
                flags.append({"view_id": v.get("id"), "duplicate_of": seen[k],
                              "basis": "same work + language + version + normalized title/DOI"})
                exact_dups.append({"work_id": wid, "views": [seen[k], v.get("id")]})
            else:
                seen[k] = v.get("id")
        langs = sorted({v.get("language") for v in vs if v.get("language")})
        versions = sorted({v.get("version") for v in vs if v.get("version")})
        work_rows.append({"work_id": wid, "canonical_title": w.get("canonical_title"),
                          "doi": kit.normalize_doi(w.get("doi")),
                          "n_views": len(vs), "languages": langs, "versions": versions,
                          "views": [{ "id": v.get("id"), "language": v.get("language"),
                                      "body_language": v.get("body_language"),
                                      "version": v.get("version"), "title": v.get("title"),
                                      "doi": kit.normalize_doi(v.get("doi")),
                                      "source_id": v.get("source_id"),
                                      "snippet": v.get("snippet")} for v in vs],
                          "exact_duplicate_flags": flags})
    n_non_en = sum(1 for v in views if (v.get("language") or "").lower() not in ("en", "english"))
    payload = {"works": work_rows, "term_alignments": ir.get("term_alignments", []),
               "n_works": len(works), "n_views": len(views),
               "n_non_english_views": n_non_en,
               "exact_duplicates": exact_dups,
               "identity_rule": "views grouped by work_id; source/DOI/version/body_language preserved per view; "
                                "exact duplicates flagged, never silently dropped",
               "scope_note": "provided works/views only; no live cross-language coverage or unseen-language claim"}
    sections = [
        ("Work / view identity matrix",
         _md_table(["work", "title", "views", "languages", "versions", "duplicates"],
                   [[w["work_id"], (w["canonical_title"] or "")[:50], w["n_views"],
                     ",".join(w["languages"]), ",".join(w["versions"]),
                     len(w["exact_duplicate_flags"])] for w in work_rows])),
        ("Views (source + version + body language preserved)",
         _md_table(["view", "work", "language", "body", "version", "source", "doi"],
                   [[v.get("id"), v.get("work_id"), v.get("language"),
                     v.get("body_language"), v.get("version"), v.get("source_id"),
                     kit.normalize_doi(v.get("doi"))] for v in views])),
        ("Term alignment (checkable, source-located)",
         _md_table(["term", "language", "render", "type", "source"],
                   [[t.get("term"), t.get("language"), t.get("render"),
                     t.get("type", "-"), t.get("source_id")]
                    for t in ir.get("term_alignments", [])]) or "none recorded"),
        ("Exact duplicates (labelled, kept)",
         _md_table(["work", "views"], [[d["work_id"], ",".join(d["views"])] for d in exact_dups])
         if exact_dups else "none"),
    ]
    summary = {"n_works": len(works), "n_views": len(views),
               "n_non_english_views": n_non_en, "n_exact_duplicates": len(exact_dups)}
    return payload, sections, summary


def _norm_patent_number(s):
    if not s:
        return None
    return re.sub(r"[\s\-/]", "", str(s)).upper()


def _b_patent(ir, out_dir):
    pats = ir.get("patents", [])
    pmap = {p.get("id"): p for p in pats}
    # union-find families over OBSERVED links only
    parent = {p["id"]: p["id"] for p in pats}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    link_evidence = []
    for p in pats:
        for fl in p.get("family_links", []):
            if fl.get("to") in parent:
                union(p["id"], fl["to"])
                link_evidence.append({"from": p["id"], "to": fl["to"],
                                      "basis": fl.get("basis"), "source_id": fl.get("source_id")})
    fams = {}
    for p in pats:
        fams.setdefault(find(p["id"]), []).append(p["id"])
    families = [{"family_id": f"F{i+1:02d}", "members": sorted(ms),
                 "basis_links": [l for l in link_evidence if l["from"] in ms or l["to"] in ms],
                 "scope": "observed links only; NOT an exhaustive official family"}
                for i, (_, ms) in enumerate(sorted(fams.items()))]
    out_pats = []
    for p in pats:
        nums = p.get("numbers") or {}
        norm_nums = {k: (_norm_patent_number(v) if not isinstance(v, list)
                         else [_norm_patent_number(x) for x in v])
                     for k, v in nums.items()}
        ls = p.get("legal_status") or {}
        if ls.get("value") and ls.get("source_id"):
            status = {"value": ls["value"], "status": "reported",
                      "source_id": ls["source_id"], "as_of": ls.get("as_of"),
                      "note": "source-located; official register lag possible"}
        else:
            status = {"value": "UNKNOWN", "status": "not_reported",
                      "note": "current official legal status not verifiable from provided sources; human_confirm"}
        claims = sorted(p.get("claims", []), key=lambda c: str(c.get("version")))
        out_pats.append({"id": p["id"], "title": p.get("title"),
                         "numbers_raw": nums, "numbers_normalized": norm_nums,
                         "number_kind_note": "publication != application != grant; priority kept separate",
                         "assignee": p.get("assignee"),
                         "filing_date": p.get("filing_date"),
                         "publication_date": p.get("publication_date"),
                         "source_id": p.get("source_id"),
                         "authorization": p.get("authorization", "green"),
                         "family_id": next(f["family_id"] for f in families if p["id"] in f["members"]),
                         "claims": [{"version": c.get("version"),
                                     "locator": c.get("locator"),
                                     "snippet": c.get("text_snippet"),
                                     "scope_note": "claim scope per this version only; versions not assumed equal"}
                                    for c in claims],
                         "legal_status": status,
                         "ocr_boundary": p.get("ocr_boundary"),
                         "risk_flags": p.get("risk_flags", [])})
    tech = [norm_record(r) for r in _records(ir)]
    payload = {"patents": out_pats, "families": families,
               "tech_literature": tech,
               "queries": ir.get("queries", []),
               "legal_status_policy": "UNKNOWN unless source-located with as_of; no转载 page treated as register",
               "scope_note": "finite provided corpus (facsimiles + records); observed links are not exhaustive families"}
    sections = [
        ("Patent records (numbers normalized; kinds kept distinct)",
         _md_table(["id", "publication", "application", "grant", "assignee", "authorization", "legal status"],
                   [[p["id"], p["numbers_normalized"].get("publication"),
                     p["numbers_normalized"].get("application"),
                     p["numbers_normalized"].get("grant"), p.get("assignee"),
                     p["authorization"], p["legal_status"]["value"]] for p in out_pats])),
        ("Families (observed links only)",
         _md_table(["family", "members", "basis"],
                   [[f["family_id"], ",".join(f["members"]),
                     "; ".join(f"{l['from']}->{l['to']}({l['basis']}@{l['source_id']})"
                               for l in f["basis_links"])] for f in families])),
        ("Claim versions (source-located; scope not assumed equal across versions)",
         _md_table(["patent", "version", "locator"],
                   [[p["id"], c["version"], _loc_str(c["locator"])]
                    for p in out_pats for c in p["claims"]])),
        ("Legal status & OCR boundaries (honest UNKNOWN)",
         _md_table(["patent", "status", "note", "ocr_boundary"],
                   [[p["id"], p["legal_status"]["value"], p["legal_status"]["note"][:60],
                     p.get("ocr_boundary") or "-"] for p in out_pats])),
    ]
    summary = {"n_patents": len(out_pats), "n_families": len(families),
               "n_legal_unknown": sum(1 for p in out_pats if p["legal_status"]["value"] == "UNKNOWN"),
               "n_tech_literature": len(tech)}
    return payload, sections, summary


_BUILDERS = {
    "query_planning": _b_query_planning,
    "question_driven": _b_question_driven,
    "screen_rank": _b_screen_rank,
    "citation_tracking": _b_citation_tracking,
    "multi_db_merge": _b_multi_db,
    "incremental_tracking": _b_incremental,
    "coverage_analysis": _b_coverage,
    "systematic_screening": _b_systematic,
    "quality_appraisal": _b_appraisal,
    "cross_language": _b_cross_language,
    "patent_search": _b_patent,
}

MAIN_NAME = {
    "query_planning": "candidate_set.json",
    "question_driven": "candidate_set.json",
    "screen_rank": "candidate_set.json",
    "citation_tracking": "citation_expansion.json",
    "multi_db_merge": "merged_records.json",
    "incremental_tracking": "incremental_state.json",
    "coverage_analysis": "coverage_analysis.json",
    "systematic_screening": "screening_audit.json",
    "quality_appraisal": "appraisal.json",
    "cross_language": "works_views.json",
    "patent_search": "patent_families.json",
}


def _provenance_map(ir, payload):
    """record/view/patent -> source locator map (bidirectional provenance)."""
    pmap = {}
    for r in _records(ir):
        pmap[r.get("id")] = {"source_id": r.get("source_id"),
                             "query_id": r.get("query_id"),
                             "snippet": r.get("snippet"),
                             "field_sources": r.get("field_sources", {}),
                             "status": r.get("status", "reported")}
    for v in ir.get("views", []):
        pmap[f"view:{v.get('id')}"] = {"source_id": v.get("source_id"),
                                       "work_id": v.get("work_id"),
                                       "language": v.get("language"),
                                       "version": v.get("version")}
    for p in ir.get("patents", []):
        pmap[f"patent:{p.get('id')}"] = {"source_id": p.get("source_id"),
                                         "authorization": p.get("authorization", "green"),
                                         "claims_locators": [c.get("locator") for c in p.get("claims", [])]}
    for x in ir.get("reference_set", []):
        pmap[f"ref:{x.get('id')}"] = {"source_id": x.get("source_id"),
                                      "inclusion_reason": x.get("inclusion_reason")}
    used = {v.get("source_id") for v in pmap.values() if v.get("source_id")}
    for ed in ir.get("edges", []):
        if ed.get("source_id"):
            used.add(ed["source_id"])
    for q in ir.get("queries", []):
        if q.get("source_id"):
            used.add(q["source_id"])
    unused = [s.get("id") for s in ir.get("sources", []) if s.get("id") not in used]
    return {"record_map": pmap, "sources_used": sorted(used),
            "sources_unused": unused,
            "pipeline": "material -> IR -> validate -> compute -> artifact -> result"}


def build(ir: dict, case: dict, out_dir) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = ir.get("kind")
    if kind not in _BUILDERS:
        raise ValueError(f"unsupported kind '{kind}'")
    payload, sections, summary = _BUILDERS[kind](ir, out_dir)
    payload["case_id"] = ir.get("case_id")
    payload["kind"] = kind
    payload["generated_at"] = kit.utc_now()
    payload["example_label"] = ir.get("example_label")  # None for real runs

    main_name = MAIN_NAME[kind]
    kit.write_json(out_dir / main_name, payload)

    # editable markdown report
    lines = [f"# Search report — {kind}",
             f"case_id: `{ir.get('case_id')}`  generated: {kit.utc_now()}",
             "",
             "> Source-bound: computed from organizer-provided LOCAL materials only. "
             "No live remote search, no fabricated records/citations/status. "
             "Every record carries a source locator; gaps are flagged human_confirm.",
             ""]
    if ir.get("example_label"):
        lines += [f"**{ir['example_label']}**", ""]
    for heading, body in sections:
        lines += [f"## {heading}", "", body, ""]
    lines += ["## Sources", "",
              _md_table(["id", "type", "name/path"],
                        [[s.get("id"), s.get("type", "-"),
                          s.get("name") or s.get("path", "-")] for s in ir.get("sources", [])]),
              "", "## Uncertainty / limits", ""]
    unc = ir.get("uncertainty", [])
    lines += ([_md_table(["item", "reason", "handling"],
                         [[u.get("item"), u.get("reason"), u.get("handling", "human_confirm")]
                          for u in unc])] if unc else ["none recorded"])
    lines += ["", "## Summary (computed)", "",
              "```json", __import__("json").dumps(summary, ensure_ascii=False, indent=1), "```", ""]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    # flat records csv (editable)
    recs = payload.get("ranked_records") or payload.get("screened_records") \
        or payload.get("records") or payload.get("retrieved_records") \
        or payload.get("tech_literature") or []
    csv_path = out_dir / "records.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        wtr = csv.writer(fh)
        wtr.writerow(["id", "title", "year", "doi", "source_id", "decision_or_label",
                      "score", "rank", "status"])
        for r in recs:
            wtr.writerow([r.get("id"), r.get("title"), r.get("year_norm") or r.get("year"),
                          r.get("doi_norm") or r.get("doi"), r.get("source_id"),
                          r.get("final_decision") or r.get("decision") or r.get("label"),
                          r.get("score"), r.get("rank"), r.get("status", "reported")])

    prov = _provenance_map(ir, payload)
    prov["summary"] = summary
    kit.write_json(out_dir / "provenance.json", prov)
    kit.write_json(out_dir / "search_ir.json", ir)

    outputs = [
        {"name": main_name, "path": str(out_dir / main_name), "format": "json", "role": "json"},
        {"name": "report.md", "path": str(out_dir / "report.md"), "format": "md", "role": "md"},
        {"name": "records.csv", "path": str(csv_path), "format": "csv", "role": "csv"},
        {"name": "provenance.json", "path": str(out_dir / "provenance.json"),
         "format": "json", "role": "provenance"},
        {"name": "search_ir.json", "path": str(out_dir / "search_ir.json"),
         "format": "json", "role": "ir"},
    ]
    ir["_summary"] = summary
    ir["_prov_unused_sources"] = prov["sources_unused"]
    return outputs