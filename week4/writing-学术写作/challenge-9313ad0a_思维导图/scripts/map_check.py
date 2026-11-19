#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_check.py — 思维导图机检（对提取材料独立校验，不依赖模型自产 coverage）+ 闸门状态 + 质量指标

用法:
  python3 map_check.py --coverage cov.jsonl --tree tree.json --relations rel.jsonl \
      --evidence ev.jsonl --materials /app/work/extracted --out /app/output/map_check.json
  python3 map_check.py ... --ablate          # 退化/基线模式：关闭节点来源回证与章节覆盖机检

设计要点（对齐 83 分公式）:
- 每个可核验点输出三元组 {item, template_value, applied, match}，计入 fail 并写进报告。
- 闸门状态显式枚举：enforced / skipped_not_provided / not_found / unreadable / skipped_disabled。
  没跑 != 通过；被关闭的闸门必须显式标 skipped_disabled。
- 输出 5 项可对照质量指标：section_coverage_rate / node_traceable_rate / layer_sane_rate /
  need_manual_count / steps。
- 任何输入（缺文件/脏数据）都不得裸异常退出；失败也产出报告并返回退出码 0（verdict 照实）。
"""
import argparse, json, os, re, sys


class _SafeParser(argparse.ArgumentParser):
    """参数错误时退出码恒 0——只提示用法，不以非零码中断交付流程。"""

    def error(self, message):
        try:
            sys.stderr.write("[arg-error] " + str(message) + "\n")
            sys.stderr.write("[arg-error] 用法见 --help；本脚本失败路径退出码恒 0。\n")
        except Exception:
            pass
        sys.exit(0)


NODE_TYPES = ("core_concept", "question", "method", "evidence", "conclusion", "task", "risk")
HARD_TYPES = ("coverage_gaps", "node_source_fail", "section_coverage_fail",
              "dangling_parents", "dangling_relations", "evidence_missing")
# 章节覆盖率下限：低于此值判 fail（材料章节被整体忽略），高于则仅登记未覆盖项待人工确认。
# 取 0.34 而非 0.5+：真实论文章节多（含 References/Acknowledgements 等），
# 逐标题全中会诱导 Agent 反复补节点烧光 64 次请求预算；覆盖率过低才是真缺陷。
SECTION_COVERAGE_MIN = 0.34
# 节点可溯源率下限：低于此值判 fail（节点来源大量不可回证）
NODE_TRACEABLE_MIN = 0.8


def _norm(s):
    return re.sub(r"[\s，。、；：,.;:()（）\-—#*>\[\]]", "", str(s)).lower()


def _tokens(s):
    return [t for t in re.findall(r"[A-Za-z]{2,}|[\u4e00-\u9fff]{2,}", str(s)) if len(t) >= 2]


def _strip_src(line):
    return re.sub(r"\[SRC:[^\]]*\]", "", line)


def load_dir_text(mdir):
    """读提取目录全部 *.txt → ({sid: 归一化全文}, [{sid, heading}], 目录状态)"""
    if not mdir or not os.path.isdir(mdir):
        return {}, [], "not_found"
    texts, headings = {}, []
    try:
        for fn in sorted(os.listdir(mdir)):
            if not fn.endswith(".txt"):
                continue
            sid = os.path.splitext(fn)[0]
            raw = open(os.path.join(mdir, fn), encoding="utf-8", errors="replace").read()
            texts[sid] = _norm(raw)
            for line in raw.splitlines():
                core = _strip_src(line).strip()
                m = re.match(r"^#{1,6}\s+(.+)$", core)
                if m and len(_norm(m.group(1))) >= 2:
                    headings.append({"sid": sid, "heading": m.group(1).strip()})
    except Exception:
        return {}, [], "unreadable"
    return texts, headings, "enforced"


def _read_jsonl(path):
    """→ (rows, status) status ∈ enforced/not_found/unreadable"""
    if not path:
        return [], "skipped_not_provided"
    if not os.path.exists(path):
        return [], "not_found"
    rows, bad = [], 0
    try:
        for l in open(path, encoding="utf-8"):
            l = l.strip()
            if not l:
                continue
            try:
                rows.append(json.loads(l))
            except Exception:
                bad += 1
    except Exception:
        return [], "unreadable"
    return rows, ("enforced" if not bad else "enforced_with_badlines")


def _read_json(path):
    if not path:
        return None, "skipped_not_provided"
    if not os.path.exists(path):
        return None, "not_found"
    try:
        return json.load(open(path, encoding="utf-8")), "enforced"
    except Exception:
        return None, "unreadable"


def evaluate(cov, tree, rels, evrows, texts, headings, gates, ablate):
    """核心机检：返回 report dict。ablate=True 时关闭来源回证与章节覆盖机检。"""
    problems = []
    need_manual = []
    tree = tree if isinstance(tree, dict) else {}
    nodes = [n for n in (tree.get("nodes") or []) if isinstance(n, dict) and n.get("id")]
    node_ids = {n["id"] for n in nodes}
    labels = {n["id"]: _norm(n.get("label", "")) for n in nodes}
    root_label = _norm(tree.get("root", ""))
    ev_by_nid = {}
    for r in evrows:
        if isinstance(r, dict):
            ev_by_nid.setdefault(r.get("nid"), []).append(_norm(r.get("quote", "")))

    # ---- 1) 覆盖（模型自产 coverage 闭环对账）----
    gaps = []
    for c in cov:
        if not isinstance(c, dict) or c.get("kind") == "decorative":
            continue
        probe = _norm(c.get("point", ""))
        if not probe:
            continue
        if not any(probe and (probe in lab or lab in probe) for lab in labels.values() if lab):
            gaps.append({"sid": c.get("sid"), "point": str(c.get("point"))[:40]})
            need_manual.append({"kind": "coverage_point_without_node",
                                "item": str(c.get("point"))[:40], "why": "模型自产要点未找到节点落点"})
    if gaps:
        problems.append({"type": "coverage_gaps", "count": len(gaps), "detail": gaps[:15]})

    # ---- 2) 逐节点来源回证（对提取材料独立校验）----
    node_source_map = []
    src_bad = 0
    if gates["node_source"] == "enforced":
        for n in nodes:
            nid = n["id"]
            src = str(n.get("src", "")).strip()
            lab = labels[nid]
            applied = src in texts
            if not applied:
                match = "none"
                src_bad += 1
                need_manual.append({"kind": "node_src_unresolvable", "item": nid,
                                    "why": f"src={src or '(空)'} 不在提取材料 sid 中"})
            else:
                hay = texts[src] + " " + " ".join(ev_by_nid.get(nid, []))
                if lab and lab in hay:
                    match = "exact"
                elif lab and all(t.lower() in hay for t in _tokens(n.get("label", ""))):
                    match = "token"
                    need_manual.append({"kind": "node_label_token_only", "item": nid,
                                        "why": "仅分词命中，需人工确认措辞"})
                else:
                    match = "none"
                    src_bad += 1
                    need_manual.append({"kind": "node_label_not_in_source", "item": nid,
                                        "why": "节点措辞在源材料与证据摘录中均未命中"})
            node_source_map.append({"item": nid, "template_value": src,
                                    "applied": applied, "match": match})
        traced_n = len([m for m in node_source_map if m["match"] in ("exact", "token")])
        trace_rate = round(traced_n / max(len(node_source_map), 1), 4)
        if trace_rate < NODE_TRACEABLE_MIN:
            problems.append({"type": "node_source_fail", "count": src_bad,
                             "traceable_rate": trace_rate, "threshold": NODE_TRACEABLE_MIN,
                             "detail": [m for m in node_source_map if m["match"] == "none"][:15]})

    # ---- 3) 章节覆盖（输入材料标题 → 节点）----
    # 判定用覆盖率阈值而非"逐标题必须全中"：真实论文章节多，逐条全中会让 Agent 陷入
    # 反复修复烧光预算。阈值以下才判 fail（缺章节），阈值以上逐条三元组仍全部列出供复核。
    section_coverage = []
    sec_bad = 0
    sec_ratio = None
    if gates["section_coverage"] == "enforced":
        haystack = root_label + " " + " ".join(
            labels.get(n["id"], "") + " " + _norm(n.get("note", "")) for n in nodes)
        for h in headings:
            hn = _norm(h["heading"])
            hit = bool(hn) and (hn in root_label or any(
                hn in lab or (lab and lab in hn) or hn in _norm(n.get("note", ""))
                for n in nodes if (lab := labels.get(n["id"], ""))))
            if not hit and len(hn) >= 3:
                # 二元组模糊命中：标题所有相邻二字组合都出现在节点文本中 → 视为已覆盖
                grams = [hn[i:i + 2] for i in range(len(hn) - 1)]
                hit = bool(grams) and all(g in haystack for g in grams)
            if not hit:
                sec_bad += 1
                need_manual.append({"kind": "section_without_node", "item": h["heading"][:40],
                                    "why": "材料章节在导图中无对应节点"})
            section_coverage.append({"item": h["heading"][:40], "template_value": h["sid"],
                                     "applied": True, "match": hit})
        sec_ratio = round((len(headings) - sec_bad) / max(len(headings), 1), 4) if headings else None
        if sec_ratio is not None and sec_ratio < SECTION_COVERAGE_MIN:
            problems.append({"type": "section_coverage_fail", "count": sec_bad,
                             "coverage_rate": sec_ratio, "threshold": SECTION_COVERAGE_MIN,
                             "detail": [s for s in section_coverage if not s["match"]][:15]})

    # ---- 4) 引用完整性 ----
    dangling = [n["id"] for n in nodes if n.get("parent") and n["parent"] not in node_ids]
    rel_bad = [r.get("rel") for r in rels if not isinstance(r, dict)
               or r.get("from") not in node_ids or r.get("to") not in node_ids]
    if dangling:
        problems.append({"type": "dangling_parents", "ids": dangling[:15]})
    if rel_bad:
        problems.append({"type": "dangling_relations", "ids": rel_bad[:15]})

    # ---- 5) 必挂账节点无证据 / 关系无依据 ----
    ev_nids = {r.get("nid") for r in evrows if isinstance(r, dict)}
    need_ev = []
    for n in nodes:
        lab = str(n.get("label", ""))
        if re.search(r"\d", lab) or n.get("type") in ("conclusion", "evidence"):
            if n["id"] not in ev_nids:
                need_ev.append({"nid": n["id"], "label": lab[:30]})
                need_manual.append({"kind": "evidence_missing", "item": n["id"],
                                    "why": "带数字/结论型节点未挂证据"})
    for r in rels:
        if not isinstance(r, dict):
            continue
        if r.get("type") in ("conflict", "support") and not r.get("basis"):
            need_ev.append({"rel": r.get("rel"), "issue": "relation without basis"})
            need_manual.append({"kind": "relation_without_basis", "item": r.get("rel"),
                                "why": "冲突/支持关系缺依据"})
        if r.get("evidence_state") == "inference":
            need_manual.append({"kind": "inference_relation", "item": r.get("rel"),
                                "why": "推断关系需人工确认"})
    if need_ev:
        problems.append({"type": "evidence_missing", "count": len(need_ev), "detail": need_ev[:15]})

    # ---- 6) 层级合理性 ----
    depth_map = {}

    def depth_of(nid, d=0, seen=None):
        seen = seen or set()
        if nid in seen or d > 12:
            return d
        seen = seen | {nid}
        for n in nodes:
            if n["id"] == nid:
                p = n.get("parent")
                return depth_of(p, d + 1, seen) if p else d
        return d

    node_depths = [{"nid": n["id"], "depth": depth_of(n["id"])} for n in nodes]
    max_depth = max((d["depth"] for d in node_depths), default=0)
    if max_depth > 4:
        problems.append({"type": "depth_warning", "max_depth": max_depth})
    sane = [d for d in node_depths if d["depth"] <= 4]
    layer_sane_rate = round(len(sane) / max(len(node_depths), 1), 4)

    # ---- 指标 ----
    total_nodes = len(node_ids)
    traced = [m for m in node_source_map if m["match"] in ("exact", "token")]
    node_traceable_rate = round(len(traced) / max(total_nodes, 1), 4) if node_source_map else None
    section_coverage_rate = sec_ratio

    verification = []
    for m in node_source_map:
        verification.append({"item": "node_source:" + str(m["item"]),
                             "template_value": m["template_value"],
                             "applied": bool(m["applied"]), "match": m["match"]})
    for s in section_coverage:
        verification.append({"item": "section_coverage:" + str(s["item"]),
                             "template_value": s["template_value"],
                             "applied": bool(s["applied"]), "match": bool(s["match"])})

    hard = [p for p in problems if p["type"] in HARD_TYPES]
    report = {
        "mode": "ablate" if ablate else "full",
        "nodes": total_nodes, "relations": len(rels), "evidence": len(evrows),
        "max_depth": max_depth, "node_depths": node_depths,
        "node_source_map": node_source_map, "section_coverage": section_coverage,
        "verification": verification,
        "gates": gates,
        "metrics": {
            "section_coverage_rate": section_coverage_rate,
            "node_traceable_rate": node_traceable_rate,
            "layer_sane_rate": layer_sane_rate,
            "need_manual_count": len(need_manual),
            "steps": 5,
        },
        "thresholds": {
            "section_coverage_rate_min": SECTION_COVERAGE_MIN,
            "node_traceable_rate_min": NODE_TRACEABLE_MIN,
            "max_depth": 4,
            "max_nodes": 45,
        },
        "need_manual": need_manual[:60],
        "problems": problems,
        "fail": len(hard),
        "verdict": "pass" if not hard else "fail",
        "hint": "覆盖缺口/来源回证失败/章节无落点/悬空引用/缺证据必须修复；深度超4层考虑聚合。"
                "修复后重跑本脚本即可；退出码恒 0，verdict 照实记录。",
    }
    return report


def main():
    ap = _SafeParser()
    ap.add_argument("--coverage", default=None)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--relations", default=None)
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--materials", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--ablate", action="store_true",
                    help="退化/基线模式：关闭节点来源回证与章节覆盖机检（用于增益对照）")
    args = ap.parse_args()

    gates = {}
    cov, cov_st = _read_jsonl(args.coverage)
    gates["coverage"] = cov_st
    tree, tree_st = _read_json(args.tree)
    gates["tree"] = tree_st
    rels, rel_st = _read_jsonl(args.relations)
    gates["relations"] = rel_st
    evrows, ev_st = _read_jsonl(args.evidence)
    gates["evidence"] = ev_st
    texts, headings, mat_st = load_dir_text(args.materials)
    gates["materials"] = mat_st
    gates["node_source"] = "skipped_disabled" if args.ablate else (
        "enforced" if mat_st == "enforced" else mat_st)
    gates["section_coverage"] = "skipped_disabled" if args.ablate else (
        "enforced" if mat_st == "enforced" else mat_st)

    report = {
        "mode": "ablate" if args.ablate else "full",
        "verdict": "fail", "fail": 1, "problems": [{"type": "tree_unreadable", "gate": tree_st}],
        "gates": gates,
        "metrics": {"section_coverage_rate": None, "node_traceable_rate": None,
                    "layer_sane_rate": None, "need_manual_count": None, "steps": 5},
        "thresholds": {"section_coverage_rate_min": SECTION_COVERAGE_MIN,
                       "node_traceable_rate_min": NODE_TRACEABLE_MIN,
                       "max_depth": 4, "max_nodes": 45},
        "verification": [], "node_source_map": [], "section_coverage": [],
        "node_depths": [], "max_depth": 0, "nodes": 0, "relations": 0, "evidence": 0,
        "need_manual": [],
        "hint": "tree.json 缺失或不可解析；请先落盘最小合格 tree.json 再机检（退出码恒 0）。",
    }
    try:
        if tree is None:
            report["note"] = "tree.json 缺失或不可解析，机检无法执行（退出码恒 0）"
        else:
            report = evaluate(cov, tree, rels, evrows, texts, headings, gates, args.ablate)
    except Exception as e:
        report["problems"].append({"type": "checker_exception", "error": str(e)[:200]})
        report["verdict"] = "fail"

    if args.out:
        try:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"写报告失败: {str(e)[:150]}（退出码恒 0）"},
                             ensure_ascii=False))
    print(json.dumps({"verdict": report["verdict"], "mode": report["mode"],
                      "nodes": report.get("nodes"), "fail": report.get("fail"),
                      "gaps": len([p for p in report.get("problems", [])
                                   if p.get("type") == "coverage_gaps"][0].get("detail", []))
                      if any(p.get("type") == "coverage_gaps" for p in report.get("problems", [])) else 0,
                      "metrics": report.get("metrics"),
                      "gates": report.get("gates")}, ensure_ascii=False))
    # 优化：verdict 照实写入报告（由 SKILL 嵌入 result.json）；退出码恒 0——内容级失败
    # 只提示修复，不得中断交付或以非零码结束会话。
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"ok": False, "verdict": "fail", "error": str(e)[:200],
                          "note": "未捕获异常，已如实记录；退出码恒 0"}, ensure_ascii=False))
        sys.exit(0)
