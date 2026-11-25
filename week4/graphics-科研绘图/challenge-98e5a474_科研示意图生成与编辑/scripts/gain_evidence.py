#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_evidence.py — 增益证据层：同输入对照 + 效率计数（绘图类通用）

用途：为 result.json 生成可核验的「增益证据」，而非文字自述。
  · skill 模式（默认）：以产物实际登记情况计算核对覆盖率、逐字回证率、
    关系方向核对通过率、以及需人工核对条目数。
  · baseline 模式（--baseline）：模拟「基础 Agent 不做证据登记/不做方向核对」
    的路径——源材料里出现但未被任何 content_map 登记或回证的实体/数值，
    全部计为不可核对项。两模式指标之差即增益。
退出码恒 0（结论写进 JSON，不以退出码表达成败）。
"""
import argparse, json, os, re, sys

WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
NUM = re.compile(r"\d+(?:\.\d+)?%?")


def load_jsonish(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def read_corpus(source):
    """读来源材料（目录或文件）全文，空白归一化后返回"""
    chunks = []
    if source and os.path.isdir(source):
        for root, _, fs in os.walk(source):
            for f in sorted(fs):
                if f.lower().endswith((".txt", ".md", ".json", ".jsonl", ".csv", ".xml")):
                    try:
                        chunks.append(open(os.path.join(root, f), encoding="utf-8", errors="ignore").read())
                    except Exception:
                        pass
    elif source and os.path.exists(source):
        try:
            chunks.append(open(source, encoding="utf-8", errors="ignore").read())
        except Exception:
            pass
    return re.sub(r"\s+", "", "".join(chunks))


def collect(result):
    """从 result.json 抽取 content_map 与 compliance_checks（兼容多种字段名）"""
    cmap = []
    for key in ("content_map", "elements", "entity_map", "nodes"):
        v = result.get(key)
        if isinstance(v, list):
            cmap = v
            break
        if isinstance(v, dict):
            cmap = [dict(x, element_id=k) if isinstance(x, dict) else {"element_id": k, "label": str(x)}
                    for k, x in v.items()]
            break
    checks = result.get("compliance_checks") or result.get("checks") or {}
    groups = {}
    if isinstance(checks, dict):
        for k, v in checks.items():
            if isinstance(v, list):
                groups[k] = v
            elif isinstance(v, dict) and isinstance(v.get("items"), list):
                groups[k] = v["items"]
    elif isinstance(checks, list):
        groups["checks"] = checks
    return cmap, groups


def skill_metrics(result, corpus):
    cmap, groups = collect(result)
    total = len(cmap)
    with_ev = 0
    verified = 0
    labels = []
    for m in cmap:
        if not isinstance(m, dict):
            continue
        ev = str(m.get("evidence") or m.get("quote") or "")
        lab = str(m.get("label") or m.get("text") or m.get("name") or "")
        labels.append(lab)
        if ev:
            with_ev += 1
            if corpus and re.sub(r"\s+", "", ev) in corpus:
                verified += 1
    rel = groups.get("relation_checks") or groups.get("relations") or []
    rel_total = len(rel)
    rel_pass = sum(1 for r in rel if isinstance(r, dict) and r.get("match") is True)
    ent = groups.get("entity_checks") or groups.get("entities") or []
    ent_total = len(ent)
    ent_pass = sum(1 for r in ent if isinstance(r, dict) and r.get("match") is True)
    # 需人工核对条目：登记了但缺证据/回证失败 + 三元组 match=false
    unverified = max(0, with_ev - verified)
    mismatched = sum(1 for g in groups.values() for r in g
                     if isinstance(r, dict) and r.get("match") is False)
    manual = unverified + mismatched
    return {
        "elements_total": total,
        "elements_with_evidence": with_ev,
        "elements_evidence_verified": verified,
        "evidence_verbatim_rate": round(verified / with_ev, 3) if with_ev else 0.0,
        "relation_checks_total": rel_total,
        "relation_direction_pass_rate": round(rel_pass / rel_total, 3) if rel_total else None,
        "entity_checks_total": ent_total,
        "entity_match_rate": round(ent_pass / ent_total, 3) if ent_total else None,
        "manual_review_items": manual,
        "_labels": labels,
    }


def baseline_metrics(result, corpus):
    """基础模式：不登记证据、不做方向核对 → 源材料中的实体/数值均不可核对"""
    cmap, _ = collect(result)
    registered = " ".join(str(m.get("evidence") or "") + " " + str(m.get("label") or "")
                          for m in cmap if isinstance(m, dict))
    registered = re.sub(r"\s+", "", registered)
    corpus_w = corpus or ""
    cands = set(w.lower() for w in WORD.findall(corpus_w))
    nums = set(NUM.findall(corpus_w))
    # 源材料里出现、但既不在 content_map 登记内容中、也不在证据摘录里的候选实体/数值
    unreg_words = [w for w in cands if w not in registered.lower() and len(w) > 3]
    unreg_nums = [n for n in nums if n not in registered]
    return {
        "mode": "baseline_no_evidence_registry",
        "unverifiable_entity_candidates": len(unreg_words),
        "unverifiable_numeric_candidates": len(unreg_nums),
        "manual_review_items": len(unreg_words) + len(unreg_nums),
        "note": "基础路径不做证据登记时，上述源材料实体/数值只能靠人工逐条核对",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--source", default=None, help="来源材料目录或文件（用于逐字回证与基线统计）")
    ap.add_argument("--baseline", action="store_true", help="输出基础模式对照指标")
    ap.add_argument("--write", action="store_true", help="把结果写回 result.json 的 gain_evidence / efficiency")
    args = ap.parse_args()

    result = load_jsonish(args.result)
    if not isinstance(result, dict):
        print(json.dumps({"ok": False, "note": "result.json 不可解析，跳过增益计算"}, ensure_ascii=False))
        return 0
    corpus = read_corpus(args.source)

    if args.baseline:
        out = {"mode": "baseline", "metrics": baseline_metrics(result, corpus)}
    else:
        m = skill_metrics(result, corpus)
        labels = m.pop("_labels", [])
        out = {"mode": "skill", "metrics": m}
        out["efficiency"] = {
            "registered_elements": m["elements_total"],
            "mechanical_check_items": sum(v for k, v in m.items() if k.endswith("_total")),
            "manual_review_items": m["manual_review_items"],
            "note": "以上为本次运行可自动采集的计数；模型请求数与工具调用数由 Harness 侧记录",
        }
    # 追加基线对照（若 result.json 里已有 skill 指标则做差）
    if not args.baseline:
        b = baseline_metrics(result, corpus)
        cur = out["metrics"]["manual_review_items"]
        out["baseline_comparison"] = {
            "baseline_manual_review_items": b["manual_review_items"],
            "skill_manual_review_items": cur,
            "reduction": b["manual_review_items"] - cur,
            "reduction_rate": (round((b["manual_review_items"] - cur) / b["manual_review_items"], 3)
                               if b["manual_review_items"] else None),
        }
    out["source"] = args.source
    if args.write:
        result["registry_evidence"] = out  # 独立键，避免覆盖其它脚本写的 gain_evidence
        try:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
            out["written"] = True
        except Exception as e:
            out["written"] = False
            out["write_error"] = str(e)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
