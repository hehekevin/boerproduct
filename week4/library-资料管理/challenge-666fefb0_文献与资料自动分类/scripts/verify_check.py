#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（lit-classify 文献与资料自动分类）。

对 result.json 做四类机械校验（与题面机检点逐项对应）：
  A. 体系事前声明与路径命中：taxonomy 必须在任何分类前声明（declared_at + 多级
     dimensions.nodes 含 node_id/path）；每条已判定条目的 primary_path 与 tags
     必须命中体系中的 node_id，体系外路径判 FAIL（防止凭空造类目）。
  B. 引用回证：已判定条目必须有 rationale；primary_path 非空 ⇒ evidence_quote
     非空且逐字回证（空白归一化后子串匹配）于 case.json 该条目的原文
     （title/abstract/keywords 等拼接文本），并在 claims 证据链中有对应条目；
     未回证列入 unbacked_numbers 并判 FAIL。
  C. 同键同类一致性：按 items[].key_signature 独立重算分组，同键条目
     primary_path 不一致 → 必须在 conflicts 登记 merged/escalated；
     escalated 必须进 pending_review。
  D. 边界与待复核登记：judged=false 条目必须有 pending_reason 并登记进
     pending_review（含 reason+needed_action）；boundary 非空的条目同样登记。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
items[].mechanical / consistency 归 classify_engine.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--taxonomy /app/work/taxonomy.json] [--out /app/work/verify_check.json] [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

CONF = ("high", "medium", "low")
BOUNDARY = (None, "none", "multi_domain", "ambiguous", "missing_fields",
            "duplicate", "unreadable")
# 须登记待复核的边界情形（duplicate 若已 merged 处置属确定性动作，不再强制登记）
REG_BOUNDARY = ("multi_domain", "ambiguous", "missing_fields", "unreadable")
TEXT_FIELDS = ("title", "name", "abstract", "summary", "description",
               "keywords", "tags", "authors", "note", "ocr_text")
CANDIDATE_KEYS = ("files", "documents", "records", "items", "materials",
                  "papers", "entries", "literature", "corpus", "results")
ID_KEYS = ("item_id", "file_id", "doc_id", "record_id", "paper_id", "id", "uid")


# ------------------------------------------------------------------ 工具
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化子串匹配口径（保留原大小写以免误伤标识符）。"""
    return re.sub(r"\s+", "", str(s or ""))


def contract_fields(case):
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
        if oc is None:
            return []
        if isinstance(oc, dict):
            for key in ("fields", "required_fields", "result.json", "result"):
                v = oc.get(key)
                if isinstance(v, list):
                    return [str(x) for x in v]
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return []


def node_ids(taxonomy):
    """提取体系中全部 node_id（容错：缺 dimensions 返回空集）。"""
    out = set()
    for dim in (taxonomy or {}).get("dimensions") or []:
        for nd in (dim or {}).get("nodes") or []:
            if isinstance(nd, dict) and nd.get("node_id"):
                out.add(str(nd["node_id"]))
    return out


def _entry_text(entry):
    parts = []
    if isinstance(entry, dict):
        for k in TEXT_FIELDS:
            v = entry.get(k)
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, list):
                parts.extend(str(x) for x in v)
    elif isinstance(entry, str):
        parts.append(entry)
    return "\n".join(parts)


def source_text(case, source_ref, item_id):
    """定位 case.json 中该条目的原文文本（title/abstract 等拼接）。

    优先按 source_ref（形如 files[0]）定位；失败则按 item_id 在候选清单
    常见 id 键中匹配；再失败返回 None（判『无法回证』而非通过）。
    """
    if not isinstance(case, dict):
        return None
    entry = None
    m = re.match(r"^([A-Za-z_]+)\[(\d+)\]$", str(source_ref or ""))
    if m and isinstance(case.get(m.group(1)), list):
        try:
            entry = case[m.group(1)][int(m.group(2))]
        except Exception:
            entry = None
    if entry is None and item_id:
        for key in CANDIDATE_KEYS:
            lst = case.get(key)
            if isinstance(lst, list):
                for e in lst:
                    if isinstance(e, dict) and any(str(e.get(k)) == str(item_id) for k in ID_KEYS if e.get(k)):
                        entry = e
                        break
            if entry is not None:
                break
    if entry is None:
        return None
    return _entry_text(entry)


# ------------------------------------------------------------------ 主分析
def analyze(res, case, ablate="none", case_state="enforced", taxonomy_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("taxonomy", "evidence", "consistency", "pending"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = inner.get("pending_review") or []
    conflicts = inner.get("conflicts") or []
    taxonomy = inner.get("taxonomy") or {}
    cov = inner.get("coverage") or {}
    ids = node_ids(taxonomy)

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "taxonomy_ledger", "state": taxonomy_state,
                            "note": "" if taxonomy_state == "enforced" else "/app/work/taxonomy.json 台账缺失，下游不得宣称已核对"})
    cons_state = "enforced" if (inner.get("consistency") or {}).get("key_groups") else "not_found"
    report["gates"].append({"gate": "consistency_recompute", "state": cons_state,
                            "note": "" if cons_state == "enforced" else "classify_engine.py 未回写 consistency.key_groups，下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, it in enumerate(items):
        iid = it.get("item_id") or "items[%d]" % i
        if it.get("confidence") is not None and it.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r（须 high/medium/low）" % (iid, it.get("confidence")))
        if "boundary" in it and it.get("boundary") not in BOUNDARY:
            report["problems"].append("%s boundary 枚举非法: %r" % (iid, it.get("boundary")))

    # ---- A. 体系事前声明与路径命中 ----
    tax_declared = bool(str(taxonomy.get("declared_at") or "").strip()) and ids
    if not off("taxonomy"):
        if not tax_declared:
            report["problems"].append("taxonomy 未事前声明（declared_at 为空或 dimensions.nodes 无 node_id）；"
                                      "体系必须在任何分类判定前声明且之后禁止调整")
        else:
            add("taxonomy.declared", "declared_at + dimensions.nodes 非空", True, True)
        if tax_declared:
            for i, it in enumerate(items):
                iid = it.get("item_id") or "items[%d]" % i
                pp = it.get("primary_path")
                if not pp:
                    continue
                ok = str(pp) in ids
                add("items[%d].taxonomy_path_hit" % i, "primary_path 命中体系 node_id", True, ok)
                if not ok:
                    report["problems"].append("%s primary_path=%r 不在已声明体系 node_id 中（体系外类目）" % (iid, pp))
                bad_tags = [str(t) for t in (it.get("tags") or []) if str(t) not in ids]
                if bad_tags:
                    report["problems"].append("%s tags 含体系外 node_id: %s" % (iid, bad_tags))

    # ---- B. 引用回证 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        pp = it.get("primary_path")
        if not off("evidence") and it.get("judged") is True and not str(it.get("rationale") or "").strip():
            report["problems"].append("%s 已判定但 rationale 为空（逐条判定须有依据说明）" % iid)
        if not off("evidence") and pp:
            quote = norm(it.get("evidence_quote"))
            src = norm(source_text(case, it.get("source_ref"), iid)) if case_state == "enforced" else ""
            ok_quote = bool(quote) and (bool(src) and quote in src)
            add("items[%d].evidence_verbatim" % i, "evidence_quote 逐字回证 case 原文", True, ok_quote)
            if not ok_quote:
                report["unbacked_numbers"].append(
                    {"item": "items[%d].evidence_quote" % i,
                     "value": str(it.get("evidence_quote") or "")[:60],
                     "reason": "evidence_quote 缺失或未在 case.json 该条目原文中逐字回证"})
            cl = claim_idx.get(iid) or claim_idx.get("items[%d]" % i) or []
            q_backed = any(quote and quote in norm(e.get("quote"))
                           for c in cl for e in (c.get("evidence") or [])) if quote else bool(cl)
            add("items[%d].claims_backed" % i, "claims 证据链含该条目且 quote 对应", True, q_backed)
            if not q_backed:
                report["problems"].append("%s 的分类依据在 claims 证据链中无逐字回证" % iid)

    # ---- C. 同键同类一致性（独立重算） ----
    if not off("consistency"):
        groups = {}
        for i, it in enumerate(items):
            key = str(it.get("key_signature") or "").strip()
            pp = it.get("primary_path")
            if key and pp:
                groups.setdefault(key, []).append((i, str(pp), str(it.get("item_id") or i)))
        for key, members in sorted(groups.items()):
            paths = sorted({p for _i, p, _id in members})
            if len(paths) <= 1:
                for _i, _p, mid in members:
                    add("items[%s].consistency_same_key" % _i, "同键同类", True, True)
                continue
            member_ids = [mid for _i, _p, mid in members]
            rec = [c for c in conflicts if isinstance(c, dict)
                   and set(str(x) for x in (c.get("item_ids") or [])) >= set(member_ids)]
            resolved = bool(rec) and any(str(c.get("resolution")) in ("merged", "escalated") for c in rec)
            for i, _p, _mid in members:
                add("items[%d].consistency_same_key" % i, "同键同类或冲突已登记", True, resolved)
            if not resolved:
                report["problems"].append("同键不同类未登记处置: key=%s items=%s paths=%s（须 conflicts 登记 merged/escalated）"
                                          % (key, member_ids, paths))
            for c in rec:
                if str(c.get("resolution")) == "escalated":
                    for mid in member_ids:
                        if not any(str(p.get("item_id")) == mid for p in pending_reg if isinstance(p, dict)):
                            report["problems"].append("%s 同键冲突 escalated 但未进入 pending_review" % mid)

    # ---- D. 边界与待复核登记 ----
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        boundary = it.get("boundary")
        needs_reg = []
        if it.get("judged") is not True:
            needs_reg.append("未判定条目须 pending_reason 并登记待复核")
        if boundary in REG_BOUNDARY:
            needs_reg.append("边界情形须登记待复核")
        if not needs_reg:
            continue
        if not off("pending"):
            ok_reason = bool(str(it.get("pending_reason") or "").strip()) if it.get("judged") is not True else True
            reg = [p for p in pending_reg if isinstance(p, dict) and str(p.get("item_id")) == iid]
            ok = ok_reason and bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                 and all(str(p.get("needed_action") or "").strip() for p in reg)
            add("items[%d].pending_registered" % i, "未判定/边界 ⇒ 登记入 pending_review", True, ok)
            if not ok:
                report["problems"].append("%s 未判定或边界情形但未登记进 pending_review"
                                          "（缺 pending_reason / reason / needed_action）" % iid)

    # ---- 覆盖面汇总一致性（始终开启） ----
    judged = [it for it in items if it.get("judged") is True]
    classified = [it for it in judged if it.get("primary_path")]
    pend_cnt = sum(1 for it in items if it.get("judged") is not True)
    bnd_cnt = sum(1 for it in items if it.get("boundary") in REG_BOUNDARY)
    ml_cnt = sum(1 for it in items if len(it.get("tags") or []) >= 2)
    if cov:
        exp = {"total_items": len(items), "judged_items": len(judged),
               "classified": len(classified), "pending": pend_cnt,
               "boundary_flagged": bnd_cnt, "multi_label_count": ml_cnt}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "classified" and len(judged) != len(items):
        report["problems"].append("verdict=classified 但存在未判定条目（judged=false）")
    if verdict == "partially_classified" and len(judged) == len(items) == len(classified):
        report["problems"].append("verdict=partially_classified 但全部条目已判定归类（应为 classified）")
    if verdict == "not_classified" and judged:
        report["problems"].append("verdict=not_classified 但存在已判定条目")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")

    # ---- steps（始终开启） ----
    steps = inner.get("steps") or []
    if not steps:
        report["problems"].append("steps 为空（须给出他人可重跑的步骤）")
    elif not any(str(s.get("command") or "").strip() for s in steps if isinstance(s, dict)):
        report["problems"].append("steps 无任何可执行 command")

    # ---- 契约字段（闸门 enforced 时） ----
    if case_state == "enforced":
        for fname in contract_fields(case):
            if isinstance(res, dict) and fname not in res:
                report["problems"].append("缺少 output_contract 字段: %s" % fname)

    if report["unbacked_numbers"]:
        report["problems"].append("存在 %d 条未回证依据（见 unbacked_numbers）" % len(report["unbacked_numbers"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--taxonomy", default="/app/work/taxonomy.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | taxonomy,evidence,consistency,pending 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_numbers/validator_verdict 回写 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        msg = "result.json 不存在或不可解析: %s（不中断交付）" % args.result
        print("[verify_check] FAIL: %s" % msg)
        _dump(args.out, {"verdict": "FAIL", "problems": [msg], "self_check": [],
                         "gates": [], "unbacked_numbers": [], "ablate": args.ablate})
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    tax = load_json(args.taxonomy) if os.path.exists(args.taxonomy) else None
    taxonomy_state = "enforced" if isinstance(tax, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, taxonomy_state=taxonomy_state)
    report["gates"].append({"gate": "classification_output",
                            "state": "enforced" if (res.get("result") or {}).get("consistency") else "not_found",
                            "note": "" if (res.get("result") or {}).get("consistency")
                            else "classify_engine.py 未回写 consistency，下游不得宣称已核对"})
    _dump(args.out, report)

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["self_check"] = report.get("self_check") or []
                cur["gates"] = report.get("gates") or []
                cur["unbacked_numbers"] = report.get("unbacked_numbers") or []
                cur["validator_verdict"] = report.get("verdict")
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(cur, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[verify_check] 回写 result.json 失败: %s" % e)

    if report["verdict"] == "PASS":
        print("[verify_check] PASS（ablate=%s，检查项 %d 条全部 applied）"
              % (args.ablate, len(report["self_check"])))
    else:
        print("[verify_check] FAIL（%d 处，不中断交付；ablate=%s）:"
              % (len(report["problems"]), args.ablate))
        for p in report["problems"][:30]:
            print("  - %s" % p)
        if len(report["problems"]) > 30:
            print("  ... 共 %d 处" % len(report["problems"]))
    return 0


def _dump(out_path, report):
    if not out_path:
        return
    try:
        d = os.path.dirname(out_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
