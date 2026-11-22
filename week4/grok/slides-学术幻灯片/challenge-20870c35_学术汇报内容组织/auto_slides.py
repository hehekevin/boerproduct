"""auto_slides.py — deterministic "autopilot" entry point for the week4 SLIDES track.

Reads the ACTUAL organizer-provided local materials under --input, auto-extracts
a complete Deck IR (sources / pages with claims / source-bound bullets / speaker
notes / data-bound figures / qa), then runs the EXISTING engine path used by
assemble_deck.py (deckkit.validate_deck -> build_deck.build -> check_deck.check
-> export_deck.export) and writes an honest result.json preserving every
output_contract key + case_id. Stdlib only; additive — no engine file modified.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_slides.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules (mirrors w4/engines/search/auto_search.py):
  * Never fabricate: every claim/bullet/number is extracted or computed from real
    file content; each bullet carries a source id + locator.
  * Judgment-heavy fields (claim wording, compression, emphasis) are deterministic
    extractions flagged human_confirm in uncertainty[] (=> honest status partial).
  * Defensive extraction: a bad/missing file becomes an honest gap, never a crash.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is still
    written (status partial/failed) with contract keys + case_id + sources + error.
  * After this baseline runs, the agent may refine work/deck_ir.json within budget
    and re-run assemble_deck.py to improve narrative/judgment fields.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import figkit
    import deckkit
    import build_deck
    import check_deck
    import export_deck
except Exception:  # catastrophic import failure -> emergency writer below
    figkit = deckkit = build_deck = check_deck = export_deck = None

AUTO_NOTE = ("auto_slides autopilot: deterministic extraction from ACTUAL local "
             "materials + existing deck engine (validate/build/check/export); "
             "no fabricated claims/numbers/figures. Claim wording and compression "
             "are auto heuristics flagged human_confirm; refine work/deck_ir.json "
             "and re-run assemble_deck.py to improve.")

KIND_BY_SKILL = {
    "academic-talk-content-organization": "content_organization",
    "academic-ppt-generate-edit": "academic_ppt",
    "arena-paper-to-ppt": "paper_to_ppt",
    "ppt-template-format-adaptation": "template_adaptation",
}

ROLE_PRIORITY = ["question", "background", "method", "result", "discussion",
                 "limitation", "conclusion"]

ROLE_HINTS = [
    ("question", r"question|aim|hypothesi|问题|假设|研究目的"),
    ("limitation", r"limitation|weakness|局限|限制|不足"),
    ("method", r"method|material|approach|experiment|方法|材料"),
    ("result", r"result|finding|observation|结果|发现"),
    ("discussion", r"discussion|implication|interpret|讨论"),
    ("conclusion", r"conclusion|summary|takeaway|结论|总结"),
    ("background", r"introduction|background|related|prior|abstract|引言|背景|综述|摘要"),
]

SEC_PATTERNS = [
    re.compile(r"^\s*Sec\s*(\d+)\s*(?:\(([^)]*)\))?\s*[:：]?\s*(.*)$"),
    re.compile(r"^\s*(.+?)\s*\((?:Sec|Section)\s*\.?\s*(\d+)[^)]*\)\s*[:：]\s*(.*)$"),
    re.compile(r"^\s*(?:#{1,6})\s+(.+?)\s*$"),
    re.compile(r"^\s*(Introduction|Background|Methods?|Materials?|Results?|Discussion|"
               r"Conclusions?|Limitations?|Abstract|引言|背景|方法|材料与方法|结果|讨论|"
               r"结论|局限性?|摘要)\s*[:：]\s*(.*)$", re.I),
]


# ── small helpers ────────────────────────────────────────────────────────────

def clip(s, n=300):
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def cjk_ratio(s):
    if not s:
        return 0.0
    return sum(1 for ch in s if ord(ch) > 0x2E80) / len(s)


def compress(s, max_words=20, max_chars=110):
    """Compress a real sentence to bullet size without inventing content."""
    s = " ".join(str(s).split())
    if cjk_ratio(s) > 0.3:
        return s if len(s) <= max_chars else s[:max_chars - 1] + "…"
    words = s.split()
    if len(words) > max_words:
        s = " ".join(words[:max_words]) + " ..."
    if len(s) > max_chars:
        s = s[:max_chars - 4].rsplit(" ", 1)[0] + " ..."
    return s


def sentences(text):
    parts = re.split(r"(?<=[.!?。！？；;])\s+|\n+", str(text or ""))
    return [p.strip() for p in parts if p and len(p.strip()) >= 4]


def role_of(heading, text=""):
    h = str(heading or "").lower()
    for role, pat in ROLE_HINTS:
        if re.search(pat, h, re.I):
            return role
    if h and h not in ("preamble",) and not h.startswith("para"):
        return None
    blob = str(text or "")[:200].lower()
    for role, pat in ROLE_HINTS:
        if re.search(pat, blob, re.I):
            return role
    return None


# ── text / PDF reading (defensive, stdlib) ──────────────────────────────────

def pdf_text(data: bytes) -> str:
    """Best-effort stdlib PDF text salvage: inflate FlateDecode streams and pull
    text-show operators; fall back to raw utf-8 replace decoding."""
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = m.group(1)
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        try:
            s = raw.decode("utf-8", errors="replace")
        except Exception:
            continue
        if "Tj" in s or "TJ" in s:
            parts = re.findall(r"\((?:\\.|[^\\()])*\)", s)
            txt = " ".join(p[1:-1] for p in parts)
            txt = txt.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
            if txt.strip():
                chunks.append(txt)
    if chunks:
        return "\n\n".join(chunks)
    return data.decode("utf-8", errors="replace")


def read_material_text(path):
    data = Path(path).read_bytes()
    if str(path).lower().endswith(".pdf") or data[:5] == b"%PDF-":
        return pdf_text(data)
    return data.decode("utf-8", errors="replace")


def parse_sections(text):
    """Split a document into located sections. Handles 'Sec1 (Introduction):',
    'Methods (Sec 2):', markdown headers and bare keyword headings."""
    title = None
    tm = re.search(r"^\s*Title\s*[:：]\s*(.+)$", text, re.M)
    if tm:
        title = tm.group(1).strip()
    sections, cur, preamble = [], None, []
    for ln in text.splitlines():
        if re.match(r"^\s*Title\s*[:：]", ln):
            if not title:
                title = ln.split(":", 1)[-1].split("：", 1)[-1].strip()
            continue
        start = None
        for i, pat in enumerate(SEC_PATTERNS):
            m = pat.match(ln)
            if m:
                if i == 0:
                    loc, head, body = f"Sec{m.group(1)}", m.group(2) or "", m.group(3)
                elif i == 1:
                    loc, head, body = f"Sec{m.group(2)}", m.group(1), m.group(3)
                elif i == 2:
                    loc, head, body = m.group(1)[:60], m.group(1), ""
                    if not title and ln.startswith("# "):
                        title = head
                else:
                    loc, head, body = m.group(1), m.group(1), m.group(2)
                start = {"locator": loc.strip(), "heading": head.strip(), "buf": []}
                if body.strip():
                    start["buf"].append(body.strip())
                break
        if start:
            if cur:
                sections.append(cur)
            cur = start
        elif cur is not None:
            if ln.strip():
                cur["buf"].append(ln.strip())
        elif ln.strip():
            preamble.append(ln.strip())
    if cur:
        sections.append(cur)
    out = []
    if preamble:
        body = " ".join(preamble)
        is_notice = (len(body) < 300 and
                     re.search(r"synthetic|example only|interface demo|not a formal|"
                               r"示例|仅供演示", body, re.I))
        if not is_notice:
            out.append({"locator": "preamble", "heading": "preamble",
                        "text": body, "role": role_of("preamble", body) or "background"})
    for s in sections:
        body = " ".join(s["buf"]).strip()
        if not body:
            continue
        out.append({"locator": s["locator"], "heading": s["heading"] or s["locator"],
                    "text": body, "role": role_of(s["heading"], body) or "discussion"})
    if not out and text.strip():
        for i, para in enumerate(re.split(r"\n\s*\n", text.strip()), 1):
            para = " ".join(para.split())
            if para:
                out.append({"locator": f"para{i}", "heading": clip(para, 40),
                            "text": para, "role": role_of("", para) or "discussion"})
    if not title:
        hm = re.search(r"^#\s+(.+)$", text, re.M)
        title = hm.group(1).strip() if hm else None
    return title, out


# ── table / chart detection (real columns only) ─────────────────────────────

def detect_chart(rows, data_path):
    if not rows or len(rows) < 2:
        return None
    cols = list(rows[0].keys())
    numeric = {}
    for c in cols:
        vals = [figkit.to_float(r.get(c)) for r in rows if str(r.get(c) or "").strip()]
        numeric[c] = bool(vals) and sum(v is not None for v in vals) >= 0.8 * len(vals)
    err = next((c for c in cols if re.fullmatch(r"sd|sem|se|std|error|err", c.lower())), None)
    ncol = next((c for c in cols if re.fullmatch(r"n|count|sample_?size", c.lower())), None)
    y = next((c for c in cols if numeric[c] and c not in (err, ncol)
              and re.search(r"expression|value|score|mean|rate|level|amount|conc|yield|y",
                            c.lower())), None)
    if not y:
        y = next((c for c in cols if numeric[c] and c not in (err, ncol)), None)
    if not y:
        return None
    cats = [c for c in cols if not numeric[c] and c not in (y,)]
    series = next((c for c in cats if re.search(r"group|arm|series|condition|treatment|"
                                                r"type|category|组|处理", c.lower())), None)
    if not series:
        series = next((c for c in cats
                       if 2 <= len({str(r.get(c)) for r in rows}) <= 8), None)
    x = next((c for c in cols if c not in (y, series, err, ncol)
              and re.search(r"day|time|week|month|year|date|dose|point|x|时间|天", c.lower())), None)
    if not x:
        x = next((c for c in cols if c not in (y, series, err, ncol)), None)
    if not x or x == y:
        return None
    ctype = "grouped_bar" if series else ("line" if numeric[x] else "bar")
    chart = {"chart_type": ctype, "data_path": str(data_path),
             "x": x, "y": y, "x_label": x, "y_label": y}
    if series:
        chart["series"] = series
    if err:
        chart["error"] = err
        chart["error_kind"] = ("sd" if err.lower() in ("sd", "std")
                               else "sem" if err.lower() in ("sem", "se") else "unknown")
    if ncol:
        chart["n"] = ncol
    return chart


def table_bullets(rows, chart, sid, name):
    """Real first->last values per series, computed from the actual table."""
    x, y = chart["x"], chart["y"]
    series = chart.get("series")
    keys = list(dict.fromkeys(str(r.get(series)) for r in rows)) if series else [""]
    bullets = []
    for k in keys[:3]:
        sub = [r for r in rows if not series or str(r.get(series)) == k]
        if not sub:
            continue
        first, last = sub[0], sub[-1]
        label = f"{k}: " if k else ""
        txt = (f"{label}{y} {first.get(y)} -> {last.get(y)} "
               f"({x} {first.get(x)}..{last.get(x)})")
        bullets.append({"text": compress(txt), "source": sid,
                        "source_locator": f"{name} rows ({k or 'all'})"})
    return bullets


# ── kind detection ───────────────────────────────────────────────────────────

def kind_supported(kind, case_id):
    if not deckkit:
        return True
    probe = {"ir_version": "1.0", "case_id": case_id or "probe", "kind": kind,
             "sources": [], "pages": [{"id": "p1", "role": "title", "claim": "probe"}]}
    try:
        rep = deckkit.validate_deck(probe)
        return not any("unknown kind" in e for e in rep["errors"])
    except Exception:
        return False


def detect_kind(args_kind, case):
    candidates = []
    if args_kind:
        candidates.append(args_kind.strip().replace("-", "_"))
    raw_kind = (case.get("raw") or {}).get("kind")
    if raw_kind:
        candidates.append(str(raw_kind).strip().replace("-", "_"))
    skill = SCRIPT_DIR / "SKILL.md"
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:2000]
            m = re.search(r"^name:\s*([a-z0-9-]+)\s*$", head, re.M)
            if m and m.group(1) in KIND_BY_SKILL:
                candidates.append(KIND_BY_SKILL[m.group(1)])
        except Exception:
            pass
    candidates.append("academic_ppt")
    for k in candidates:
        if kind_supported(k, case.get("case_id")):
            return k
    return "academic_ppt"


# ── Deck IR auto-fill ────────────────────────────────────────────────────────

def build_ir(case, kind, sources, docs, tables, uncertainty):
    raw = case.get("raw") or {}
    task = case.get("task_md") or ""
    main = max(docs, key=lambda d: len(d.get("text", "")), default=None)
    title = (main or {}).get("title") or raw.get("title")
    if not title:
        title = clip(task.strip().splitlines()[0], 120) if task.strip() else None
    if not title:
        title = "(no extractable title in provided materials)"
        uncertainty.append({"item": "title", "reason": "no title found in materials/case",
                            "handling": "human_confirm"})
    audience = raw.get("audience") or "academic audience"
    duration = raw.get("duration_min") or 10
    target = raw.get("slide_count_target")
    if not target:
        m = re.search(r"(\d+)[-\s]?(?:slide|页|张)", task)
        target = int(m.group(1)) if m else 8
    try:
        duration, target = int(duration), int(target)
    except Exception:
        duration, target = 10, 8
    all_text = " ".join(d.get("text", "") for d in docs)
    cjk = cjk_ratio(all_text[:3000]) > 0.1
    tpl = {"theme_font": "DejaVu Sans",
           "cjk_font": "Noto Sans CJK SC" if cjk else "DejaVu Sans",
           "title_pt": 28, "body_pt": 18, "min_pt": 14, "accent": "#0C5DA5",
           "footer": str(case.get("case_id", "")), "max_bullets": 4,
           "max_words_per_bullet": 20}
    ir = {"ir_version": "1.0", "case_id": case.get("case_id", "unknown-case"),
          "kind": kind, "title": clip(title, 160), "audience": audience,
          "goal": clip(raw.get("task") or task or title, 300),
          "duration_min": duration, "slide_count_target": target,
          "template": tpl, "sources": sources, "pages": [], "qa": [],
          "exports": [{"format": "pptx"}, {"format": "pdf"}, {"format": "png"}],
          "uncertainty": uncertainty}

    msid = main["sid"] if main else (sources[0]["id"] if sources else None)
    title_page = {"id": "p1", "role": "title", "layout": "title",
                  "claim": compress(title, 24, 140),
                  "notes": "Auto baseline: open with the one-sentence takeaway."}
    if msid:
        title_page.update({"source": msid, "source_locator": "Title"})
    ir["pages"].append(title_page)

    # gather content sections across all text documents
    content = []
    for d in docs:
        for s in d.get("sections", []):
            content.append({**s, "sid": d["sid"], "name": d["name"]})
    # budget selection: backbone roles first (question/method/result/limitation/
    # conclusion), then remaining roles; display in narrative order afterwards.
    select_order = ["question", "method", "result", "limitation", "conclusion",
                    "background", "discussion"]
    content.sort(key=lambda s: (select_order.index(s["role"])
                                if s["role"] in select_order else 99))
    budget = max(1, target - 1)
    selected = content[:budget]
    omitted = [f"{s['name']} {s['locator']}" for s in content[budget:]]
    selected.sort(key=lambda s: (ROLE_PRIORITY.index(s["role"])
                                 if s["role"] in ROLE_PRIORITY else 99))
    # chart from the first chartable table
    chart, chart_tbl = None, None
    for t in tables:
        chart = detect_chart(t["rows"], t["path"])
        if chart:
            chart_tbl = t
            break
    used_result = False
    pages = ir["pages"]
    for s in selected:
        sents = sentences(s["text"])
        if not sents:
            continue
        role = s["role"] if s["role"] in deckkit.VALID_ROLES else "discussion"
        pid = f"p{len(pages) + 1}"
        claim_src, bullet_srcs = sents[0], sents[1:5]
        if not bullet_srcs and len(claim_src) > 80:
            # single long sentence: split at a real comma near the middle
            mid = len(claim_src) // 2
            cuts = [m.start() for m in re.finditer(r"[,;，；]", claim_src)]
            if cuts:
                cut = min(cuts, key=lambda c: abs(c - mid))
                claim_src, bullet_srcs = claim_src[:cut], [claim_src[cut + 1:].strip()]
        page = {"id": pid, "role": role, "layout": "content",
                "claim": compress(claim_src, 24, 140),
                "bullets": [{"text": compress(t), "source": s["sid"],
                             "source_locator": f"{s['locator']} sentence{i}"}
                            for i, t in enumerate(bullet_srcs, 2)],
                "notes": (f"Auto baseline from {s['name']} {s['locator']}: "
                          "verify wording/emphasis before presenting."),
                "source": s["sid"], "source_locator": s["locator"]}
        if role == "result" and chart and not used_result:
            page["figures"] = [{"ref": "Fig1", "chart": dict(chart),
                                "caption": compress(f"Fig1 {chart['y']} by {chart['x']} "
                                                    f"({Path(chart['data_path']).name})", 24, 120),
                                "source": chart_tbl["sid"],
                                "source_locator": Path(chart["data_path"]).name}]
            page["layout"] = "picture"
            used_result = True
        pages.append(page)
    if chart and not used_result and len(pages) < target + 1:
        # no result section in text: build a data-bound result page from the table
        bullets = table_bullets(chart_tbl["rows"], chart, chart_tbl["sid"], chart_tbl["name"])
        nums = [figkit.to_float(r.get(chart["y"])) for r in chart_tbl["rows"]]
        nums = [v for v in nums if v is not None]
        claim = (f"{chart['y']} ranges {min(nums)}..{max(nums)} in {chart_tbl['name']}"
                 if nums else f"Data table {chart_tbl['name']}")
        pid = f"p{len(pages) + 1}"
        pages.append({"id": pid, "role": "result", "layout": "picture",
                      "claim": compress(claim, 24, 140), "bullets": bullets,
                      "figures": [{"ref": "Fig1", "chart": dict(chart),
                                   "caption": compress(f"Fig1 {chart['y']} by {chart['x']} "
                                                       f"({chart_tbl['name']})", 24, 120),
                                   "source": chart_tbl["sid"],
                                   "source_locator": chart_tbl["name"]}],
                      "notes": "Auto baseline: walk the figure; values computed from the table.",
                      "source": chart_tbl["sid"], "source_locator": chart_tbl["name"]})
    if omitted:
        uncertainty.append({"item": "slide budget",
                            "reason": "sections omitted to respect slide_count_target: "
                                      + "; ".join(omitted[:8]),
                            "handling": "human_confirm"})
    roles = {p["role"] for p in pages}
    missing = [bb for bb in ("question", "method", "result", "conclusion")
               if bb not in roles and not (bb == "question" and "background" in roles)]
    if missing:
        uncertainty.append({"item": "narrative backbone",
                            "reason": f"roles not locatable in materials: {missing}; "
                                      "no content fabricated to fill them",
                            "handling": "human_confirm"})
    if not docs:
        uncertainty.append({"item": "materials",
                            "reason": "no extractable text document in provided materials",
                            "handling": "human_confirm"})
    # Q&A prep for content_organization, grounded in the real limitation page
    if kind == "content_organization":
        lim = next((p for p in pages if p["role"] == "limitation"), None)
        if lim and lim.get("bullets"):
            ir["qa"].append({"question": "What limitations bound these findings?",
                             "answer_points": [b["text"] for b in lim["bullets"][:3]],
                             "backup_page": lim["id"], "source": lim["source"]})
    uncertainty.append({"item": "claims/bullets/notes",
                        "reason": "auto-extracted and compressed from source sentences; "
                                  "scientific judgment and emphasis pending human review",
                        "handling": "human_confirm"})
    ir["provenance"] = {
        "pipeline": "material -> auto_extract -> deck IR -> validate -> editable pptx -> render/export",
        "skill_version": getattr(deckkit, "SKILL_VERSION", "1.0.0"),
        "changes": [{"step": "auto_extract", "at": figkit.utc_now(),
                     "detail": f"deterministic extraction from {len(sources)} material files"}],
    }
    return ir


# ── status / result helpers (mirror assemble_deck.py policy) ─────────────────

def fill_contract(result, case, artifacts):
    """Additive post-fill: point contract keys at real artifacts when the engine
    left a structured pointer (e.g. editable_pptx / png previews / outline)."""
    contract = case.get("output_contract") or {}
    if not isinstance(contract, dict):
        return
    by_role = {}
    for o in artifacts:
        by_role.setdefault(o.get("role", ""), o)
        by_role.setdefault(o.get("format", ""), o)
    for key in contract:
        kl = key.lower()
        cur = result.get(key)
        if cur not in (None,) and not isinstance(cur, dict):
            continue
        art = None
        if "pptx" in kl or "editable" in kl or "deck_pptx" in kl:
            art = by_role.get("pptx")
        elif "outline" in kl or kl.endswith("_md"):
            art = by_role.get("md")
        elif "png" in kl or "preview" in kl:
            art = by_role.get("png") or by_role.get("png-preview")
        elif "pdf" in kl:
            art = by_role.get("pdf")
        if art:
            result[key] = art["path"]


def emergency_result(case, out_dir, error, sources=None, kind=None):
    """Last-resort honest result.json using ONLY json/os (figkit may be unavailable)."""
    contract = (case or {}).get("output_contract") or {}
    result = {}
    if isinstance(contract, dict):
        for key, spec in contract.items():
            kl = key.lower()
            if "json" in kl or "result" in kl or "meta" in kl:
                result[key] = "result.json"
            elif isinstance(spec, dict) and "default" in spec:
                result[key] = spec["default"]
            else:
                result[key] = {"_contract_spec": spec, "_status": "see notes/error"}
    elif isinstance(contract, list):
        result["output_contract"] = contract
    result.update({"case_id": (case or {}).get("case_id", "unknown-case"),
                   "status": "failed", "kind": kind,
                   "sources": sources or [],
                   "uncertainty": [{"item": "pipeline", "reason": str(error),
                                    "handling": "human_confirm"}],
                   "notes": AUTO_NOTE, "error": str(error)})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "result.json", "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return result


# ── main pipeline ────────────────────────────────────────────────────────────

def run(args):
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work)
    work_dir.mkdir(parents=True, exist_ok=True)

    case = figkit.load_case(args.input)
    materials = figkit.list_materials(args.input)
    sources, docs, tables, uncertainty = [], [], [], []
    template_path = None
    task_text = ""
    for i, m in enumerate(materials, 1):
        sid = f"S{i}"
        ext = (m.get("ext") or "").lstrip(".").lower() or "file"
        try:
            ver = figkit.sha256_file(m["path"])[:12]
        except Exception:
            ver = "unknown"
        kind_label = ("table" if ext in ("csv", "tsv", "tab") else
                      "pdf" if ext == "pdf" else
                      "template" if ext == "pptx" else "text")
        sources.append({"id": sid, "locator": m["name"], "kind": kind_label,
                        "version": ver, "path": m["path"]})
        low = m["name"].lower()
        if low == "case.json":
            continue
        if low == "task.md":
            try:
                task_text = read_material_text(m["path"])
            except Exception:
                pass
            continue
        if ext == "pptx":
            if template_path is None:
                template_path = m["path"]
            continue
        try:
            if ext in ("csv", "tsv", "tab"):
                rows = figkit.read_table(m["path"])
                if rows:
                    tables.append({"sid": sid, "name": m["name"],
                                   "path": m["path"], "rows": rows})
                else:
                    uncertainty.append({"item": m["name"], "reason": "table has no data rows",
                                        "handling": "human_confirm"})
            else:
                text = read_material_text(m["path"])
                if text and text.count("\ufffd") / len(text) > 0.1:
                    uncertainty.append({"item": m["name"],
                                        "reason": "file is not decodable text (binary/corrupt); "
                                                  "registered as source, content not extracted",
                                        "handling": "human_confirm"})
                    continue
                title, sections = parse_sections(text)
                docs.append({"sid": sid, "name": m["name"], "text": text,
                             "title": title, "sections": sections})
        except Exception as e:
            uncertainty.append({"item": m["name"],
                                "reason": f"extraction failed: {type(e).__name__}: {e}; "
                                          "file registered but not parsed",
                                "handling": "human_confirm"})
    if task_text and not case.get("task_md"):
        case["task_md"] = task_text
    if not materials:
        uncertainty.append({"item": "materials",
                            "reason": "input directory empty or unreadable; nothing to extract",
                            "handling": "human_confirm"})

    kind = detect_kind(args.kind, case)
    ir = build_ir(case, kind, sources, docs, tables, uncertainty)
    if template_path:
        ir["template"]["path"] = template_path
    ir["provenance"]["page_map"] = deckkit.build_page_map(ir)
    # de-duplicate uncertainty entries
    seen, uniq = set(), []
    for u in ir["uncertainty"]:
        key = (u.get("item"), u.get("reason"))
        if key not in seen:
            seen.add(key)
            uniq.append(u)
    ir["uncertainty"] = uniq

    work_ir = work_dir / "deck_ir.json"
    figkit.write_json(work_ir, ir)

    # ── SAME validate+build path as assemble_deck.py ──
    validation = deckkit.validate_deck(ir)
    figkit.write_json(out_dir / "validation.json", validation)
    artifacts, build_info, check_rep, export_rep = [], {}, None, None
    status = None
    if validation["ok"]:
        try:
            build_info = build_deck.build(ir, out_dir, template_path)
            artifacts.append({"name": "deck.pptx", "path": build_info["pptx"],
                              "format": "pptx", "role": "pptx"})
            check_rep = check_deck.check(ir, out_dir)
            figkit.write_json(out_dir / "deck_check.json", check_rep)
            ex = export_deck.export(ir, out_dir)
            artifacts = ex["artifacts"]
            export_rep = ex["report"]
            status = "success" if export_rep.get("true_render") else "partial"
        except Exception as e:  # noqa: BLE001
            status = "partial"
            ir["uncertainty"].append({"item": "build", "reason": f"{type(e).__name__}: {e}",
                                      "impact": "deck not fully built",
                                      "handling": "IR+validation saved; fix and re-run"})
            traceback.print_exc()
    else:
        status = "partial"

    figkit.write_json(out_dir / "deck_ir.json", ir)
    figkit.write_json(out_dir / "provenance.json", ir["provenance"])
    # editable source-bound outline (paper_to_ppt convention; additive for others)
    outline = ["# " + ir.get("title", "Deck outline"), ""]
    for p in ir.get("pages", []):
        outline.append(f"## {p.get('id', '?')} [{p.get('role', '')}] {p.get('claim', '')}")
        outline.append(f"source: {p.get('source', '')} {p.get('source_locator', '')}")
        for b in p.get("bullets", []):
            outline.append(f"- {b.get('text', '')} ({b.get('source', '')} {b.get('source_locator', '')})")
        for f in p.get("figures", []):
            outline.append(f"- figure {f.get('ref', '')}: {f.get('caption', '')} ({f.get('source', '')})")
        if p.get("notes"):
            outline.append(f"notes: {p['notes']}")
        outline.append("")
    (out_dir / "outline.md").write_text("\n".join(outline), encoding="utf-8")
    artifacts.append({"name": "outline.md", "path": str(out_dir / "outline.md"),
                      "format": "md", "role": "md"})

    notes = AUTO_NOTE
    if not validation["ok"]:
        notes += " deck validation failed: " + "; ".join(validation["errors"])
    elif validation["warnings"]:
        notes += " warnings: " + "; ".join(validation["warnings"][:6])
    result = figkit.build_result(case, ir, artifacts, status, validation, export_rep, notes)
    result["deck_info"] = {k: build_info.get(k) for k in
                           ("n_slides", "used_template", "slide_size_in") if k in build_info}
    result["deck_check"] = check_rep
    result.setdefault("provenance", {})["page_map"] = ir["provenance"].get("page_map", {})
    fill_contract(result, case, artifacts)
    result["autopilot"] = {"kind": kind, "n_materials": len(materials),
                           "n_pages": len(ir.get("pages", [])),
                           "work_ir": str(work_ir)}
    figkit.write_result(out_dir, result)
    print(json.dumps({"status": status, "case_id": case["case_id"], "kind": kind,
                      "validation_ok": validation["ok"], "errors": validation["errors"],
                      "n_slides": build_info.get("n_slides"),
                      "n_pages": len(ir.get("pages", [])),
                      "deck_check": (check_rep or {}).get("overall"),
                      "export": (export_rep or {}).get("overall"),
                      "result": str(out_dir / "result.json")}, ensure_ascii=False, indent=2))
    return 0 if status in ("success", "partial") else 1


def main():
    ap = argparse.ArgumentParser(description="slides track autopilot (auto-extract Deck IR + run engine)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if figkit is None or deckkit is None or build_deck is None:
            raise RuntimeError("cannot import sibling figkit.py / deckkit.py / build_deck.py")
        return run(args)
    except Exception as e:
        traceback.print_exc()
        # honest fallback: NEVER exit without result.json
        try:
            case = figkit.load_case(args.input) if figkit else {}
            kind = args.kind or "academic_ppt"
            try:
                mats = figkit.list_materials(args.input) if figkit else []
                sources = [{"id": f"S{i}", "locator": m["name"],
                            "kind": (m.get("ext") or "").lstrip(".")}
                           for i, m in enumerate(mats, 1)]
            except Exception:
                sources = []
            ir = {"ir_version": "1.0", "case_id": case.get("case_id", "unknown-case"),
                  "kind": kind, "sources": sources, "pages": [],
                  "uncertainty": [{"item": "pipeline",
                                   "reason": f"{type(e).__name__}: {e}",
                                   "handling": "human_confirm"}]}
            result = figkit.build_result(case, ir, [], "failed",
                                         notes=AUTO_NOTE + f" FATAL: {e}")
            result["error"] = f"{type(e).__name__}: {e}"
            figkit.write_result(args.out, result)
        except Exception as e2:
            if not case:
                try:
                    with open(Path(args.input) / "case.json", encoding="utf-8") as fh:
                        raw = json.load(fh)
                    case = {"case_id": raw.get("case_id", "unknown-case"),
                            "output_contract": raw.get("output_contract") or {}}
                except Exception:
                    case = {}
            emergency_result(case, args.out, f"{e}; fallback also failed: {e2}",
                             sources=sources, kind=kind)
        print(json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())