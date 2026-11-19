#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（开题报告赛道统一收尾）
把 case_id、output_contract 原字段、主产物全文（内嵌）、证据映射、检查报告、增益取证、
效率计数、状态与不确定性组装成 /app/output/result.json。已有骨架时只回填不覆盖。

用法:
  python3 build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact proposal.docx --artifact-md proposal.md \
      --embed-file /app/output/proposal.md --embed-key deliverable_content \
      --evidence /app/work/plan.jsonl --fact-check /app/output/fact_check.json \
      --consistency /app/output/plan_check.json --seven-check /app/output/seven_check.json \
      --gain-evidence /app/output/gain_evidence.json \
      --route /app/work/route.jsonl --milestones /app/work/milestones.jsonl \
      --risks /app/work/risk_table.jsonl --ledger /app/work/fact_ledger.jsonl \
      --render /app/output/previews/render_log.json \
      --status complete --notes '[待核条目...]' --changelog '取舍记录'

语义回填: output_contract 的每个键按键名语义自动填入对应产物（proposal_md→正文全文、
seven_elements_checklist→七要素逐条、milestone_plan→里程碑、risk_table→风险表、
source_mapping→来源台账、uncertainty→不确定性…），键不缺失且值不为空。

容错: case.json/各报告缺失或损坏时降级组装，绝不崩溃；status 仅接受
complete/partial/failed/blocked 四级，越界值降级为 partial 并登记。
退出码恒为 0（verdict/ok 如实记录在末尾自检 JSON），脚本不中断交付链。
"""
import argparse, json, os, re, sys

STATUSES = ("complete", "partial", "failed", "blocked")
MAX_LEDGER_ENTRIES = 400


def load_jsonish(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        try:
            return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        except Exception:
            return {"raw_path": p}


def load_lines(p):
    rows = []
    if not p or not os.path.exists(p):
        return rows
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return rows


def contract_keys(contract):
    """从 output_contract 提取字段名列表；兼容 list[str]/list[dict]/dict 多种形态。"""
    keys = []
    try:
        if isinstance(contract, list):
            for k in contract:
                if isinstance(k, str):
                    keys.append(k)
                elif isinstance(k, dict):
                    for f in ("name", "key", "field", "id"):
                        if k.get(f):
                            keys.append(k[f])
                            break
        elif isinstance(contract, dict):
            hit = False
            for f in ("fields", "required", "keys", "properties"):
                v = contract.get(f)
                if isinstance(v, list) and v:
                    for k in v:
                        if isinstance(k, str):
                            keys.append(k)
                        elif isinstance(k, dict):
                            for ff in ("name", "key", "field", "id"):
                                if k.get(ff):
                                    keys.append(k[ff])
                                    break
                    hit = bool(keys)
                    break
                if isinstance(v, dict) and v:
                    keys.extend(list(v.keys()))
                    hit = True
                    break
            if not hit:
                keys = [k for k in contract.keys()
                        if k not in ("description", "note", "notes", "contract_version")]
    except Exception:
        pass
    seen, out = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def as_list(s):
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else [str(v)]
    except Exception:
        return [x.strip() for x in s.split(";") if x.strip()]


# ---- 键名语义映射：契约键 → 产物来源 ----------------------------------------
# 顺序即优先级；同一产物可命中多个键（如 source_mapping 与 references 区分）。
SEMANTIC_RULES = [
    ("gain", "gain_evidence"),
    ("efficiency", "efficiency"),
    ("seven_element", "seven_elements"),
    ("checklist", "seven_elements"),
    ("element", "seven_elements"),
    ("要素", "seven_elements"),
    ("route", "technical_route"),
    ("技术路线", "technical_route"),
    ("method", "technical_route"),
    ("milestone", "milestone_plan"),
    ("timeline", "milestone_plan"),
    ("schedule", "milestone_plan"),
    ("阶段计划", "milestone_plan"),
    ("进度", "milestone_plan"),
    ("risk", "risk_table"),
    ("风险", "risk_table"),
    ("alignment", "question_goal_alignment"),
    ("question", "question_goal_alignment"),
    ("goal", "question_goal_alignment"),
    ("目标", "question_goal_alignment"),
    ("问题", "question_goal_alignment"),
    ("innovation", "innovation_points"),
    ("创新", "innovation_points"),
    ("reference", "references"),
    ("bibliograph", "references"),
    ("文献", "references"),
    ("source", "source_mapping"),
    ("mapping", "source_mapping"),
    ("evidence", "source_mapping"),
    ("citation", "source_mapping"),
    ("来源", "source_mapping"),
    ("uncertain", "uncertainty"),
    ("boundary", "version_and_boundary"),
    ("version", "version_and_boundary"),
    ("gap", "material_gaps"),
    ("缺口", "material_gaps"),
    ("status", "status"),
    ("状态", "status"),
    ("proposal", "deliverable_content"),
    ("markdown", "deliverable_content"),
    ("full_text", "deliverable_content"),
    ("正文", "deliverable_content"),
    ("content", "deliverable_content"),
    ("md", "deliverable_content"),
]


def pick_semantic(key, artifacts):
    """按键名语义返回应填入契约键的产物值；无匹配返回 None。"""
    low = str(key).lower()
    for token, name in SEMANTIC_RULES:
        if token in low:
            val = artifacts.get(name)
            if val not in (None, "", [], {}):
                return val
    return None


def extract_references(text):
    """从 proposal.md 抽取参考文献条目（## 参考文献 之后的非空行）。"""
    refs, in_refs = [], False
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            in_refs = ("参考文献" in s or "references" in s.lower())
            continue
        if in_refs and s:
            refs.append(s)
    return refs


def extract_innovation(text):
    """从正文抽取创新点相关行（仅登记原文行，不改写）。"""
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if s and ("创新点" in s or "创新性" in s or "创新" in s):
            out.append(s)
    return out[:40]


def seven_elements_manifest(seven_report):
    """从 seven_check 报告整理七要素逐条清单（含定位与核验状态）。"""
    if not isinstance(seven_report, dict):
        return []
    items = []
    for c in seven_report.get("checks", []) or []:
        if not isinstance(c, dict):
            continue
        if not str(c.get("check", "")).startswith(("A_section", "B_route", "C_timeline")):
            continue
        items.append({
            "check": c.get("check"),
            "item": c.get("item"),
            "expected": c.get("expected"),
            "applied": c.get("applied"),
            "match": c.get("match"),
            "location": c.get("location"),
            "reason": c.get("reason"),
        })
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--artifact-md", default=None)
    ap.add_argument("--embed-file", default=None,
                    help="主产物全文文件（md/txt），内容作为字符串写入 --embed-key 字段")
    ap.add_argument("--embed-key", default="deliverable_content")
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--seven-check", dest="seven_check", default=None,
                    help="seven_check.json（章节完整性/路线可执行/时间表一致性）")
    ap.add_argument("--gain-evidence", dest="gain_evidence", default=None,
                    help="gain_evidence.json（同输入双跑对照的真实运行证据）")
    ap.add_argument("--efficiency", default=None, help="efficiency.json（效率计数）")
    ap.add_argument("--render", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--route", default=None, help="route.jsonl 技术路线步骤")
    ap.add_argument("--milestones", default=None, help="milestones.jsonl 阶段计划")
    ap.add_argument("--risks", default=None, help="risk_table.jsonl 风险表")
    ap.add_argument("--plan", default=None, help="plan.jsonl 问题-目标对齐表")
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[],
                    help="--set key=value 直接回填 output_contract 字段")
    args = ap.parse_args()

    notes = list(as_list(args.notes) or [])
    status = args.status if args.status in STATUSES else "partial"
    if status != args.status:
        notes.append("status '%s' 不在四级诚实状态内，已降级为 partial" % args.status)

    case = load_jsonish(args.case) or {}
    if not isinstance(case, dict):
        case = {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), (dict, list)) else {}
    key_list = contract_keys(contract)

    result_path = args.out
    old = load_jsonish(result_path) if os.path.exists(result_path) else None
    result = old if isinstance(old, dict) else {}

    result.setdefault("case_id", case_id)

    # ---- 载入各产物 --------------------------------------------------
    seven_report = load_jsonish(args.seven_check) if args.seven_check else None
    plan_report = load_jsonish(args.consistency) if args.consistency else None
    fact_report = load_jsonish(args.fact_check) if args.fact_check else None
    gain_report = load_jsonish(args.gain_evidence) if args.gain_evidence else None
    eff_report = load_jsonish(args.efficiency) if args.efficiency else None
    render_report = load_jsonish(args.render) if args.render else None
    ledger_rows = load_lines(args.ledger) if args.ledger else []
    route_rows = load_lines(args.route) if args.route else []
    ms_rows = load_lines(args.milestones) if args.milestones else []
    risk_rows = load_lines(args.risks) if args.risks else []
    plan_rows = load_lines(args.plan) if args.plan else load_lines(args.evidence)

    # ---- 主产物全文内嵌 ----------------------------------------------
    embed_chars = 0
    embed_text = ""
    if args.embed_file:
        try:
            embed_text = open(args.embed_file, encoding="utf-8", errors="ignore").read()
            if embed_text.strip():
                result[args.embed_key] = embed_text
                embed_chars = len(embed_text)
            else:
                notes.append("embed 文件为空: %s" % args.embed_file)
        except Exception as e:
            notes.append("embed 读取失败 %s: %s" % (args.embed_file, str(e)[:120]))
        result.setdefault(args.embed_key, None)

    refs = extract_references(embed_text)
    innovation = extract_innovation(embed_text)

    artifacts = {
        "deliverable_content": embed_text if embed_chars else None,
        "seven_elements": seven_elements_manifest(seven_report),
        "technical_route": route_rows,
        "milestone_plan": ms_rows,
        "risk_table": risk_rows,
        "question_goal_alignment": plan_rows,
        "innovation_points": innovation,
        "references": refs,
        "source_mapping": ledger_rows[:MAX_LEDGER_ENTRIES],
        "uncertainty": None,      # 延迟填充（依赖下方合并后的 uncertainty）
        "version_and_boundary": None,
        "material_gaps": None,
        "gain_evidence": gain_report,
        "efficiency": eff_report,
        "status": status,
    }

    # ---- 证据/检查报告直接落位 ----------------------------------------
    if args.artifact:
        result["deliverable"] = {"docx": args.artifact,
                                 "markdown": args.artifact_md or None,
                                 "editable": True}
    if args.evidence:
        result["evidence_map"] = plan_rows
    if fact_report is not None:
        result["fact_check"] = fact_report
    if plan_report is not None:
        result["consistency_check"] = plan_report
    if seven_report is not None:
        result["completeness_check"] = seven_report
    if render_report is not None:
        result["render"] = render_report
    if args.ledger:
        result["fact_ledger_ref"] = args.ledger

    # ---- 不确定性 / 变更记录 ------------------------------------------
    prev_notes = result.get("uncertainty")
    merged = [x for x in (prev_notes if isinstance(prev_notes, list) else []) if x not in notes]
    result["uncertainty"] = merged + notes
    if args.changelog:
        result["changelog"] = as_list(args.changelog)
    else:
        result.setdefault("changelog", [])
    result["status"] = status

    # 依赖 uncertainty 的语义产物
    artifacts["uncertainty"] = result["uncertainty"]
    artifacts["version_and_boundary"] = {
        "changes": result["changelog"],
        "human_confirmation_items": result["uncertainty"],
        "material_gaps": [n for n in result["uncertainty"]
                          if any(k in n for k in ("缺口", "缺失", "无法", "无法获取",
                                                  "不可提取", "材料"))],
        "exceptions": [n for n in result["uncertainty"]
                       if any(k in n for k in ("异常", "报错", "失败", "中断"))],
    }
    artifacts["material_gaps"] = artifacts["version_and_boundary"]["material_gaps"]

    # ---- 语义回填契约键（键不缺 + 值不为空）---------------------------
    for k in key_list:
        val = pick_semantic(k, artifacts)
        if val not in (None, "", [], {}):
            result[k] = val
        elif k not in result or result.get(k) in (None, "", [], {}):
            result[k] = None

    # ---- 固定语义产物（平台契约之外的通用可核验字段）------------------
    for name, val in artifacts.items():
        if name == "deliverable_content" and args.embed_key != "deliverable_content":
            continue
        if val not in (None, "", [], {}):
            result.setdefault(name, val)

    # ---- --set 显式覆盖（最后生效）------------------------------------
    for kv in args.set:
        if "=" in kv:
            k, v = kv.split("=", 1)
            try:
                v = json.loads(v)
            except Exception:
                pass
            result[k] = v

    try:
        os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
        json.dump(result, open(result_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        written = True
    except Exception as e:
        written = False
        sys.stderr.write("result.json 写盘失败: %s\n" % e)

    # ---- 自检输出（协议第 6 条依据）------------------------------------
    empty_keys = [k for k in key_list if result.get(k) in (None, "", [], {})]
    filled_keys = [k for k in key_list if result.get(k) not in (None, "", [], {})]
    check = {"ok": written, "result": result_path, "status": status,
             "case_id": result.get("case_id"), "contract_keys": key_list,
             "contract_keys_total": len(key_list),
             "contract_keys_empty": empty_keys,
             "contract_keys_filled": len(filled_keys),
             "embed_key": args.embed_key if args.embed_file else None,
             "embed_chars": embed_chars,
             "seven_check_verdict": (result.get("completeness_check") or {}).get("verdict")
                                    if isinstance(result.get("completeness_check"), dict) else None,
             "gain_evidence_present": bool(result.get("gain_evidence")),
             "gain_comparison_rows": len((result.get("gain_evidence") or {}).get("comparison", []))
                                    if isinstance(result.get("gain_evidence"), dict) else 0,
             "efficiency_present": bool(result.get("efficiency")),
             "uncertainty_count": len(result["uncertainty"])}
    print(json.dumps(check, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
