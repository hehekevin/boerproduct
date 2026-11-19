#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""format_check.py — 逐项格式机检（排得对）：稿件 × 规格清单 → 逐项三元组核对报告

对 checklist.json 中每个 checkable 条目做机器核对，逐项输出
  {item_id, category, template_value, applied, match, source}
md 级：必需章节 / 标题编号连续与层级跳变 / 题注前缀与顺序编号 / 图表交叉引用顺序 / 引用样式与孤立引用 / 摘要字数
docx 级（--docx 给出时，解析 XML）：页边距 / 栏数 / 字号 / 行距 —— 数值容差 ±0.05cm
闸门显式枚举 enforced/skipped_not_provided/skipped_ablation/not_found/unreadable；
--ablate 退化模式关闭「docx 排版规格机检 + 题注格式机检 + 标题编号机检」，用于同输入双跑对照取证。
退出码恒 0：verdict/fail 计数如实写报告。
"""
import argparse, json, os, re, sys, time, zipfile

try:
    import _rlog
except Exception:
    _rlog = None

TWIPS_PER_CM = 567.0


def norm_head(s):
    return re.sub(r"[\s#*_:：·\-—0-9.]+", "", s).lower()


def load(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


# ---------------- md 级检查 ----------------

def check_sections(draft, req):
    if not req:
        return {"item": "sections_complete", "gate": "skipped_not_provided", "verdict": "warn",
                "template_value": None, "applied": None, "match": None,
                "gate_note": "checklist 无 required_sections，本项未运行；下游不得宣称章节已核对。"}
    heads = [norm_head(m.group(1)) for m in
             (re.match(r"^\s*#{1,6}\s*(.+)$", l) for l in draft.splitlines()) if m]
    heads += [norm_head(m.group(1)) for m in
              (re.match(r"^\s*(第?[一二三四五六七八九十\d]+[、.．章节])\s*\S+", l) for l in draft.splitlines()) if m]
    missing = [s for s in req if not any(norm_head(s) in h or h in norm_head(s) for h in heads if h)]
    return {"item": "sections_complete", "gate": "enforced", "template_value": req,
            "applied": [s for s in req if s not in missing], "missing": missing,
            "match": not missing, "verdict": "pass" if not missing else "fail",
            "hint": "补齐缺失章节；确不适用则在 uncertainty 显式声明，不静默省略。" if missing else ""}


def check_headings(draft):
    nums = []
    for l in draft.splitlines():
        m = re.match(r"^\s*#{1,6}\s+(?:第?[一二三四五六七八九十]+[章节]\s*)?(\d+(?:\.\d+)*)[、.\s]", l)
        if not m:
            m = re.match(r"^\s*(\d+(?:\.\d+)+)\s", l)
        if m:
            parts = [int(x) for x in m.group(1).split(".")]
            nums.append(parts)
    if not nums:
        return {"item": "heading_numbering", "gate": "not_found", "verdict": "warn",
                "template_value": "章节编号连续且层级不跳变", "applied": None, "match": None,
                "gate_note": "稿内未检出编号标题，本项未运行。"}
    problems = []
    prev = []
    for parts in nums:
        if prev:
            if parts[:-1] != prev[:-1] and parts[:-1] != prev[:len(parts) - 1]:
                # 允许同级递增或进入子级；否则跳变
                if parts[:len(prev)] != prev[:len(parts)] and parts[:-1] != prev[:-1]:
                    problems.append({"at": ".".join(map(str, prev)), "to": ".".join(map(str, parts)),
                                     "kind": "level_jump_or_repeat"})
            if parts[:-1] == prev[:-1] and parts[-1] != prev[-1] + 1:
                problems.append({"at": ".".join(map(str, prev)), "to": ".".join(map(str, parts)),
                                 "kind": "number_not_continuous"})
        prev = parts
    return {"item": "heading_numbering", "gate": "enforced",
            "template_value": "章节编号连续且层级不跳变",
            "applied": [".".join(map(str, p)) for p in nums][:40],
            "match": not problems, "problems": problems[:20],
            "verdict": "pass" if not problems else "fail",
            "hint": "编号跳号/层级跳变需修正标题编号。" if problems else ""}


def _caption_prefix(checklist):
    """从 checklist 题注条目推导期望前缀字面量（如 图 / Figure. / Table），默认 图/表。"""
    fig = tab = None
    for it in (checklist.get("items") or []):
        if it.get("category") == "caption" and "前缀" in (it.get("name") or ""):
            m = re.search(r"(图|表|Figure|Fig\.?|Table)\s*([0-9]+)", it.get("template_value", ""), re.I)
            if m:
                key = m.group(1).strip()
                if re.match(r"^[A-Za-z]", key):
                    fig = fig or key
                else:
                    fig = fig or key
                    if key == "表":
                        tab = key
    if fig is None:
        fig = "图"
    if tab is None:
        tab = "表"
    return fig, tab


def check_captions(draft, checklist):
    fig_key, tab_key = _caption_prefix(checklist)
    caps, problems = [], []
    for ln, l in enumerate(draft.splitlines(), 1):
        m = re.match(r"^\s*\**\s*(图\s*\d+|表\s*\d+|Figure\s*\d+|Fig\.?\s*\d+|Table\s*\d+)\b", l, re.I)
        if not m or len(l) >= 220:
            continue
        rest = l[m.end():].strip().lstrip("*").strip()
        # 题注行特征：token 后是无句号的短标题；以句号/逗号续行的正文段不算题注
        if re.search(r"[。；，]", rest.rstrip("）)")):
            continue
        caps.append({"kind": "fig" if re.match(r"图|Figure|Fig", m.group(1), re.I) else "tab",
                     "token": m.group(1), "line": ln})
    for kind, key, seq in (("fig", fig_key, []), ("tab", tab_key, [])):
        k = 0
        for c in caps:
            if c["kind"] != kind:
                continue
            k += 1
            want = re.sub(r"\s+", "", key) + str(k)
            got = re.sub(r"\s+", "", c["token"])
            if got != want:
                problems.append({"line": c["line"], "got": c["token"], "want": want, "kind": "prefix_or_order"})
            seq.append(got)
    return {"item": "caption_format", "gate": "enforced" if caps else "not_found",
            "template_value": {"fig_prefix": fig_key, "tab_prefix": tab_key, "sequential": True},
            "applied": caps[:40],
            "match": (not problems) if caps else None,
            "problems": problems[:20], "verdict": ("warn" if not caps else ("pass" if not problems else "fail")),
            "gate_note": "稿内未检出题注，本项未运行。" if not caps else "",
            "hint": "题注前缀须符合模板（如 图N/Figure N.）且按出现顺序连续编号。"}


def check_xref(draft):
    seq = []
    for m in re.finditer(r"(?:图|表|Figure|Fig\.?|Table)\s*(\d+)", draft):
        seq.append(int(m.group(1)))
    mono = all(b >= a for a, b in zip(seq, seq[1:]))
    return {"item": "cross_reference", "gate": "enforced" if seq else "not_found",
            "template_value": "图表编号按正文提及顺序递增", "applied": seq[:60], "match": mono if seq else None,
            "verdict": "warn" if not seq else ("pass" if mono else "warn"),
            "gate_note": "稿内未检出图表引用，本项未运行。" if not seq else "",
            "hint": "图表编号应按正文首次提及顺序递增。"}


def check_citations(draft, checklist):
    style = None
    for it in (checklist.get("items") or []):
        if it.get("category") == "citation":
            style = it.get("template_value"); break
    cites, entries = set(), set()
    for m in re.finditer(r"\[(\d{1,3}(?:\s*[,，\-]\s*\d{1,3})*)\]", draft):
        for p in re.split(r"[,，\-]", m.group(1)):
            if p.strip().isdigit():
                cites.add(int(p.strip()))
    ref_zone = ""
    m = re.search(r"#{1,6}\s*参\s*考\s*文\s*献|#{1,6}\s*References", draft, re.I)
    if m:
        ref_zone = draft[m.end():]
    else:
        ref_zone = "\n".join(draft.splitlines()[-40:])
    for l in ref_zone.splitlines():
        em = re.match(r"^\s*[\[(]?(\d{1,3})[\]).]\s", l)
        if em:
            entries.add(int(em.group(1)))
    if not cites and not entries:
        return {"item": "citation_style", "gate": "not_found", "verdict": "warn",
                "template_value": {"style": style}, "applied": None, "match": None,
                "gate_note": "稿内未检出编号引用与文献表，本项未运行。"}
    orphan_c = sorted(c for c in cites if c not in entries)
    orphan_e = sorted(e for e in entries if e not in cites)
    style_ok = None
    if style and entries:
        ok = re.search(r"7714|顺序编码|GB", str(style))
        style_ok = bool(ok)  # 顺序编码制与编号条目形态一致；作者-年制另行人工判断
    return {"item": "citation_style", "gate": "enforced", "template_value": {"style": style},
            "applied": {"cited": sorted(cites), "listed": sorted(entries)},
            "match": not (orphan_c or (style_ok is False)),
            "cited_not_listed": orphan_c, "listed_not_cited": orphan_e,
            "verdict": "pass" if not (orphan_c or (style_ok is False)) else "fail",
            "hint": "正文引用须在文献表有条目；样式与模板不符须逐条修正。"}


def check_abstract(draft, checklist):
    for it in (checklist.get("items") or []):
        if it.get("category") == "abstract" and it.get("numeric"):
            lo, hi = it["numeric"]["min"], it["numeric"]["max"]
            m = re.search(r"#{1,6}\s*摘\s*要(.*?)(?=#{1,6}\s|\Z)", draft, re.S | re.I)
            zone = m.group(1) if m else ""
            n = len(re.findall(r"[\u4e00-\u9fff]", zone))
            return {"item": "abstract_word_range", "gate": "enforced", "template_value": [lo, hi],
                    "applied": n, "match": lo <= n <= hi,
                    "verdict": "pass" if lo <= n <= hi else "warn",
                    "hint": "摘要字数 %d 超出 [%d,%d]。" % (n, lo, hi)}
    return {"item": "abstract_word_range", "gate": "skipped_not_provided", "verdict": "warn",
            "template_value": None, "applied": None, "match": None,
            "gate_note": "checklist 无摘要字数规格，本项未运行。"}


# ---------------- docx 级检查（转得全之后：排得对的落点） ----------------

def docx_spec(path):
    """解析 docx XML：页边距(cm)/栏数/正文字号(pt)/行距(倍)。失败返回 None。"""
    try:
        with zipfile.ZipFile(path) as z:
            doc = z.read("word/document.xml").decode("utf-8", "ignore")
            try:
                styles = z.read("word/styles.xml").decode("utf-8", "ignore")
            except Exception:
                styles = ""
    except Exception:
        return None
    spec = {}
    m = re.search(r'<w:pgMar[^>]*w:top="(-?\d+)"[^>]*w:bottom="(-?\d+)"[^>]*w:left="(-?\d+)"[^>]*w:right="(-?\d+)"', doc)
    if m:
        spec["margins_cm"] = {k: round(int(v) / TWIPS_PER_CM, 2)
                              for k, v in zip(("top", "bottom", "left", "right"), m.groups())}
    m = re.search(r'<w:cols[^>]*w:num="(\d+)"', doc)
    spec["columns"] = int(m.group(1)) if m else 1
    m = re.search(r'w:styleId="Normal".*?<w:sz w:val="(\d+)"', styles, re.S)
    spec["body_font_pt"] = int(m.group(1)) / 2 if m else None
    m = re.search(r'<w:spacing[^>]*w:line="(\d+)"', doc) or re.search(r'<w:spacing[^>]*w:line="(\d+)"', styles)
    spec["line_multiple"] = round(int(m.group(1)) / 240.0, 2) if m else None
    return spec


def check_docx_spec(checklist, spec):
    """对照 checklist 中 checkable=docx 的条目逐项核对（同一校验器双臂复用）。"""
    out = []
    if spec is None:
        return out
    tol = 0.05
    for it in (checklist.get("items") or []):
        if it.get("checkable") != "docx" or not it.get("numeric"):
            continue
        cat, num = it["category"], it["numeric"]
        applied, ok = None, None
        if cat == "margin" and spec.get("margins_cm"):
            applied = spec["margins_cm"]
            sides = num.get("sides") or (
                {k: num["cm"] for k in ("top", "bottom", "left", "right")} if num.get("cm") else {})
            ok = bool(sides) and all(
                applied.get(s) is not None and abs(applied[s] - v) <= tol for s, v in sides.items())
        elif cat == "columns":
            applied = spec.get("columns")
            ok = applied == num.get("count")
        elif cat == "font_size":
            applied = spec.get("body_font_pt")
            tgt = num.get("pt")
            ok = (applied is not None and tgt is not None and abs(applied - tgt) <= 0.6) if it.get("scope") == "body" else None
            if ok is None:
                continue  # 标题字号差异按 scope 分别核对，缺数据时跳过不硬判
        elif cat == "line_spacing" and spec.get("line_multiple") is not None:
            applied = spec["line_multiple"]
            tgt = num.get("pt") if num.get("unit") == "x" else None
            ok = abs(applied - tgt) <= 0.1 if tgt else None
            if ok is None:
                continue
        else:
            continue
        out.append({"item": "docx_spec", "item_id": it.get("item_id"), "category": cat, "name": it.get("name"),
                    "template_value": it.get("template_value"), "numeric": num,
                    "applied": applied, "match": ok,
                    "source": it.get("source"),
                    "verdict": "pass" if ok else "fail"})
    return out


# ---------------- 主入口（供 CLI 与 gain_evidence 复用） ----------------

ABLATE_DISABLE = ("docx_spec", "caption_format", "heading_numbering")


def run_check(draft_md, checklist, docx_path=None, ablate=False):
    draft, gates, unreadable = "", {}, None
    try:
        draft = open(draft_md, encoding="utf-8").read()
        gates["draft_readable"] = "enforced"
    except Exception as e:
        unreadable = str(e)[:160]
    checklist = checklist if isinstance(checklist, dict) else {}
    results = [check_sections(draft, checklist.get("required_sections") or [])]
    results.append({"item": "heading_numbering", "gate": "skipped_ablation", "verdict": "ablate",
                    "template_value": "章节编号连续且层级不跳变", "applied": None, "match": None,
                    "gate_note": "退化模式：标题编号机检已关闭，本项未运行；下游不得宣称编号已核对。"} if ablate
                   else check_headings(draft))
    results.append({"item": "caption_format", "gate": "skipped_ablation", "verdict": "ablate",
                    "template_value": None, "applied": None, "match": None,
                    "gate_note": "退化模式：题注格式机检已关闭，本项未运行；下游不得宣称题注已核对。"} if ablate
                   else check_captions(draft, checklist))
    results.append(check_xref(draft))
    results.append(check_citations(draft, checklist))
    results.append(check_abstract(draft, checklist))
    docx_results = []
    if docx_path and os.path.exists(docx_path):
        spec = docx_spec(docx_path)
        gates["docx_readable"] = "enforced" if spec is not None else "unreadable"
        if ablate:
            gates["docx_spec"] = "skipped_ablation"
            docx_results.append({"item": "docx_spec", "gate": "skipped_ablation", "verdict": "ablate",
                                 "template_value": "页边距/栏数/字号/行距", "applied": None, "match": None,
                                 "gate_note": "退化模式：docx 排版规格机检已关闭，本项未运行；下游不得宣称排版已核对。"})
        else:
            gates["docx_spec"] = "enforced" if spec else "not_found"
            docx_results = check_docx_spec(checklist, spec)
    else:
        gates["docx_spec"] = "skipped_not_provided"
        if not ablate:
            docx_results.append({"item": "docx_spec", "gate": "skipped_not_provided", "verdict": "warn",
                                 "template_value": "页边距/栏数/字号/行距", "applied": None, "match": None,
                                 "gate_note": "未提供 --docx，排版规格机检未运行；下游不得宣称排版已核对。"})
    results.extend(docx_results)
    if unreadable:
        gates["draft_readable"] = "unreadable"
    fails = [r for r in results if r.get("verdict") == "fail"]
    skipped = [r["item"] for r in results if r.get("gate") in ("skipped_not_provided", "not_found")]
    ablated = [r["item"] for r in results if r.get("gate") == "skipped_ablation"]
    return {"draft": draft_md, "docx": docx_path, "mode": "ablate" if ablate else "full",
            "gates": gates, "results": results, "fail": len(fails),
            "skipped": skipped, "ablated": ablated,
            "verdict": "ablate" if ablate else ("pass" if not fails and not unreadable else "fail"),
            "gate_note": (("存在 skipped 检查项（%s）：未运行不得宣称已核对。" % ",".join(skipped)) if skipped else "")
                         + (("；退化模式关闭的机制（%s）：不得宣称这些项已核对。" % ",".join(ablated)) if ablated else ""),
            "exit_code_policy": "always_zero: 校验失败不阻断交付，verdict 与 fail 计数如实记录在报告内"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--checklist", required=True)
    ap.add_argument("--docx", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--ablate", action="store_true",
                    help="退化/基线模式：关闭 docx 排版规格机检、题注格式机检、标题编号机检（同输入双跑对照）")
    args, err = None, None
    try:
        args = ap.parse_args()
    except SystemExit as e:
        err = e
    if args is None:
        print(json.dumps({"ok": False, "note": "argparse error（非致命，恒 exit 0）", "detail": str(err)}, ensure_ascii=False))
        return 0
    t0 = time.time()
    report = run_check(args.draft, load(args.checklist), args.docx, bool(args.ablate))
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        try:
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as e:
            report["write_error"] = str(e)[:200]
    print(json.dumps({"verdict": report["verdict"], "fail": report["fail"],
                      "items": [(r.get("item") or r.get("name") or "?") + ":" + r.get("verdict", "?")
                                for r in report["results"]]},
                     ensure_ascii=False))
    if _rlog is not None:
        _rlog.log_call("format_check", argv=sys.argv[1:], seconds=time.time() - t0,
                       extra={"ablate": bool(args.ablate), "verdict": report["verdict"], "fail": report["fail"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
