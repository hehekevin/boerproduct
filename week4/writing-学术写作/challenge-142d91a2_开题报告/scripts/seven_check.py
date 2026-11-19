#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seven_check.py — 开题方案三项机检（章节完整性/路线可执行/时间表一致性）
A. 七要素章节完整性: 逐项核对正文是否包含全部必备章节（含边界与不确定性登记），
   每项输出 {item, expected, applied, match, location} 三元组——不许只写"已核对"。
B. 技术路线可执行性: route.jsonl 每步必须有 input/output/依赖/资源/里程碑归属；
   依赖引用必须指向真实存在的步骤；每步必须落到 ≥1 个里程碑。
C. 时间表-内容一致性: milestones.jsonl 的周期与交付物必须能回证到正文；
   正文进度表中出现的月份区间必须有对应里程碑条目；总周期不超 constraints。

闸门状态显式枚举: enforced(已核) / skipped_not_provided(输入未提供) /
not_found(文件不存在) / unreadable(不可解析)。未运行≠通过，skipped 必须写 gate_note。
退化模式(--ablate sections|route|timeline|all): 关闭指定机检，模拟"不加载本 Skill
的基础 Agent"在同一输入上的行为——被关闭的检查仍占位输出 applied=false, match=false，
既不计入 fail 也不得计入通过率（占位项计入"需人工核对条目数"）。
退出码: 恒为 0。verdict 照实记录 fail/incomplete/ablation，脚本永不中断交付链。
"""
import argparse, json, os, re, sys

GATE_OK = "enforced"


def gate(path):
    """输入闸门状态判定。"""
    if not path or not os.path.exists(path):
        return "not_found"
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            f.read(1024)
        return GATE_OK
    except Exception:
        return "unreadable"


def load_lines(path):
    rows, used = [], 0
    if not path or not os.path.exists(path):
        return rows, False
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
                used += 1
            except Exception:
                continue
    return rows, used > 0


def load_json(path):
    if not path or not os.path.exists(path):
        return None
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


# 七要素必备章节：item → 正文中须出现的关键词（任一命中即 match）
SECTIONS = [
    ("研究背景", ["研究背景", "选题背景", "背景与意义", "立项依据"]),
    ("研究现状与缺口", ["研究现状", "国内外现状", "文献综述", "gap", "缺口"]),
    ("问题定义", ["研究问题", "问题定义", "拟解决", "关键科学问题"]),
    ("研究目标", ["研究目标", "总体目标", "研究内容与目标"]),
    ("技术路线与方法", ["技术路线", "研究方法", "技术方案", "实施路线"]),
    ("阶段计划", ["阶段计划", "进度安排", "进度计划", "里程碑", "研究计划"]),
    ("风险与应对", ["风险", "应对", "备选方案"]),
    ("预期成果", ["预期成果", "预期产出", "考核指标", "创新点"]),
    ("边界与不确定性", ["待人工确认", "待确认", "不确定性", "notes_for_human", "材料缺口"]),
]


def check_sections(text, findings):
    """A. 章节完整性：逐项三元组，缺失计 fail。"""
    for item, kws in SECTIONS:
        hit_line = None
        for ln, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            if any(norm(k).lower() in norm(low) for k in kws):
                hit_line = ln
                break
        findings.append({"check": "A_section_completeness", "item": item,
                         "expected": "正文含章节关键词 " + "/".join(kws[:2]),
                         "applied": True, "match": hit_line is not None,
                         "location": "line%d" % hit_line if hit_line else None})
    return [f for f in findings if f["check"] == "A_section_completeness" and not f["match"]]


def sections_placeholders(findings):
    """A 被退化关闭：仍占位输出全部必备章节项（applied=false, match=false）。"""
    for item, kws in SECTIONS:
        findings.append({"check": "A_section_completeness", "item": item,
                         "expected": "正文含章节关键词 " + "/".join(kws[:2]),
                         "applied": False, "match": False, "location": None,
                         "reason": "ablation_disabled: 未执行章节完整性机检"})


def check_route(route, ms, findings, fails):
    """B. 技术路线可执行性：字段齐全 + 依赖真实 + 里程碑归属。"""
    sids = {r.get("sid") for r in route if isinstance(r, dict)}
    mids = {m.get("mid") for m in ms if isinstance(m, dict)}
    for r in route:
        if not isinstance(r, dict):
            fails.append({"check": "B_route_executability", "item": "row",
                          "problem": "route 行非对象"})
            continue
        sid = r.get("sid") or "unnamed"
        miss = [k for k in ("name", "input", "output", "depends", "resources")
                if (k not in r if k == "depends" else not r.get(k))]
        findings.append({"check": "B_route_executability", "item": sid,
                         "expected": "name/input/output/depends/resources 五字段齐全",
                         "applied": True, "match": not miss,
                         "location": "route.jsonl:%s" % sid})
        if miss:
            fails.append({"check": "B_route_executability", "item": sid,
                          "problem": "字段缺失: " + ",".join(miss)})
        for d in (r.get("depends") or []):
            if d not in sids:
                fails.append({"check": "B_route_executability", "item": sid,
                              "problem": "依赖 %s 不存在" % d})
        # 里程碑归属：显式 milestone 字段，或 resources/mid 引用
        owner = r.get("milestone") or r.get("mid")
        findings.append({"check": "B_route_milestone_map", "item": sid,
                         "expected": "每步归属 ≥1 个里程碑",
                         "applied": True, "match": bool(owner and owner in mids),
                         "location": "route.jsonl:%s" % sid})
        if not (owner and owner in mids):
            fails.append({"check": "B_route_milestone_map", "item": sid,
                          "problem": "未归属到有效里程碑（milestone=%s）" % owner})
    return sids, mids


def route_placeholders(route, findings):
    """B 被退化关闭：每步占位两条（字段齐全/里程碑归属）。"""
    for r in route:
        if not isinstance(r, dict):
            continue
        sid = r.get("sid") or "unnamed"
        findings.append({"check": "B_route_executability", "item": sid,
                         "expected": "name/input/output/depends/resources 五字段齐全",
                         "applied": False, "match": False,
                         "location": "route.jsonl:%s" % sid,
                         "reason": "ablation_disabled: 未执行路线可执行性机检"})
        findings.append({"check": "B_route_milestone_map", "item": sid,
                         "expected": "每步归属 ≥1 个里程碑",
                         "applied": False, "match": False,
                         "location": "route.jsonl:%s" % sid,
                         "reason": "ablation_disabled: 未执行里程碑归属机检"})


MONTH_PAT = re.compile(r"第?\s*(\d+)\s*[-~至到]\s*(\d+)\s*月")


def check_timeline(text, ms, con, findings, fails):
    """C. 时间表-内容一致性：正文可回证 + 进度表条目有对应里程碑 + 超期。"""
    span = None
    if con:
        for k in ("total_months", "period_months"):
            if con.get(k):
                try:
                    span = int(con[k])
                except Exception:
                    pass
    body = norm(text)
    for m in ms:
        if not isinstance(m, dict):
            continue
        mid = m.get("mid") or "unnamed"
        period = norm(m.get("period"))
        ok_period = bool(period) and period in body
        findings.append({"check": "C_timeline_consistency", "item": "%s.period" % mid,
                         "expected": "正文回证里程碑周期 %s" % (m.get("period") or ""),
                         "applied": True, "match": ok_period,
                         "location": "milestones.jsonl:%s" % mid})
        if not ok_period:
            fails.append({"check": "C_timeline_consistency", "item": "%s.period" % mid,
                          "problem": "周期 '%s' 未出现在正文——时间表与内容脱节" % (m.get("period") or "")})
        has_del = bool(m.get("deliverable"))
        findings.append({"check": "C_timeline_deliverable", "item": "%s.deliverable" % mid,
                         "expected": "里程碑声明交付物（deliverable 必填）",
                         "applied": True, "match": has_del,
                         "location": "milestones.jsonl:%s" % mid})
        if not has_del:
            fails.append({"check": "C_timeline_consistency", "item": "%s.deliverable" % mid,
                          "problem": "里程碑无交付物（task/deliverable 必填）"})
    # 正文进度表中的月份区间必须有对应里程碑（防正文乱排）
    ms_periods = {norm(m.get("period")) for m in ms if isinstance(m, dict)}
    for ln, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith(("|", "-")) or "月" not in s:
            continue
        for a, b in MONTH_PAT.findall(s):
            cand = ["第%s-%s月" % (a, b), "%s-%s月" % (a, b)]
            if not any(norm(c) in ms_periods for c in cand):
                fails.append({"check": "C_timeline_consistency", "item": "draft:line%d" % ln,
                              "problem": "正文计划区间 第%s-%s月 无对应里程碑条目" % (a, b)})
            if span:
                try:
                    if int(b) > span:
                        fails.append({"check": "C_timeline_consistency", "item": "draft:line%d" % ln,
                                      "problem": "正文区间超出给定周期 %d 月" % span})
                except Exception:
                    pass


def timeline_placeholders(ms, findings):
    """C 被退化关闭：每个里程碑占位两条（周期回证/交付物）。"""
    for m in ms:
        if not isinstance(m, dict):
            continue
        mid = m.get("mid") or "unnamed"
        findings.append({"check": "C_timeline_consistency", "item": "%s.period" % mid,
                         "expected": "正文回证里程碑周期 %s" % (m.get("period") or ""),
                         "applied": False, "match": False,
                         "location": "milestones.jsonl:%s" % mid,
                         "reason": "ablation_disabled: 未执行时间表一致性机检"})
        findings.append({"check": "C_timeline_deliverable", "item": "%s.deliverable" % mid,
                         "expected": "里程碑声明交付物（deliverable 必填）",
                         "applied": False, "match": False,
                         "location": "milestones.jsonl:%s" % mid,
                         "reason": "ablation_disabled: 未执行时间表一致性机检"})


def compute_metrics(findings, ablated):
    """可对照指标：完整率 / 通过率 / 需人工核对条目数 / 步骤数。
    通过率分母含被退化关闭的占位项——未运行不等于通过。"""
    def pick(prefix):
        return [f for f in findings if f.get("check", "").startswith(prefix)]

    sec = pick("A_section_completeness")
    rou = pick("B_route")
    tim = pick("C_timeline")
    sec_matched = sum(1 for f in sec if f.get("applied") and f.get("match"))
    rou_matched = sum(1 for f in rou if f.get("applied") and f.get("match"))
    tim_matched = sum(1 for f in tim if f.get("applied") and f.get("match"))
    unverified = sum(1 for f in findings if not f.get("applied"))
    failed = sum(1 for f in findings if f.get("applied") and not f.get("match"))
    total = len(findings)
    verified = sum(1 for f in findings if f.get("applied") and f.get("match"))
    return {
        "checks_total": total,
        "checks_verified": verified,
        "checks_failed": failed,
        "checks_unverified": unverified,
        "section_completeness_rate": round(sec_matched / len(sec), 4) if sec else None,
        "route_executability_pass_rate": round(rou_matched / len(rou), 4) if rou else None,
        "timeline_consistency_rate": round(tim_matched / len(tim), 4) if tim else None,
        "manual_check_items": failed + unverified,
        "ablated_checks": sorted(set(ablated)),
        "metric_note": "分母含被退化关闭的占位项；未运行≠通过。"
                       "manual_check_items = 失败项 + 未核验项 = 需人工复核条目数。",
    }


def run_checks(draft=None, route=None, milestones=None, constraints=None, ablate=None):
    """执行三项机检并返回报告（可被 gain_evidence.py 直接调用做同输入对照）。"""
    ablate = set(x.strip().lower() for x in (ablate or "").split(",")
                 if x.strip() and x.strip() != "none")
    if "all" in ablate:
        ablate |= {"sections", "route", "timeline"}

    findings, fails, notes = [], [], []
    gates = {}

    gates["draft"] = gate(draft)
    gates["route"] = gate(route) if route else "skipped_not_provided"
    gates["milestones"] = gate(milestones)
    gates["constraints"] = gate(constraints) if constraints else "skipped_not_provided"
    for name, st in gates.items():
        if st != GATE_OK:
            notes.append("gate[%s]=%s：下游不得宣称该项已核对" % (name, st))

    text = ""
    if gates["draft"] == GATE_OK:
        try:
            text = open(draft, encoding="utf-8", errors="ignore").read()
        except Exception:
            gates["draft"] = "unreadable"
            notes.append("gate[draft]=unreadable：章节完整性检查未运行")
    if gates["draft"] != GATE_OK:
        notes.append("A 章节完整性 skipped：正文不可读，不视为通过")

    ms, ms_ok = load_lines(milestones)
    if gates["milestones"] == GATE_OK and not ms_ok:
        gates["milestones"] = "unreadable"
        notes.append("gate[milestones]=unreadable：时间表一致性检查未运行")
    if gates["milestones"] != GATE_OK:
        notes.append("C 时间表一致性 skipped：milestones 不可用，不视为通过")

    # A 章节完整性
    if gates["draft"] == GATE_OK:
        if "sections" in ablate:
            sections_placeholders(findings)
            notes.append("ablation: A 章节完整性机检已关闭（退化对照模式）")
        else:
            misses = check_sections(text, findings)
            for f in misses:
                fails.append({"check": "A_section_completeness", "item": f["item"],
                              "problem": "必备章节缺失（无关键词命中）"})

    # B 路线可执行性
    route_rows, route_ok = ([], False)
    if route and gates["route"] == GATE_OK:
        route_rows, route_ok = load_lines(route)
        if not route_ok:
            gates["route"] = "unreadable"
            notes.append("gate[route]=unreadable：路线可执行性检查未运行")
        elif "route" in ablate:
            route_placeholders(route_rows, findings)
            notes.append("ablation: B 路线可执行性机检已关闭（退化对照模式）")
        else:
            check_route(route_rows, ms, findings, fails)
    elif route is None:
        notes.append("B 路线可执行性 skipped_not_provided：未提供 route.jsonl，"
                     "下游不得宣称技术路线已逐条核对")

    con = load_json(constraints) if constraints else None
    if constraints and gates["constraints"] == GATE_OK and not con:
        gates["constraints"] = "unreadable"
        notes.append("gate[constraints]=unreadable：周期上限检查未运行")
    if gates["draft"] == GATE_OK and gates["milestones"] == GATE_OK:
        if "timeline" in ablate:
            timeline_placeholders(ms, findings)
            notes.append("ablation: C 时间表一致性机检已关闭（退化对照模式）")
        else:
            check_timeline(text, ms, con, findings, fails)

    n_fail = len(fails)
    if n_fail:
        verdict = "fail"
    elif ablate:
        verdict = "ablation"
    elif all(v == GATE_OK for v in gates.values()):
        verdict = "pass"
    else:
        verdict = "incomplete"
    if gates.get("route") == "skipped_not_provided" and verdict == "pass":
        verdict = "incomplete"

    report = {"verdict": verdict, "gates": gates,
              "fail": n_fail, "failures": fails[:200],
              "checks": findings,
              "checks_total": len(findings), "checks_matched": sum(
                  1 for f in findings if f.get("applied") and f.get("match")),
              "notes": notes,
              "metrics": compute_metrics(findings, ablate),
              "hint": "fail 项必须修复后重跑或如实登记 uncertainty；"
                      "incomplete/skipped/ablation 表示未运行，不视为已核对。"}
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", default=None, help="proposal.md 正文")
    ap.add_argument("--route", default=None, help="route.jsonl 技术路线步骤")
    ap.add_argument("--milestones", default=None, help="milestones.jsonl 阶段计划")
    ap.add_argument("--constraints", default=None, help="constraints.json 周期/资源约束")
    ap.add_argument("--ablate", default=None,
                    help="退化模式：关闭机检 sections,route,timeline,all（逗号分隔）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    report = run_checks(draft=args.draft, route=args.route, milestones=args.milestones,
                         constraints=args.constraints, ablate=args.ablate)
    if args.out:
        try:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception as e:
            report["notes"].append("报告写盘失败: %s" % str(e)[:120])
    print(json.dumps({k: report[k] for k in ("verdict", "fail", "checks_total",
                                             "checks_matched")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
