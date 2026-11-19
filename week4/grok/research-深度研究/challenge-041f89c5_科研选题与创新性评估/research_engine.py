"""research_engine — deterministic source-bound research core (stdlib only).

Week4 RESEARCH track (深度研究). One engine, five kinds:
  deep_research      深度研究 Agent: question decomposition -> search plan ->
                     multi-step tool log -> evidence synthesis -> bounded proposal
  lit_review         文献综述生成: screening -> themes -> claim-evidence bound draft
  systematic_review  系统性文献综述: PRISMA-style protocol, two-round screening log,
                     quality appraisal, reproducible synthesis
  trend_analysis     研究前沿与趋势分析: year/theme statistics OVER PROVIDED SOURCES ONLY
  topic_novelty      科研选题与创新性评估: question definition, comparison matrix,
                     scoped novelty verdicts, premise-checked feasibility

Division of labour: the Agent reads the ACTUAL /input materials and fills the IR
(sources, records, protocol, claims with exact quotes, themes, conflicts, gaps,
kind-specific blocks). This engine VALIDATES (locators, quote-in-file checks,
screening arithmetic, verdict consistency, bounded-language scan) and COMPUTES
(PRISMA counts, dedup cross-check, synthesis matrix + support tallies, year/theme
trend statistics, novelty coverage derivation) then BUILDS editable Markdown +
valid OOXML docx + CSV matrices + SVG figures + provenance.json (claim_map).

Hard boundaries enforced in code:
* every substantive claim binds evidence {source_id, paragraph_id, quote};
  quotes are re-checked against the actual source file when it is text;
* screening decisions carry rationale + criterion ids; counts must add up;
* trend/novelty statements are scoped to the provided source set; global
  novelty / completeness / completed-experiment wording is rejected;
* gaps and assumptions are flagged human_confirm, never fabricated.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

import w4kit

IR_VERSION = "1.0"
KINDS = {"deep_research", "lit_review", "systematic_review",
         "trend_analysis", "topic_novelty"}
STRENGTHS = {"established", "supported", "suggestive", "contested", "uncertain"}
STANCES = {"supports", "contradicts", "partial", "context"}
DECISIONS = {"include", "exclude", "pending"}
STAGES = {"title_abstract", "full_text"}
CLAIM_TYPES = {"fact", "inference", "gap", "method", "comparison"}
GAP_TYPES = {"evidence_gap", "conflict_unresolved", "method_failure",
             "repeated_open_question", "coverage_gap"}
NOVELTY_TYPES = {"method", "data", "application", "conclusion"}
VERDICTS = {"novel_within_sources", "partially_overlapping", "covered", "uncertain"}
COVERAGE = {"full", "partial", "none"}
QUALITY_GRADES = {"high", "moderate", "low", "unclear"}
TEXT_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".xml", ".html", ".tex", ".bib"}

# wording that oversteps the provided-source boundary (agent-authored text only)
GLOBAL_PAT = re.compile(
    r"(全球|国际|世界)(首创|首次|领先|空白)|国内(首创|空白)|无人研究|尚无人(研究|报道)"
    r"|填补.{0,6}空白|world[- ]?first|first[- ]?ever|globally (novel|new)"
    r"|state[- ]of[- ]the[- ]art (overall|globally)"
    r"|已完成(了)?(全部|系统)?实验|实验(已|均)完成|experiments? (were |have been )?(completed|finished)",
    re.IGNORECASE)

STRENGTH_LABEL = {"established": "已被多项证据确立", "supported": "有证据支持",
                  "suggestive": "提示性证据", "contested": "存在争议",
                  "uncertain": "不确定"}
STANCE_LABEL = {"supports": "支持", "contradicts": "反对/矛盾",
                "partial": "部分支持", "context": "背景"}


# ── helpers ─────────────────────────────────────────────────────────────────

def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _base_dirs(ir) -> list:
    dirs = ir.get("_base_dirs") or []
    return [Path(d) for d in dirs] + [Path.cwd()]


def resolve_file(src: dict, ir: dict):
    """Resolve a source's material file against IR dir / input dir."""
    f = src.get("file") or src.get("path")
    if not f:
        return None
    p = Path(f)
    if p.is_absolute() and p.exists():
        return p
    for base in _base_dirs(ir):
        for cand in (base / f, base / "materials" / Path(f).name,
                     base / "input" / f):
            if cand.exists():
                return cand
    return None


def _file_text(path: Path):
    if path.suffix.lower() not in TEXT_EXT:
        return None
    try:
        return w4kit.read_text(path)
    except OSError:
        return None


def _paragraph_slice(text: str, pid: str):
    """Materials may mark paragraphs as [P3] ... ; restrict quote search to it."""
    if not pid:
        return None
    m = re.search(r"\[" + re.escape(str(pid)) + r"\]", text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(r"\[P\d+\]", rest)
    return rest[:nxt.start()] if nxt else rest


def iter_evidence(ir: dict):
    """Yield (owner_label, evidence_dict) for every evidence locator in the IR."""
    for c in ir.get("claims", []):
        for ev in c.get("evidence", []):
            yield f"claim {c.get('id', '?')}", ev
    for g in ir.get("gaps", []):
        for ev in g.get("evidence", []):
            yield f"gap {g.get('id', '?')}", ev
    for cf in ir.get("conflicts", []):
        for pos in cf.get("positions", []):
            ev = pos.get("evidence") or pos
            if isinstance(ev, dict) and ev.get("source_id"):
                yield f"conflict {cf.get('id', '?')}", ev
    for q in ir.get("quality", []):
        for d in q.get("dimensions", []):
            ev = d.get("evidence")
            if isinstance(ev, dict) and ev.get("source_id"):
                yield f"quality {q.get('record_id', '?')}", ev
    topic = ir.get("topic", {})
    for row in topic.get("comparison", []):
        for pw in row.get("prior_work", []):
            ev = pw.get("evidence")
            if isinstance(ev, dict) and ev.get("source_id"):
                yield f"comparison {row.get('dimension', '?')}", ev
    for n in topic.get("novelty", []):
        for cb in n.get("covered_by", []):
            yield f"novelty {n.get('id', '?')}", cb
    for f in topic.get("feasibility", []):
        for ev in f.get("evidence", []):
            yield f"feasibility {f.get('id', '?')}", ev


def check_quotes(ir: dict) -> list:
    """Re-verify each quoted excerpt against the ACTUAL source file (text files).

    status: verified | not_found | unverifiable (binary/missing file) | no_quote
    """
    sources = {s.get("id"): s for s in ir.get("sources", [])}
    cache, results = {}, []
    for owner, ev in iter_evidence(ir):
        sid = ev.get("source_id")
        quote = ev.get("quote")
        rec = {"owner": owner, "source_id": sid,
               "paragraph_id": ev.get("paragraph_id"), "status": "no_quote"}
        if not quote:
            results.append(rec)
            continue
        src = sources.get(sid)
        path = resolve_file(src, ir) if src else None
        if path is None:
            rec["status"] = "unverifiable"
            rec["detail"] = "source file not resolvable"
        else:
            if path not in cache:
                cache[path] = _file_text(path)
            text = cache[path]
            if text is None:
                rec["status"] = "unverifiable"
                rec["detail"] = f"binary/unsupported file type {path.suffix}"
            else:
                scope = _paragraph_slice(text, ev.get("paragraph_id"))
                haystack = _norm(scope if scope is not None else text)
                if _norm(quote) in haystack:
                    rec["status"] = "verified"
                    if scope is None and ev.get("paragraph_id"):
                        rec["detail"] = "paragraph marker not found; whole-file match"
                else:
                    rec["status"] = "not_found"
                    rec["detail"] = "quote not present in source file"
        results.append(rec)
    return results


def _agent_texts(ir: dict):
    """Agent-authored prose fields (quotes excluded) for boundary scan."""
    yield "research_question.main", ir.get("research_question", {}).get("main", "")
    for sq in ir.get("research_question", {}).get("subquestions", []):
        yield f"subquestion {sq.get('id')}", sq.get("question", "")
    for c in ir.get("claims", []):
        yield f"claim {c.get('id')}", c.get("text", "")
    for t in ir.get("themes", []):
        yield f"theme {t.get('id')}", t.get("name", "") + " " + t.get("basis", "")
    for g in ir.get("gaps", []):
        yield f"gap {g.get('id')}", g.get("text", "")
    for n in ir.get("topic", {}).get("novelty", []):
        yield f"novelty {n.get('id')}", n.get("statement", "")
    yield "proposal", ir.get("proposal", {}).get("text", "")
    for ph in ir.get("trend", {}).get("phases", []):
        yield f"phase {ph.get('id')}", ph.get("label", "") + " " + ph.get("basis", "")


# ── screening / PRISMA ──────────────────────────────────────────────────────

def compute_screening(ir: dict) -> dict:
    records = ir.get("records", [])
    by_id = {r.get("id"): r for r in records}
    dups = [r for r in records if r.get("duplicate_of")]
    live = [r for r in records if not r.get("duplicate_of")]
    ta_ex = [r for r in live if r.get("stage") == "title_abstract"
             and r.get("decision") == "exclude"]
    ft = [r for r in live if r.get("stage") == "full_text"]
    ft_ex = [r for r in ft if r.get("decision") == "exclude"]
    included = [r for r in live if r.get("decision") == "include"]
    pending = [r for r in live if r.get("decision") == "pending"]
    reasons = Counter()
    for r in ta_ex + ft_ex:
        for cid in r.get("criteria_applied", []) or ["(uncoded)"]:
            reasons[cid] += 1
    counts = {
        "identified": len(records),
        "duplicates_removed": len(dups),
        "title_abstract_screened": len(live),
        "title_abstract_excluded": len(ta_ex),
        "full_text_assessed": len(ft),
        "full_text_excluded": len(ft_ex),
        "included": len(included),
        "pending": len(pending),
    }
    arithmetic_ok = (counts["full_text_assessed"]
                     == counts["title_abstract_screened"]
                     - counts["title_abstract_excluded"] - counts["pending"]
                     and counts["included"]
                     == counts["full_text_assessed"] - counts["full_text_excluded"])
    # independent dedup cross-check (DOI exact + fuzzy title/year)
    dedup = w4kit.dedup_records(records) if records else {
        "n_input": 0, "n_clusters": 0, "n_duplicates_removed": 0, "clusters": []}
    declared_pairs = {frozenset((r.get("id"), r.get("duplicate_of"))) for r in dups}
    undeclared = []
    for c in dedup.get("clusters", []):
        if c["n_members"] > 1:
            ids = c["members"]
            pairs = {frozenset((a, b)) for a in ids for b in ids if a != b}
            if not (pairs & declared_pairs):
                undeclared.append(ids)
    return {"counts": counts, "arithmetic_ok": arithmetic_ok,
            "exclusion_reasons": dict(reasons),
            "included_record_ids": [r.get("id") for r in included],
            "included_source_ids": sorted({r.get("source_id") for r in included
                                           if r.get("source_id")}),
            "pending_record_ids": [r.get("id") for r in pending],
            "dedup_crosscheck": {"n_clusters": dedup["n_clusters"],
                                 "undeclared_duplicate_clusters": undeclared},
            "log": [{"record_id": r.get("id"), "source_id": r.get("source_id"),
                     "title": r.get("title"), "stage": r.get("stage"),
                     "decision": r.get("decision"),
                     "duplicate_of": r.get("duplicate_of"),
                     "criteria_applied": r.get("criteria_applied", []),
                     "reason": r.get("reason"), "reviewer": r.get("reviewer")}
                    for r in records]}


# ── evidence synthesis ──────────────────────────────────────────────────────

def compute_synthesis(ir: dict) -> dict:
    claims = ir.get("claims", [])
    sources = {s.get("id"): s for s in ir.get("sources", [])}
    rows, per_claim = [], {}
    for c in claims:
        sup = con = par = 0
        sids = set()
        for ev in c.get("evidence", []):
            stance = ev.get("stance", "supports")
            sids.add(ev.get("source_id"))
            if stance == "supports":
                sup += 1
            elif stance == "contradicts":
                con += 1
            elif stance == "partial":
                par += 1
            rows.append({"claim_id": c.get("id"), "claim_text": c.get("text"),
                         "theme_id": c.get("theme_id"),
                         "strength": c.get("strength"),
                         "source_id": ev.get("source_id"),
                         "source_title": sources.get(ev.get("source_id"), {}).get("title"),
                         "paragraph_id": ev.get("paragraph_id"),
                         "quote": ev.get("quote"), "stance": stance})
        per_claim[c.get("id")] = {"n_supports": sup, "n_contradicts": con,
                                  "n_partial": par, "n_sources": len(sids),
                                  "strength": c.get("strength")}
    used = {r["source_id"] for r in rows}
    all_ids = set(sources)
    themes = {t.get("id"): t for t in ir.get("themes", [])}
    theme_counts = Counter(c.get("theme_id") for c in claims)
    return {
        "matrix": rows, "per_claim": per_claim,
        "n_claims": len(claims), "n_evidence_rows": len(rows),
        "sources_cited": sorted(used),
        "sources_registered_not_cited": sorted(all_ids - used),
        "claims_per_theme": {tid: theme_counts.get(tid, 0) for tid in themes},
        "contested_claims": [cid for cid, v in per_claim.items()
                             if v["n_contradicts"] > 0],
    }


# ── trend statistics (provided sources only) ────────────────────────────────

def compute_trend(ir: dict) -> dict:
    sources = {s.get("id"): s for s in ir.get("sources", [])}
    screening = compute_screening(ir)
    scope_ids = screening["included_source_ids"] or sorted(sources)
    year_of = {}
    for sid in scope_ids:
        y = w4kit.to_float(sources.get(sid, {}).get("year"))
        year_of[sid] = int(y) if y is not None else None
    known = {s: y for s, y in year_of.items() if y is not None}
    hist = Counter(known.values())
    years = sorted(hist)
    # theme x year from claim evidence (each claim counted once per source-year)
    themes = {t.get("id"): t.get("name", t.get("id")) for t in ir.get("themes", [])}
    theme_year = {tid: Counter() for tid in themes}
    for c in ir.get("claims", []):
        tid = c.get("theme_id")
        if tid not in theme_year:
            continue
        seen = set()
        for ev in c.get("evidence", []):
            sid = ev.get("source_id")
            y = known.get(sid)
            if y is not None and (sid, y) not in seen:
                seen.add((sid, y))
                theme_year[tid][y] += 1
    # early/late split at median year -> direction per theme (descriptive only)
    direction = {}
    if years:
        mid = years[len(years) // 2]
        for tid, cnt in theme_year.items():
            early = sum(v for y, v in cnt.items() if y < mid)
            late = sum(v for y, v in cnt.items() if y >= mid)
            if late > early:
                d = "rising_within_set"
            elif early > late:
                d = "declining_within_set"
            else:
                d = "stable_within_set"
            direction[tid] = {"early_count": early, "late_count": late,
                              "split_year": mid, "direction": d}
    growth = []
    for a, b in zip(years, years[1:]):
        growth.append({"from_year": a, "to_year": b,
                       "count_from": hist[a], "count_to": hist[b],
                       "delta": hist[b] - hist[a]})
    phases = ir.get("trend", {}).get("phases", [])
    phase_check = []
    for ph in phases:
        reps = ph.get("representative_works", [])
        ok, notes = True, []
        for rw in reps:
            sid = rw.get("source_id")
            if sid not in sources:
                ok = False
                notes.append(f"{sid}: not registered")
            elif sid not in scope_ids:
                notes.append(f"{sid}: not in included set")
            elif known.get(sid) is not None and ph.get("years"):
                lo, hi = ph["years"][0], ph["years"][-1]
                if not (lo <= known[sid] <= hi):
                    ok = False
                    notes.append(f"{sid}: year {known[sid]} outside phase window")
        phase_check.append({"phase_id": ph.get("id"), "ok": ok, "notes": notes})
    return {"scope": "provided_sources_only", "n_sources_in_scope": len(scope_ids),
            "year_basis": ir.get("trend", {}).get("year_basis", "publication_year"),
            "year_histogram": {str(y): hist[y] for y in years},
            "missing_year_sources": sorted(s for s, y in year_of.items() if y is None),
            "theme_year_matrix": {tid: {str(y): theme_year[tid][y] for y in years}
                                  for tid in themes},
            "theme_direction": direction, "year_growth": growth,
            "phase_check": phase_check,
            "caveat": "小样本描述性统计：仅反映所提供来源集合，不代表领域全局趋势；"
                      "年度口径见 year_basis，波动不等于拐点。"}


# ── novelty / feasibility (scoped) ──────────────────────────────────────────

def derive_verdict(covered_by: list) -> str:
    covs = [cb.get("coverage") for cb in covered_by]
    if "full" in covs:
        return "covered"
    if "partial" in covs:
        return "partially_overlapping"
    if covs and all(c == "none" for c in covs):
        return "novel_within_sources"
    return "uncertain"


def compute_novelty(ir: dict) -> dict:
    topic = ir.get("topic", {})
    items, mismatches = [], []
    for n in topic.get("novelty", []):
        derived = derive_verdict(n.get("covered_by", []))
        declared = n.get("verdict")
        if declared and declared != derived:
            mismatches.append({"novelty_id": n.get("id"), "declared": declared,
                               "derived": derived})
        items.append({"id": n.get("id"), "statement": n.get("statement"),
                      "type": n.get("type"), "declared_verdict": declared,
                      "derived_verdict": derived,
                      "n_covered_by": len(n.get("covered_by", [])),
                      "uncertainty": n.get("uncertainty")})
    feas = []
    for f in topic.get("feasibility", []):
        status = f.get("status")
        needs_confirm = status in ("assumption", "unknown")
        feas.append({"id": f.get("id"), "premise": f.get("premise"),
                     "status": status, "n_evidence": len(f.get("evidence", [])),
                     "human_confirm": bool(f.get("human_confirm")) or needs_confirm,
                     "risk": f.get("risk")})
    comp = topic.get("comparison", [])
    comparable = sum(1 for r in comp if r.get("comparable"))
    return {"novelty_items": items, "verdict_mismatches": mismatches,
            "feasibility": feas,
            "n_assumptions": sum(1 for f in feas if f["status"] == "assumption"),
            "comparison_dimensions": len(comp), "comparable_dimensions": comparable,
            "scope": "provided_sources_only",
            "caveat": "新颖性判定仅在所提供来源范围内成立；未检索到 ≠ 全球无人研究；"
                      "所有判定为前瞻性评估，未执行实验。"}


# ── validation ──────────────────────────────────────────────────────────────

def validate_ir(ir: dict) -> dict:
    errors, warnings = [], []
    if ir.get("ir_version") != IR_VERSION:
        errors.append(f"ir_version must be {IR_VERSION}")
    if not ir.get("case_id"):
        errors.append("case_id required")
    kind = ir.get("kind")
    if kind not in KINDS:
        errors.append(f"unknown kind {kind!r}; expected one of {sorted(KINDS)}")
    sources = ir.get("sources", [])
    sids = [s.get("id") for s in sources]
    if not sources:
        errors.append("sources registry empty: register the provided materials first")
    if len(set(sids)) != len(sids):
        errors.append("duplicate source ids in registry")
    for s in sources:
        if not s.get("id") or not s.get("title"):
            errors.append("every source needs id + title")
        if not (s.get("file") or s.get("path")):
            warnings.append(f"source {s.get('id')}: no file pointer (quotes unverifiable)")
        elif resolve_file(s, ir) is None:
            warnings.append(f"source {s.get('id')}: file '{s.get('file')}' not found "
                            "against IR/input dirs (quotes unverifiable)")
    errors.extend(w4kit.check_sources(ir))

    # protocol / criteria
    proto = ir.get("protocol", {})
    inc_ids = {c.get("id") for c in proto.get("inclusion", [])}
    exc_ids = {c.get("id") for c in proto.get("exclusion", [])}
    crit_ids = inc_ids | exc_ids
    if not inc_ids or not exc_ids:
        warnings.append("protocol: inclusion/exclusion criteria not both defined")
    for q in proto.get("search_queries", []):
        if not q.get("query") or not q.get("intent"):
            warnings.append(f"search query {q.get('id')}: missing query text or intent")
        if q.get("executed") and not q.get("date"):
            warnings.append(f"search query {q.get('id')}: executed without date")

    # records / screening
    records = ir.get("records", [])
    rids = {r.get("id") for r in records}
    if not records:
        warnings.append("no screening records: PRISMA flow will be empty")
    for r in records:
        rid = r.get("id", "?")
        if r.get("source_id") not in set(sids):
            errors.append(f"record {rid}: source_id not registered")
        if r.get("duplicate_of"):
            if r["duplicate_of"] not in rids:
                errors.append(f"record {rid}: duplicate_of target missing")
            continue
        if r.get("decision") not in DECISIONS:
            errors.append(f"record {rid}: decision must be include/exclude/pending")
        if r.get("stage") not in STAGES:
            errors.append(f"record {rid}: stage must be title_abstract/full_text")
        if r.get("decision") == "exclude" and not r.get("reason"):
            errors.append(f"record {rid}: exclusion without rationale")
        if r.get("decision") == "include" and r.get("stage") != "full_text":
            warnings.append(f"record {rid}: included before full-text stage")
        for cid in r.get("criteria_applied", []):
            if cid not in crit_ids:
                errors.append(f"record {rid}: criterion '{cid}' not defined in protocol")
    screening = compute_screening(ir)
    if records and not screening["arithmetic_ok"]:
        errors.append(f"PRISMA counts do not add up: {screening['counts']}")
    for cluster in screening["dedup_crosscheck"]["undeclared_duplicate_clusters"]:
        warnings.append(f"possible undeclared duplicates: {cluster} (verify DOI/title)")

    # claims
    themes = {t.get("id") for t in ir.get("themes", [])}
    claim_ids = {c.get("id") for c in ir.get("claims", [])}
    sq_ids = {s.get("id") for s in ir.get("research_question", {}).get("subquestions", [])}
    if not ir.get("claims"):
        errors.append("no claims: synthesis would be empty")
    for c in ir.get("claims", []):
        cid = c.get("id", "?")
        if not c.get("text"):
            errors.append(f"claim {cid}: empty text")
        if c.get("strength") not in STRENGTHS:
            errors.append(f"claim {cid}: strength must be one of {sorted(STRENGTHS)}")
        if c.get("type") and c["type"] not in CLAIM_TYPES:
            warnings.append(f"claim {cid}: non-standard type {c['type']}")
        evs = c.get("evidence", [])
        if not evs:
            errors.append(f"claim {cid}: no evidence binding (claim-evidence rule)")
        for ev in evs:
            if ev.get("stance") and ev["stance"] not in STANCES:
                errors.append(f"claim {cid}: invalid stance {ev['stance']}")
            if not ev.get("quote"):
                errors.append(f"claim {cid}: evidence lacks exact quote")
            if not ev.get("paragraph_id"):
                warnings.append(f"claim {cid}: evidence lacks paragraph_id")
        if c.get("theme_id") and c["theme_id"] not in themes:
            errors.append(f"claim {cid}: theme '{c['theme_id']}' not registered")
        if c.get("subquestion_id") and sq_ids and c["subquestion_id"] not in sq_ids:
            errors.append(f"claim {cid}: subquestion '{c['subquestion_id']}' not defined")
        if c.get("strength") == "established" and any(
                e.get("stance") == "contradicts" for e in evs):
            errors.append(f"claim {cid}: 'established' with contradicting evidence "
                          "(use contested/supported)")
        if c.get("strength") in ("suggestive", "uncertain") and not c.get("uncertainty"):
            warnings.append(f"claim {cid}: weak strength without uncertainty note")

    # quote re-verification against actual files
    qchecks = check_quotes(ir)
    for q in qchecks:
        if q["status"] == "not_found":
            errors.append(f"{q['owner']}: quote not found in {q['source_id']} "
                          f"({q.get('detail')}) — fix quote or mark extraction_failed")
        elif q["status"] == "unverifiable":
            warnings.append(f"{q['owner']}: quote unverifiable ({q.get('detail')})")
        elif q["status"] == "no_quote":
            warnings.append(f"{q['owner']}: evidence without quote")

    # themes / conflicts / gaps
    for t in ir.get("themes", []):
        if not t.get("basis"):
            warnings.append(f"theme {t.get('id')}: no induction basis (must grow from sources)")
    for cf in ir.get("conflicts", []):
        pos = cf.get("positions", [])
        if len(pos) < 2:
            errors.append(f"conflict {cf.get('id')}: needs >=2 positions")
        for p in pos:
            ev = p.get("evidence") or p
            if not (ev.get("source_id") and (ev.get("quote") or ev.get("paragraph_id"))):
                errors.append(f"conflict {cf.get('id')}: position lacks source locator")
        if not cf.get("handling"):
            warnings.append(f"conflict {cf.get('id')}: no handling/resolution note")
    for g in ir.get("gaps", []):
        if g.get("type") and g["type"] not in GAP_TYPES:
            warnings.append(f"gap {g.get('id')}: non-standard type {g['type']}")
        if not g.get("evidence") and not g.get("search_scope_checked"):
            errors.append(f"gap {g.get('id')}: needs evidence or documented search scope "
                          "(no 'not found => nobody studied' reasoning)")
        if not g.get("human_confirm"):
            warnings.append(f"gap {g.get('id')}: not flagged human_confirm")

    # kind-specific requirements
    if kind == "deep_research":
        sqs = ir.get("research_question", {}).get("subquestions", [])
        if not sqs:
            errors.append("deep_research: subquestions required")
        for sq in sqs:
            for dep in sq.get("depends_on", []):
                if dep not in sq_ids:
                    errors.append(f"subquestion {sq.get('id')}: dependency '{dep}' undefined")
        # cycle detection
        graph = {s.get("id"): s.get("depends_on", []) for s in sqs}
        state = {}
        def dfs(n):
            state[n] = 1
            for m in graph.get(n, []):
                if state.get(m) == 1:
                    return True
                if state.get(m, 0) == 0 and dfs(m):
                    return True
            state[n] = 2
            return False
        if any(state.get(n, 0) == 0 and dfs(n) for n in graph):
            errors.append("subquestion dependency graph has a cycle")
        if not ir.get("tool_log"):
            warnings.append("deep_research: tool_log empty (replay path not recorded)")
        for step in ir.get("tool_log", []):
            if not (step.get("tool") and step.get("params") is not None):
                warnings.append(f"tool_log step {step.get('step')}: missing tool/params")
    if kind == "lit_review" and not ir.get("themes"):
        errors.append("lit_review: themes required (induced from sources)")
    if kind == "systematic_review":
        if not proto.get("search_queries"):
            errors.append("systematic_review: search_queries required")
        stages = {r.get("stage") for r in records if not r.get("duplicate_of")}
        if records and stages == {"title_abstract"}:
            warnings.append("systematic_review: no full-text round recorded")
        inc_recs = screening["included_record_ids"]
        q_recs = {q.get("record_id") for q in ir.get("quality", [])}
        for rid in inc_recs:
            if rid not in q_recs:
                warnings.append(f"systematic_review: included record {rid} lacks quality appraisal")
        for q in ir.get("quality", []):
            if q.get("overall") not in QUALITY_GRADES:
                errors.append(f"quality {q.get('record_id')}: overall grade invalid")
            for d in q.get("dimensions", []):
                if not d.get("evidence"):
                    warnings.append(f"quality {q.get('record_id')}/{d.get('name')}: no evidence")
    if kind == "trend_analysis":
        tr = ir.get("trend", {})
        if not tr.get("phases"):
            warnings.append("trend_analysis: no phase划分 provided")
        trend = compute_trend(ir)
        if not trend["year_histogram"]:
            errors.append("trend_analysis: no year data in scope")
        for pc in trend["phase_check"]:
            if not pc["ok"]:
                errors.append(f"phase {pc['phase_id']}: {'; '.join(pc['notes'])}")
        if trend["missing_year_sources"]:
            warnings.append(f"trend_analysis: missing year for {trend['missing_year_sources']}")
    if kind == "topic_novelty":
        topic = ir.get("topic", {})
        qd = topic.get("question_definition", {})
        for k in ("object", "variables", "baseline", "falsifiable"):
            if not qd.get(k):
                errors.append(f"topic_novelty: question_definition.{k} required")
        if not topic.get("novelty"):
            errors.append("topic_novelty: novelty items required")
        nov = compute_novelty(ir)
        for mm in nov["verdict_mismatches"]:
            errors.append(f"novelty {mm['novelty_id']}: declared '{mm['declared']}' "
                          f"but coverage derives '{mm['derived']}'")
        for n in topic.get("novelty", []):
            if n.get("type") not in NOVELTY_TYPES:
                errors.append(f"novelty {n.get('id')}: type must be {sorted(NOVELTY_TYPES)}")
            if not n.get("uncertainty"):
                errors.append(f"novelty {n.get('id')}: explicit uncertainty required")
            for cb in n.get("covered_by", []):
                if cb.get("coverage") not in COVERAGE:
                    errors.append(f"novelty {n.get('id')}: coverage must be full/partial/none")
                if not cb.get("quote"):
                    errors.append(f"novelty {n.get('id')}: covered_by lacks quote")
        for f in topic.get("feasibility", []):
            if f.get("status") == "supported" and not f.get("evidence"):
                errors.append(f"feasibility {f.get('id')}: 'supported' without evidence")
            if f.get("status") == "assumption" and not f.get("human_confirm"):
                warnings.append(f"feasibility {f.get('id')}: assumption not flagged human_confirm")
        if not topic.get("comparison"):
            warnings.append("topic_novelty: comparison matrix empty")

    # boundary language scan (agent-authored text only)
    for label, text in _agent_texts(ir):
        m = GLOBAL_PAT.search(str(text))
        if m:
            errors.append(f"{label}: over-boundary wording '{m.group(0)}' — scope to "
                          "provided sources; no global novelty/completeness or "
                          "completed-experiment claims")
    proposal = ir.get("proposal", {})
    if proposal and not proposal.get("bounded", True):
        errors.append("proposal.bounded must be true (prospective, source-scoped)")
    if not ir.get("uncertainty"):
        warnings.append("uncertainty list empty: conflicts/bias/gaps must be declared")
    if not ir.get("provenance", {}).get("pipeline"):
        ir.setdefault("provenance", {})["pipeline"] = (
            "material -> research IR -> validate -> compute -> artifact -> result")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


# ── document model (shared by md + docx renderers) ──────────────────────────

def _cite(ev: dict) -> str:
    pid = ev.get("paragraph_id")
    return f"【{ev.get('source_id')}" + (f"·{pid}" if pid else "") + "】"


def _doc_model(ir: dict, computed: dict) -> list:
    """Ordered block list: {t: h1/h2/h3/p/table/bullets, ...}."""
    B = []
    kind = ir.get("kind")
    n_src = len(ir.get("sources", []))
    n_rec = len(ir.get("records", []))
    B.append({"t": "h1", "text": ir.get("title", "研究报告")})
    B.append({"t": "p", "text":
              f"边界声明：本报告仅基于组织方提供的 {n_src} 个来源 / {n_rec} 条记录，"
              "所有结论均绑定来源定位（source_id·paragraph_id·原文摘录）。"
              "不构成全局新颖性或领域完备性判断；文中研究建议为前瞻性方案，未执行任何实验。"
              "冲突证据并列呈现，无法确定项标注 human_confirm。"})
    rq = ir.get("research_question", {})
    B.append({"t": "h2", "text": "1 研究问题与范围"})
    B.append({"t": "p", "text": rq.get("main", "(未提供)")})
    sqs = rq.get("subquestions", [])
    if sqs:
        B.append({"t": "table", "header": ["子问题", "内容", "依赖", "检索动作"],
                  "rows": [[sq.get("id"), sq.get("question"),
                            ", ".join(sq.get("depends_on", [])) or "—",
                            sq.get("search_action", "—")] for sq in sqs]})
    scope = ir.get("scope", {})
    if scope:
        B.append({"t": "p", "text": "范围与口径：" + "；".join(
            f"{k}: {v}" for k, v in scope.items() if v)})

    proto = ir.get("protocol", {})
    scr = computed["screening"]
    B.append({"t": "h2", "text": "2 检索与筛选协议（PRISMA 式）"})
    if proto.get("search_queries"):
        B.append({"t": "table",
                  "header": ["编号", "数据库/范围", "检索式", "意图", "状态"],
                  "rows": [[q.get("id"), q.get("database", "provided set"),
                            q.get("query"), q.get("intent"),
                            "prospective" if not q.get("executed") else
                            f"executed {q.get('date', '')}"]
                           for q in proto["search_queries"]]})
    if proto.get("inclusion"):
        B.append({"t": "bullets", "items":
                  [f"纳入 {c.get('id')}: {c.get('text')}" for c in proto["inclusion"]]})
    if proto.get("exclusion"):
        B.append({"t": "bullets", "items":
                  [f"排除 {c.get('id')}: {c.get('text')}" for c in proto["exclusion"]]})
    c = scr["counts"]
    B.append({"t": "table", "header": ["PRISMA 阶段", "数量"],
              "rows": [["识别记录", c["identified"]],
                       ["去重移除", c["duplicates_removed"]],
                       ["题录级筛选", c["title_abstract_screened"]],
                       ["题录级排除", c["title_abstract_excluded"]],
                       ["全文级评估", c["full_text_assessed"]],
                       ["全文级排除", c["full_text_excluded"]],
                       ["最终纳入", c["included"]],
                       ["待定", c["pending"]]]})
    B.append({"t": "p", "text": "逐条筛选记录（含排除理由与判定条款）见 screening_log.csv；"
              "流程图见 prisma_flow.svg。计数由引擎从记录重算并通过加和校验。"})
    if ir.get("quality"):
        B.append({"t": "h2", "text": "3 纳入研究质量评价"})
        B.append({"t": "table",
                  "header": ["记录", "维度判断", "总体等级", "对综合的影响"],
                  "rows": [[q.get("record_id"),
                            "；".join(f"{d.get('name')}:{d.get('judgment')}"
                                     for d in q.get("dimensions", [])),
                            q.get("overall"), q.get("effect_on_synthesis", "—")]
                           for q in ir["quality"]]})

    syn = computed["synthesis"]
    B.append({"t": "h2", "text": "证据综合矩阵（论断 × 来源 × 摘录 × 强度）"})
    B.append({"t": "p", "text":
              f"共 {syn['n_claims']} 条论断、{syn['n_evidence_rows']} 条证据行；"
              f"存在相反证据的论断 {len(syn['contested_claims'])} 条。"
              "完整矩阵见 synthesis_matrix.csv，逐条回链见 provenance.json。"})
    B.append({"t": "table",
              "header": ["论断", "来源·段落", "立场", "强度", "原文摘录"],
              "rows": [[r["claim_id"],
                        f"{r['source_id']}·{r['paragraph_id'] or '—'}",
                        STANCE_LABEL.get(r["stance"], r["stance"]),
                        STRENGTH_LABEL.get(r["strength"], r["strength"]),
                        r["quote"]] for r in syn["matrix"]]})

    B.append({"t": "h2", "text": "主题综述（论断-证据绑定）"})
    themes = ir.get("themes", [])
    claims_by_theme = {}
    for cl in ir.get("claims", []):
        claims_by_theme.setdefault(cl.get("theme_id"), []).append(cl)
    for t in themes:
        B.append({"t": "h3", "text": f"{t.get('id')} {t.get('name')}"})
        if t.get("basis"):
            B.append({"t": "p", "text": "归纳依据：" + t["basis"]})
        for cl in claims_by_theme.get(t.get("id"), []):
            cites = " ".join(_cite(ev) for ev in cl.get("evidence", []))
            label = STRENGTH_LABEL.get(cl.get("strength"), cl.get("strength"))
            line = f"[{cl.get('id')}|{label}] {cl.get('text')} {cites}"
            if cl.get("uncertainty"):
                line += f"（不确定性：{cl['uncertainty']}）"
            B.append({"t": "p", "text": line})
        if t.get("boundary"):
            B.append({"t": "p", "text": "主题边界：" + t["boundary"]})
    orphan = claims_by_theme.get(None, [])
    for cl in orphan:
        B.append({"t": "p", "text": f"[{cl.get('id')}] {cl.get('text')}"})

    if ir.get("conflicts"):
        B.append({"t": "h2", "text": "冲突证据（并列呈现）"})
        for cf in ir["conflicts"]:
            B.append({"t": "h3", "text": f"{cf.get('id')} {cf.get('topic', '')}"})
            for p in cf.get("positions", []):
                ev = p.get("evidence") or p
                B.append({"t": "p", "text":
                          f"立场：{p.get('text', '')} {_cite(ev)} "
                          f"摘录：“{ev.get('quote', '')}”"})
            B.append({"t": "p", "text":
                      f"归因：{cf.get('attribution', '未归因')}；"
                      f"处理：{cf.get('handling', '未决')}；"
                      f"状态：{cf.get('resolution', 'unresolved')}"})
    if ir.get("gaps"):
        B.append({"t": "h2", "text": "研究空白（证据缺口，非检索遗漏断言）"})
        for g in ir["gaps"]:
            line = (f"[{g.get('id')}|{g.get('type', 'evidence_gap')}] {g.get('text')} "
                    + " ".join(_cite(ev) for ev in g.get("evidence", [])))
            if g.get("search_scope_checked"):
                line += f"（已核查范围：{g['search_scope_checked']}）"
            line += " —— human_confirm" if g.get("human_confirm") else ""
            B.append({"t": "p", "text": line})

    if kind == "trend_analysis" or ir.get("trend", {}).get("phases"):
        tr = computed["trend"]
        B.append({"t": "h2", "text": "趋势分析（仅限所提供来源集合）"})
        B.append({"t": "p", "text": tr["caveat"] + f" 年度口径：{tr['year_basis']}。"})
        B.append({"t": "table", "header": ["年份", "纳入来源数"],
                  "rows": [[y, n] for y, n in tr["year_histogram"].items()]})
        if tr["theme_year_matrix"]:
            years = list(tr["year_histogram"])
            B.append({"t": "table",
                      "header": ["主题"] + years,
                      "rows": [[tid] + [row.get(y, 0) for y in years]
                               for tid, row in tr["theme_year_matrix"].items()]})
        if tr["theme_direction"]:
            B.append({"t": "table",
                      "header": ["主题", "前期计数", "后期计数", "切分年", "集合内方向"],
                      "rows": [[tid, d["early_count"], d["late_count"],
                                d["split_year"], d["direction"]]
                               for tid, d in tr["theme_direction"].items()]})
        for ph in ir.get("trend", {}).get("phases", []):
            reps = "；".join(f"{rw.get('source_id')}（{rw.get('reason', '')}）"
                            for rw in ph.get("representative_works", []))
            B.append({"t": "p", "text":
                      f"阶段 {ph.get('id')} {ph.get('label')} "
                      f"[{ph.get('years', ['?', '?'])[0]}–{ph.get('years', ['?', '?'])[-1]}]："
                      f"{ph.get('basis', '')} 代表作：{reps}"})
        B.append({"t": "p", "text": "年度分布图见 trend_chart.svg（由上表数据绘制）。"})

    if kind == "topic_novelty":
        nov = computed["novelty"]
        topic = ir.get("topic", {})
        qd = topic.get("question_definition", {})
        B.append({"t": "h2", "text": "选题与创新性评估（范围限定 + 显式不确定性）"})
        B.append({"t": "p", "text": nov["caveat"]})
        B.append({"t": "table", "header": ["要素", "内容"],
                  "rows": [["研究对象", qd.get("object")],
                           ["关键变量", qd.get("variables")],
                           ["比较基线", qd.get("baseline")],
                           ["预期结论", qd.get("expected", "—")],
                           ["可证伪条件", qd.get("falsifiable")]]})
        if topic.get("comparison"):
            B.append({"t": "h3", "text": "已有工作比较矩阵"})
            B.append({"t": "table",
                      "header": ["维度", "已有工作（来源·摘录）", "拟议方案", "可直接比较", "说明"],
                      "rows": [[r.get("dimension"),
                                "；".join(f"{pw.get('source_id')}: {pw.get('value', '')}"
                                         f"“{pw.get('evidence', {}).get('quote', '')}”"
                                         for pw in r.get("prior_work", [])),
                                r.get("proposed"),
                                "是" if r.get("comparable") else "否",
                                r.get("reason", "—")] for r in topic["comparison"]]})
        B.append({"t": "h3", "text": "创新性逐条判定（引擎按覆盖证据复核）"})
        B.append({"t": "table",
                  "header": ["编号", "创新陈述", "类型", "覆盖来源", "判定", "不确定性"],
                  "rows": [[it["id"], it["statement"], it["type"],
                            ", ".join(cb.get("source_id", "") + ":" + cb.get("coverage", "")
                                      for cb in next((n.get("covered_by", []) for n in
                                                      topic.get("novelty", [])
                                                      if n.get("id") == it["id"]), [])),
                            it["derived_verdict"], it["uncertainty"]]
                           for it in nov["novelty_items"]]})
        B.append({"t": "h3", "text": "可行性前提核查"})
        B.append({"t": "table",
                  "header": ["前提", "状态", "证据数", "需人工确认", "风险"],
                  "rows": [[f["premise"], f["status"], f["n_evidence"],
                            "是" if f["human_confirm"] else "否", f.get("risk", "—")]
                           for f in nov["feasibility"]]})

    if ir.get("tool_log"):
        B.append({"t": "h2", "text": "多步工具调用记录（可复跑路径）"})
        B.append({"t": "table",
                  "header": ["步骤", "工具", "参数", "返回摘要", "状态"],
                  "rows": [[s.get("step"), s.get("tool"),
                            str(s.get("params")), s.get("result_summary", ""),
                            s.get("status", "ok")] for s in ir["tool_log"]]})

    if ir.get("proposal"):
        pr = ir["proposal"]
        B.append({"t": "h2", "text": "有界研究建议（前瞻性，未执行实验）"})
        B.append({"t": "p", "text": pr.get("text", "")})
        if pr.get("constraints"):
            B.append({"t": "bullets", "items": ["约束：" + x for x in pr["constraints"]]})
        B.append({"t": "p", "text": "明确不主张：" + "；".join(
            pr.get("not_claimed", ["全局新颖性", "领域完备性", "已完成实验"]))})

    B.append({"t": "h2", "text": "不确定性与人工确认清单"})
    items = [f"{u.get('item', u) if isinstance(u, dict) else u}"
             for u in ir.get("uncertainty", [])]
    items += [f"gap {g.get('id')}: {g.get('text')} (human_confirm)"
              for g in ir.get("gaps", []) if g.get("human_confirm")]
    items += [f"feasibility {f.get('id')}: {f.get('premise')} (assumption, human_confirm)"
              for f in ir.get("topic", {}).get("feasibility", [])
              if f.get("status") == "assumption"]
    B.append({"t": "bullets", "items": items or ["(未声明)"]})

    B.append({"t": "h2", "text": "来源登记（参考文献）"})
    B.append({"t": "table",
              "header": ["编号", "标题", "年份", "文件", "DOI/标识"],
              "rows": [[s.get("id"), s.get("title"), s.get("year", "—"),
                        s.get("file", "—"), s.get("doi", "—")]
                       for s in ir.get("sources", [])]})
    return B


def _render_md(blocks: list) -> str:
    out = []
    for b in blocks:
        t = b["t"]
        if t in ("h1", "h2", "h3"):
            out += ["#" * int(t[1]) + " " + str(b["text"]), ""]
        elif t == "p":
            out += [str(b["text"]), ""]
        elif t == "bullets":
            out += ["- " + str(x) for x in b["items"]] + [""]
        elif t == "table":
            hdr = [str(x) for x in b["header"]]
            out += ["| " + " | ".join(hdr) + " |",
                    "|" + "|".join(["---"] * len(hdr)) + "|"]
            for row in b["rows"]:
                cells = [str(x if x is not None else "—").replace("|", "\\|")
                         .replace("\n", " ") for x in row]
                out += ["| " + " | ".join(cells) + " |"]
            out += [""]
    return "\n".join(out)


# ── stdlib OOXML docx (docxkit pattern, extended with tables) ───────────────

_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="34"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:rPr><w:b/><w:sz w:val="23"/></w:rPr></w:style>
</w:styles>"""


def _p(text, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return (f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(str(text))}'
            "</w:t></w:r></w:p>")


def _tbl(header, rows):
    n = len(header)
    borders = ("<w:tblBorders>" + "".join(
        f'<w:{s} w:val="single" w:sz="4" w:color="999999"/>'
        for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
        + "</w:tblBorders>")
    grid = "<w:tblGrid>" + '<w:gridCol w:w="1800"/>' * n + "</w:tblGrid>"
    def cell(x, bold=False):
        rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
        return ('<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>'
                f'<w:p><w:r>{rpr}<w:t xml:space="preserve">'
                f'{escape(str(x if x is not None else "—"))}</w:t></w:r></w:p></w:tc>')
    trs = ["<w:tr>" + "".join(cell(h, True) for h in header) + "</w:tr>"]
    for row in rows:
        trs.append("<w:tr>" + "".join(cell(x) for x in row) + "</w:tr>")
    return (f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>{borders}</w:tblPr>'
            f'{grid}{"".join(trs)}</w:tbl>')


def _render_docx(path: Path, blocks: list):
    import zipfile
    body = []
    for b in blocks:
        t = b["t"]
        if t == "h1":
            body.append(_p(b["text"], "Title"))
        elif t == "h2":
            body.append(_p(b["text"], "Heading1"))
        elif t == "h3":
            body.append(_p(b["text"], "Heading2"))
        elif t == "p":
            body.append(_p(b["text"]))
        elif t == "bullets":
            body.extend(_p("• " + str(x)) for x in b["items"])
        elif t == "table":
            body.append(_tbl(b["header"], b["rows"]))
            body.append(_p(""))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body>{"".join(body)}<w:sectPr/></w:body></w:document>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/styles.xml", _STYLES)


# ── SVG figures (real computed data) ────────────────────────────────────────

def _svg_year_chart(trend: dict) -> str:
    hist = trend["year_histogram"]
    years = list(hist)
    if not years:
        years, hist = ["n/a"], {"n/a": 0}
    w, h, pad, bw = 720, 320, 50, 46
    maxv = max(hist.values()) or 1
    plot_h = h - 2 * pad
    bars = []
    for i, y in enumerate(years):
        v = hist[y]
        bh = int(plot_h * v / maxv)
        x = pad + i * (bw + 18)
        bars.append(f'<rect x="{x}" y="{h - pad - bh}" width="{bw}" height="{bh}" fill="#3b6fb5"/>')
        bars.append(f'<text x="{x + bw / 2}" y="{h - pad - bh - 6}" font-size="13" text-anchor="middle">{v}</text>')
        bars.append(f'<text x="{x + bw / 2}" y="{h - pad + 18}" font-size="12" text-anchor="middle">{y}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<rect width="{w}" height="{h}" fill="white"/>'
            f'<text x="{w / 2}" y="24" font-size="15" text-anchor="middle">'
            f'Included sources per year (provided set only, n={trend["n_sources_in_scope"]})</text>'
            f'<line x1="{pad - 8}" y1="{h - pad}" x2="{w - 10}" y2="{h - pad}" stroke="#333"/>'
            + "".join(bars) + "</svg>")


def _svg_prisma(counts: dict) -> str:
    steps = [("Records identified", counts["identified"]),
             ("Duplicates removed", counts["duplicates_removed"]),
             ("Title/abstract screened", counts["title_abstract_screened"]),
             ("Title/abstract excluded", counts["title_abstract_excluded"]),
             ("Full-text assessed", counts["full_text_assessed"]),
             ("Full-text excluded", counts["full_text_excluded"]),
             ("Studies included", counts["included"])]
    boxes, y = [], 20
    for label, v in steps:
        boxes.append(f'<rect x="40" y="{y}" width="300" height="44" fill="#eef3fa" stroke="#3b6fb5"/>'
                     f'<text x="52" y="{y + 27}" font-size="13">{escape(label)}: {v}</text>')
        if y > 20:
            boxes.append(f'<line x1="190" y1="{y - 16}" x2="190" y2="{y}" stroke="#333" marker-end="url(#a)"/>')
        y += 60
    h = y + 10
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="{h}" viewBox="0 0 400 {h}">'
            f'<defs><marker id="a" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">'
            f'<path d="M0,0 L8,4 L0,8 z" fill="#333"/></marker></defs>'
            f'<rect width="400" height="{h}" fill="white"/>' + "".join(boxes) + "</svg>")


# ── build ───────────────────────────────────────────────────────────────────

def _csv(path: Path, header: list, rows: list):
    import csv
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        wtr = csv.writer(fh)
        wtr.writerow(header)
        for row in rows:
            wtr.writerow([x if x is not None else "" for x in row])


def build(ir: dict, case: dict, out_dir) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = ir.get("kind")
    screening = compute_screening(ir)
    synthesis = compute_synthesis(ir)
    qchecks = check_quotes(ir)
    trend = compute_trend(ir) if (kind == "trend_analysis"
                                 or ir.get("trend", {}).get("phases")) else None
    novelty = compute_novelty(ir) if kind == "topic_novelty" else None
    computed = {"screening": screening, "synthesis": synthesis,
                "quote_checks": qchecks, "trend": trend, "novelty": novelty}
    ir["_computed"] = computed

    outputs = []
    blocks = _doc_model(ir, computed)
    md_path = out_dir / "research_report.md"
    md_path.write_text(_render_md(blocks), encoding="utf-8")
    outputs.append({"name": "research_report.md", "path": str(md_path),
                    "format": "md", "role": "md"})
    docx_path = out_dir / "research_report.docx"
    _render_docx(docx_path, blocks)
    outputs.append({"name": "research_report.docx", "path": str(docx_path),
                    "format": "docx", "role": "docx"})

    _csv(out_dir / "synthesis_matrix.csv",
         ["claim_id", "claim_text", "theme_id", "strength", "source_id",
          "source_title", "paragraph_id", "quote", "stance"],
         [[r[k] for k in ("claim_id", "claim_text", "theme_id", "strength",
                          "source_id", "source_title", "paragraph_id", "quote",
                          "stance")] for r in synthesis["matrix"]])
    outputs.append({"name": "synthesis_matrix.csv", "path": str(out_dir / "synthesis_matrix.csv"),
                    "format": "csv", "role": "csv"})
    _csv(out_dir / "screening_log.csv",
         ["record_id", "source_id", "title", "stage", "decision", "duplicate_of",
          "criteria_applied", "reason", "reviewer"],
         [[r["record_id"], r["source_id"], r["title"], r["stage"], r["decision"],
           r["duplicate_of"], ";".join(r["criteria_applied"] or []),
           r["reason"], r["reviewer"]] for r in screening["log"]])
    outputs.append({"name": "screening_log.csv", "path": str(out_dir / "screening_log.csv"),
                    "format": "csv", "role": "csv"})

    (out_dir / "prisma_flow.svg").write_text(_svg_prisma(screening["counts"]),
                                             encoding="utf-8")
    outputs.append({"name": "prisma_flow.svg", "path": str(out_dir / "prisma_flow.svg"),
                    "format": "svg", "role": "svg"})
    if trend:
        (out_dir / "trend_chart.svg").write_text(_svg_year_chart(trend), encoding="utf-8")
        outputs.append({"name": "trend_chart.svg", "path": str(out_dir / "trend_chart.svg"),
                        "format": "svg", "role": "svg"})
        w4kit.write_json(out_dir / "trend_stats.json", trend)
        outputs.append({"name": "trend_stats.json", "path": str(out_dir / "trend_stats.json"),
                        "format": "json", "role": "json"})
    if novelty:
        w4kit.write_json(out_dir / "novelty_assessment.json", novelty)
        outputs.append({"name": "novelty_assessment.json",
                        "path": str(out_dir / "novelty_assessment.json"),
                        "format": "json", "role": "json"})

    # provenance: bidirectional claim/record/source/section map
    claim_map = {}
    for c in ir.get("claims", []):
        checks = [q for q in qchecks if q["owner"] == f"claim {c.get('id')}"]
        claim_map[c.get("id")] = {
            "text": c.get("text"), "theme_id": c.get("theme_id"),
            "subquestion_id": c.get("subquestion_id"),
            "strength": c.get("strength"), "type": c.get("type", "fact"),
            "evidence": c.get("evidence", []),
            "quote_check": [q["status"] for q in checks],
            "support": synthesis["per_claim"].get(c.get("id"))}
    source_map = {}
    for s in ir.get("sources", []):
        path = resolve_file(s, ir)
        cited_by = [c.get("id") for c in ir.get("claims", [])
                    if any(e.get("source_id") == s.get("id") for e in c.get("evidence", []))]
        screened_by = [r.get("id") for r in ir.get("records", [])
                       if r.get("source_id") == s.get("id")]
        source_map[s.get("id")] = {
            "title": s.get("title"), "file": s.get("file"),
            "sha256": w4kit.sha256_file(path) if path else None,
            "cited_by_claims": cited_by, "screened_by_records": screened_by}
    section_map = {}
    cur = None
    for b in blocks:
        if b["t"] in ("h1", "h2", "h3"):
            cur = str(b["text"])
            section_map[cur] = []
        elif b["t"] == "p" and cur:
            for cid in re.findall(r"\[(C\d+|G\d+)\|", str(b["text"])):
                section_map[cur].append(cid)
    provenance = {
        "pipeline": ir.get("provenance", {}).get("pipeline"),
        "generated_at": w4kit.utc_now(), "case_id": ir.get("case_id"), "kind": kind,
        "claim_map": claim_map, "source_map": source_map,
        "record_map": {r["record_id"]: r for r in screening["log"]},
        "section_map": section_map,
        "prisma": screening["counts"],
        "synthesis_stats": {k: synthesis[k] for k in
                            ("n_claims", "n_evidence_rows", "sources_cited",
                             "sources_registered_not_cited", "claims_per_theme",
                             "contested_claims")},
        "quote_check_summary": dict(Counter(q["status"] for q in qchecks)),
        "quote_checks": qchecks,
        "changes": ir.get("provenance", {}).get("changes", []),
        "boundary": "provided_sources_only; prospective proposal; no experiments run",
    }
    if trend:
        provenance["trend_stats"] = trend
    if novelty:
        provenance["novelty_summary"] = novelty
    w4kit.write_json(out_dir / "provenance.json", provenance)
    outputs.append({"name": "provenance.json", "path": str(out_dir / "provenance.json"),
                    "format": "json", "role": "json"})
    return outputs


def summarize(ir: dict) -> dict:
    """Extra result.json fields recomputed from the IR (deterministic)."""
    comp = ir.get("_computed") or {}
    screening = comp.get("screening") or compute_screening(ir)
    synthesis = comp.get("synthesis") or compute_synthesis(ir)
    qchecks = comp.get("quote_checks") or check_quotes(ir)
    extra = {
        "prisma": screening["counts"],
        "exclusion_reasons": screening["exclusion_reasons"],
        "synthesis_stats": {k: synthesis[k] for k in
                            ("n_claims", "n_evidence_rows", "sources_cited",
                             "sources_registered_not_cited", "contested_claims")},
        "quote_check_summary": dict(Counter(q["status"] for q in qchecks)),
        "human_confirm": ([{"item": f"gap {g.get('id')}", "reason": g.get("text")}
                           for g in ir.get("gaps", []) if g.get("human_confirm")]
                          + [{"item": f"feasibility {f.get('id')}",
                              "reason": f.get("premise")}
                             for f in ir.get("topic", {}).get("feasibility", [])
                             if f.get("status") in ("assumption", "unknown")]),
        "boundary": "provided_sources_only; no global novelty/completeness claim; "
                    "no completed experiments",
    }
    if comp.get("trend"):
        extra["trend_summary"] = {
            "year_histogram": comp["trend"]["year_histogram"],
            "theme_direction": comp["trend"]["theme_direction"],
            "caveat": comp["trend"]["caveat"]}
    if comp.get("novelty"):
        extra["novelty_summary"] = {
            "items": [{"id": i["id"], "verdict": i["derived_verdict"]}
                      for i in comp["novelty"]["novelty_items"]],
            "n_assumptions": comp["novelty"]["n_assumptions"],
            "caveat": comp["novelty"]["caveat"]}
    return extra