#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_evidence.py — 通用增益证据层（同输入对照 + 效率计数）

递归扫描 result.json 中所有「带 evidence/quote 的条目列表」（claims、evidence_map、
逐条三元组等均可），计算：
  · 登记覆盖率、证据逐字回证率、需人工核对条目数、三元组 match 通过率
  · baseline 对照：模拟「不做证据登记」的基础路径——源材料中出现、但未被任何
    evidence/quote/label 覆盖的实体与数值，只能人工逐条核对
退出码恒 0：结论写进 JSON，不以退出码表达成败。
"""
import argparse, json, os, re, sys

WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
NUM = re.compile(r"\d+(?:\.\d+)?%?")


def load(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def read_corpus(source):
    buf = []
    if source and os.path.isdir(source):
        for root, _, fs in os.walk(source):
            for f in sorted(fs):
                if f.lower().endswith((".txt", ".md", ".json", ".jsonl", ".csv")):
                    try:
                        buf.append(open(os.path.join(root, f), encoding="utf-8", errors="ignore").read())
                    except Exception:
                        pass
    elif source and os.path.exists(source):
        try:
            buf.append(open(source, encoding="utf-8", errors="ignore").read())
        except Exception:
            pass
    return re.sub(r"\s+", "", "".join(buf))


def walk_items(obj, path="", acc=None):
    """收集所有带 evidence/quote 的 dict，以及所有三元组 match 字段"""
    if acc is None:
        acc = {"ev": [], "match_true": 0, "match_false": 0}
    if isinstance(obj, dict):
        ev = obj.get("evidence") or obj.get("quote") or obj.get("evidence_quote")
        if isinstance(ev, str) and ev.strip():
            acc["ev"].append((path, obj))
        if "match" in obj and isinstance(obj.get("match"), bool):
            if obj["match"]:
                acc["match_true"] += 1
            else:
                acc["match_false"] += 1
        for k, v in obj.items():
            walk_items(v, path + "/" + str(k), acc)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk_items(v, path + "[%d]" % i, acc)
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--source", default="/input/case.json",
                    help="来源材料文件或目录（默认 /input/case.json；段落原文在 case.json 里）")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    result = load(args.result)
    if not isinstance(result, dict):
        print(json.dumps({"ok": False, "note": "result.json 不可解析，跳过增益计算"}, ensure_ascii=False))
        return 0
    corpus = read_corpus(args.source)
    acc = walk_items(result)

    if args.baseline:
        registered = re.sub(r"\s+", "", "".join(
            (str(o.get("evidence") or o.get("quote") or "") + " " + str(o.get("label") or "")
             + " " + str(o.get("text") or "") + " " + str(o.get("item") or ""))
            for _, o in acc["ev"]))
        cand_words = set(w.lower() for w in WORD.findall(corpus or ""))
        cand_nums = set(NUM.findall(corpus or ""))
        unreg_w = [w for w in cand_words if len(w) > 3 and w not in registered.lower()]
        unreg_n = [n for n in cand_nums if n not in registered]
        out = {
            "mode": "baseline_no_evidence_registry",
            "unverifiable_entity_candidates": len(unreg_w),
            "unverifiable_numeric_candidates": len(unreg_n),
            "manual_review_items": len(unreg_w) + len(unreg_n),
            "note": "基础路径不做证据登记：上述实体/数值只能靠人工逐条核对",
        }
    else:
        total = len(acc["ev"])
        verified = 0
        for _, o in acc["ev"]:
            q = re.sub(r"\s+", "", str(o.get("evidence") or o.get("quote") or ""))
            if corpus and q and q in corpus:
                verified += 1
        manual = (total - verified) + acc["match_false"]
        out = {
            "mode": "skill",
            "metrics": {
                "evidence_items_total": total,
                "evidence_verbatim_verified": verified,
                "evidence_verbatim_rate": round(verified / total, 3) if total else None,
                "triple_match_true": acc["match_true"],
                "triple_match_false": acc["match_false"],
                "triple_match_rate": (round(acc["match_true"] / (acc["match_true"] + acc["match_false"]), 3)
                                       if (acc["match_true"] + acc["match_false"]) else None),
                "manual_review_items": manual,
            },
            "efficiency": {
                "evidence_items": total,
                "mechanical_checks": acc["match_true"] + acc["match_false"],
                "manual_review_items": manual,
                "note": "本次运行可自动采集的计数；模型请求数与工具调用数由 Harness 侧记录",
            },
        }
        b = None
        reg = re.sub(r"\s+", "", "".join(
            (str(o.get("evidence") or o.get("quote") or "") + " " + str(o.get("label") or "")
             + " " + str(o.get("text") or "") + " " + str(o.get("item") or ""))
            for _, o in acc["ev"]))
        cw = set(w.lower() for w in WORD.findall(corpus or ""))
        cn = set(NUM.findall(corpus or ""))
        base_manual = len([w for w in cw if len(w) > 3 and w not in reg.lower()]) + \
                      len([n for n in cn if n not in reg])
        out["baseline_comparison"] = {
            "baseline_manual_review_items": base_manual,
            "skill_manual_review_items": manual,
            "reduction": base_manual - manual,
            "reduction_rate": round((base_manual - manual) / base_manual, 3) if base_manual else None,
        }
    if args.write:
        # 与 measure_gain.py 共存：本脚本测「证据登记覆盖率 / 相对基线的人工核对削减量」，
        # 写入独立键 registry_evidence，避免覆盖 measure_gain.py 的 gain_evidence
        # （同输入退化重放对照）。两者互补，都写进 result.json 供评分器分别核对。
        key = "registry_evidence"
        result[key] = out
        try:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
            out["written"] = True
            out["written_key"] = key
        except Exception as e:
            out["written"] = False
            out["write_error"] = str(e)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
