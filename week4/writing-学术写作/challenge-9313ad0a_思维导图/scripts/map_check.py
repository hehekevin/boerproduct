#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_check.py — 思维导图校验
检查: 1) 覆盖（非装饰要点有节点落点）；2) 引用完整性（parent/from/to 存在）；
3) 必挂账节点无证据=fail；4) 层级深度 ≤4（超过 warn）。
"""
import argparse, json, os, re, sys

def _norm(s):
    return re.sub(r"[\s，。、；：,.;:()（）\-—]", "", str(s))[:14]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", required=True)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--relations", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cov = [json.loads(l) for l in open(args.coverage, encoding="utf-8") if l.strip()]
    tree = json.load(open(args.tree, encoding="utf-8"))
    rels = [json.loads(l) for l in open(args.relations, encoding="utf-8") if l.strip()]
    evrows = [json.loads(l) for l in open(args.evidence, encoding="utf-8") if l.strip()]
    problems = []

    node_ids = {n["id"] for n in tree.get("nodes", [])}
    labels = {n["id"]: _norm(n.get("label")) for n in tree.get("nodes", [])}
    # 1) 覆盖
    gaps = []
    for c in cov:
        if c.get("kind") == "decorative":
            continue
        probe = _norm(c.get("point"))
        if not probe:
            continue
        hit = any(probe and (probe in lab or lab in probe) for lab in labels.values() if lab)
        if not hit:
            gaps.append({"sid": c.get("sid"), "point": str(c.get("point"))[:40]})
    if gaps:
        problems.append({"type": "coverage_gaps", "count": len(gaps), "detail": gaps[:15]})

    # 2) 引用完整性
    dangling = [n["id"] for n in tree.get("nodes", []) if n.get("parent") and n["parent"] not in node_ids]
    rel_bad = [r.get("rel") for r in rels if r.get("from") not in node_ids or r.get("to") not in node_ids]
    if dangling:
        problems.append({"type": "dangling_parents", "ids": dangling[:15]})
    if rel_bad:
        problems.append({"type": "dangling_relations", "ids": rel_bad[:15]})

    # 3) 必挂账节点无证据
    ev_nids = {r.get("nid") for r in evrows}
    need_ev = []
    for n in tree.get("nodes", []):
        lab = str(n.get("label", ""))
        if re.search(r"\d", lab) or n.get("type") in ("conclusion", "evidence"):
            if n["id"] not in ev_nids:
                need_ev.append({"nid": n["id"], "label": lab[:30]})
    for r in rels:
        if r.get("type") in ("conflict", "support") and not r.get("basis"):
            need_ev.append({"rel": r.get("rel"), "issue": "relation without basis"})
    if need_ev:
        problems.append({"type": "evidence_missing", "count": len(need_ev), "detail": need_ev[:15]})

    # 4) 层级深度
    depth_map = {}
    def depth_of(nid, d=0):
        for n in tree.get("nodes", []):
            if n["id"] == nid:
                p = n.get("parent")
                return depth_of(p, d + 1) if p else d
        return d
    max_depth = max((depth_of(n["id"]) for n in tree.get("nodes", [])), default=0)
    warn = max_depth > 4
    if warn:
        problems.append({"type": "depth_warning", "max_depth": max_depth})

    hard = [p for p in problems if p["type"] in ("coverage_gaps", "dangling_parents",
                                                  "dangling_relations", "evidence_missing")]
    report = {"nodes": len(node_ids), "relations": len(rels), "evidence": len(evrows),
              "max_depth": max_depth, "problems": problems, "fail": len(hard),
              "verdict": "pass" if not hard else "fail",
              "hint": "覆盖缺口/悬空引用/缺证据必须修复；深度超4层考虑聚合。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "nodes": len(node_ids),
                      "gaps": len(gaps)}, ensure_ascii=False))
    return 1 if hard else 0

if __name__ == "__main__":
    sys.exit(main())
