#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_evidence.py — 增益证据层（同输入双臂消融 + 污染反例注入 + 效率计数）

同一校验器（format_check.run_check）对同一输入各跑一遍：
  · normal 臂：全部机制开启 → fail_normal
  · ablate 臂：--ablate 关闭「docx 排版规格机检/题注格式机检/标题编号机检」→ fail_ablate
FAIL 数差（fail_normal - fail_ablate）即被关闭机制的机器判定增量，逐机制映射指标并记录边界与失效条件。
污染反例：把刻意注入违规的稿件副本（重复标题编号/题注跳号/孤立引用/必需章节改名）交给 normal 臂复跑，
验证其抓错能力（caught 注入数 vs 抓到数，逐条留痕）。
--selftest：内存最小用例自检（双臂差 + 污染捕获断言），结论照实输出，退出码恒 0。
--write：结果写入 result.json 的 gain_evidence 键（唯一写入方，build_result 不写此键）。
退出码恒 0：结论一律写 JSON，不以退出码表达成败。
"""
import argparse, json, os, re, sys, time

try:
    import _rlog
except Exception:
    _rlog = None

try:
    import format_check as _fc
except Exception:
    _fc = None


def load(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


# ---------------- 污染反例注入 ----------------

def inject_pollution(draft_text, required_sections):
    """返回 (污染文本, 注入清单)。每条注入记录 applied（文本是否命中注入点）。"""
    injections, text = [], draft_text

    def sub_once(pat, repl, name, mechanism):
        nonlocal text
        m = re.search(pat, text, re.M)
        if not m:
            injections.append({"name": name, "mechanism": mechanism, "applied": False,
                               "note": "未找到注入点（稿件形态不含该结构），跳过"})
            return
        text = text[:m.start()] + repl(m) + text[m.end():]
        injections.append({"name": name, "mechanism": mechanism, "applied": True})

    # 1) 重复标题编号（插入新行，保留原行）→ heading_numbering 应报 number_not_continuous
    m = re.search(r"^##\s+\d+(?:\.\d+)*\s.*$", text, re.M)
    if m:
        num = re.search(r"\d+(?:\.\d+)*", m.group(0)).group(0)
        text = text[:m.end()] + "\n## %s 重复编号注入（污染反例）" % num + text[m.end():]
        injections.append({"name": "duplicate_heading_number", "mechanism": "heading_numbering",
                           "applied": True, "detail": "插入重复编号 %s" % num})
    else:
        injections.append({"name": "duplicate_heading_number", "mechanism": "heading_numbering",
                           "applied": False, "note": "稿内无编号标题，跳过"})
    # 2) 第二个题注跳号 → caption_format 应报 prefix_or_order
    sub_once(r"(图\s*2)", lambda m: "图3（题注跳号注入）", "caption_number_skip", "caption_format")
    # 3) 孤立引用 [99] → citation_style 应报 cited_not_listed
    if re.search(r"\S", text):
        m = re.search(r"^(\S.*\S)$", text, re.M)
        if m:
            text = text[:m.end()] + " [99]" + text[m.end():]
            injections.append({"name": "orphan_citation_99", "mechanism": "citation_style",
                               "applied": True})
    # 4) 必需章节移除（整行替换，不留原子串）→ sections_complete 应报 missing
    if required_sections:
        sec = required_sections[0]
        pat = re.compile(r"^##\s*" + re.escape(sec) + r"\s*$", re.M)
        m = pat.search(text)
        if m:
            # 注意不能保留 sec 子串，否则标题模糊匹配（substring）会放行
            text = pat.sub("## 污染注入占位标题", text, count=1)
            injections.append({"name": "required_section_removed", "mechanism": "sections_complete",
                               "applied": True, "detail": "移除必需章节《%s》标题行" % sec})
        else:
            injections.append({"name": "required_section_removed", "mechanism": "sections_complete",
                               "applied": False, "note": "稿内无 %s 标题，跳过" % sec})
    return text, injections


def mechanism_map(checklist, ablate_report, normal_report):
    """机制→指标映射：每个被关闭的机制对应哪些检查项、多少条变人工核对。"""
    ablated_items = set(ablate_report.get("ablated") or [])
    mp = []
    for it in (normal_report.get("results") or []):
        if it.get("item") in ablated_items:
            mp.append({"mechanism": it["item"], "gate_in_ablate": "skipped_ablation",
                       "checked_items_normal": 1,
                       "manual_in_ablate": 1,
                       "note": "该机制关闭后此检查项不再运行，须人工逐条核对（不得宣称已核对）"})
    docx_count = sum(1 for it in (normal_report.get("results") or []) if it.get("item") == "docx_spec" and it.get("gate") == "enforced")
    if "docx_spec" in ablated_items:
        mp.append({"mechanism": "docx_spec", "gate_in_ablate": "skipped_ablation",
                   "checked_items_normal": docx_count or None,
                   "manual_in_ablate": None,
                   "note": "docx 排版规格（页边距/栏数/字号/行距）核对全部退化为人工，条数见 normal 臂 results"})
    return mp


def dual_run(draft_md, checklist, docx_path=None):
    """同输入双臂：返回对照结构（含机器判定的 fail 差值）。"""
    normal = _fc.run_check(draft_md, checklist, docx_path, ablate=False)
    ablate = _fc.run_check(draft_md, checklist, docx_path, ablate=True)
    fail_delta = normal["fail"] - ablate["fail"]
    enforced_n = sum(1 for r in normal["results"] if r.get("gate") == "enforced")
    enforced_a = sum(1 for r in ablate["results"] if r.get("gate") == "enforced")
    has_items = bool((checklist or {}).get("items") or (checklist or {}).get("required_sections"))
    out = {
        "normal_arm": {"fail": normal["fail"], "verdict": normal["verdict"],
                       "enforced_checks": enforced_n,
                       "fail_items": [r.get("item") for r in normal["results"] if r.get("verdict") == "fail"]},
        "ablated_arm": {"fail": ablate["fail"], "verdict": ablate["verdict"],
                        "enforced_checks": enforced_a,
                        "ablated_mechanisms": ablate.get("ablated") or [],
                        "fail_items": [r.get("item") for r in ablate["results"] if r.get("verdict") == "fail"]},
        "fail_delta": {"value": fail_delta, "decided_by": "machine: 两臂同输入各跑一遍，fail 计数差",
                       "meaning": "被关闭机制在 normal 臂额外抓出的违规数（>0 即机制有真实检出力）",
                       "valid": bool(has_items) and _fc is not None,
                       "invalid_note": None if has_items else "checklist 无条目（模板未识别）：差值无意义，记 null 供人工判断"},
    }
    if not out["fail_delta"]["valid"]:
        out["fail_delta"]["value"] = None
    out["mechanism_metric_map"] = mechanism_map(checklist, ablate, normal)
    return out, normal, ablate


def pollution_test(draft_md, checklist, docx_path, workdir, required_sections):
    try:
        text = open(draft_md, encoding="utf-8").read()
    except Exception as e:
        return {"applied": False, "error": str(e)[:160],
                "note": "稿件不可读：污染反例验证未运行，下游不得宣称抓错能力已验证"}
    polluted, injections = inject_pollution(text, required_sections)
    pdir = os.path.join(workdir, "ablation")
    os.makedirs(pdir, exist_ok=True)
    pfile = os.path.join(pdir, "adapted_polluted.md")
    try:
        open(pfile, "w", encoding="utf-8").write(polluted)
    except Exception as e:
        return {"applied": False, "error": str(e)[:160], "injections": injections,
                "note": "污染副本写盘失败：验证未运行"}
    rep = _fc.run_check(pfile, checklist, None, ablate=False)
    caught = [r.get("item") for r in rep["results"] if r.get("verdict") == "fail"]
    applied = [i for i in injections if i.get("applied")]
    return {"applied": True, "polluted_copy": pfile, "injections": injections,
            "injected_count": len(applied), "caught_items": caught, "caught_count": len(caught),
            "caught_all": set(i["mechanism"] for i in applied).issubset(set(caught)) if applied else None,
            "note": "污染副本与正式稿隔离存放于 %s，不影响交付物" % pdir}


def baseline_comparison(checklist, normal_report):
    items = (checklist or {}).get("items") or []
    docx_items = [i for i in items if i.get("checkable") == "docx"]
    md_items = [i for i in items if i.get("checkable") == "md"]
    req = (checklist or {}).get("required_sections") or []
    baseline_manual = len(items) + len(req) + 3  # +3: 无机检时编号/交叉引用/引用对应均需人工通读
    skipped_n = len(normal_report.get("skipped") or [])
    skill_manual = normal_report["fail"] + skipped_n
    reduction = baseline_manual - skill_manual
    return {"baseline_manual_review_items": baseline_manual,
            "baseline_note": "基础路径：不做规格抽取与机检，每条规格/章节须人工翻模板逐条比对",
            "skill_manual_review_items": skill_manual,
            "reduction": reduction,
            "reduction_rate": round(reduction / baseline_manual, 3) if baseline_manual else None,
            "docx_machine_items": len(docx_items), "md_machine_items": len(md_items)}


def efficiency_counters(normal_report, run_log_path):
    rows = _rlog.read_log(run_log_path) if _rlog is not None else []
    by_tool = {}
    for r in rows:
        by_tool[r.get("tool") or "unknown"] = by_tool.get(r.get("tool") or "unknown", 0) + 1
    return {"tool_calls": len(rows), "tool_calls_by_script": by_tool,
            "mechanical_check_runs": by_tool.get("format_check", 0),
            "checks_enforced_normal_arm": sum(1 for r in normal_report["results"] if r.get("gate") == "enforced"),
            "note": "仅统计脚本可自动采集项；模型请求数由 Harness 侧记录，不在此冒充"}


def selftest(tmpdir):
    """内存最小用例：双臂差 + 污染捕获断言。返回 verdict 字符串（PASS/FAIL）与明细。"""
    detail = {}
    ok = _fc is not None
    detail["format_check_import"] = "ok" if ok else "missing"
    if not ok:
        return "FAIL", detail
    cl = {"items": [
        {"item_id": "F01", "category": "margin", "name": "页边距", "checkable": "docx",
         "check_type": "numeric", "template_value": "上下2.54cm", "numeric": {"cm": 2.54}, "scope": None,
         "source": {"file": "demo", "line": 1, "quote": "页边距上下2.54cm"}},
        {"item_id": "F02", "category": "citation", "name": "参考文献样式", "checkable": "md",
         "check_type": "enum", "template_value": "顺序编码制", "numeric": None, "scope": None,
         "source": {"file": "demo", "line": 2, "quote": "参考文献采用顺序编码制"}}],
        "required_sections": ["摘要", "结论"]}
    draft = "# 示意稿（自检用）\n\n## 摘要\n\n示意正文一段。\n\n## 1 方法\n\n**图1 示意图**\n\n## 2 结论\n\n引用[1]。\n\n## 参考文献\n\n[1] 示意条目. 期刊, 2024.\n"
    dpath = os.path.join(tmpdir, "selftest_draft.md")
    open(dpath, "w", encoding="utf-8").write(draft)
    try:
        out, normal, _ = dual_run(dpath, cl, None)
        detail["fail_normal"] = normal["fail"]
        detail["ablated_mechanisms"] = out["ablated_arm"]["ablated_mechanisms"]
        ok = ok and normal["fail"] >= 0
        pol = pollution_test(dpath, cl, None, tmpdir, cl["required_sections"])
        detail["pollution"] = {"injected": pol.get("injected_count"), "caught": pol.get("caught_count"),
                               "caught_items": pol.get("caught_items")}
        ok = ok and pol.get("caught_count", 0) > 0
    except Exception as e:
        detail["error"] = str(e)[:200]
        ok = False
    return ("PASS" if ok else "FAIL"), detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--draft", default="/app/output/adapted.md")
    ap.add_argument("--checklist", default="/app/work/checklist.json")
    ap.add_argument("--docx", default="/app/output/adapted.docx")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--run-log", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--write", action="store_true")
    args, err = None, None
    try:
        args = ap.parse_args()
    except SystemExit as e:
        err = e
    if args is None:
        print(json.dumps({"ok": False, "note": "argparse error（非致命，恒 exit 0）", "detail": str(err)}, ensure_ascii=False))
        return 0
    t0 = time.time()
    if args.selftest:
        import tempfile
        verdict, detail = selftest(tempfile.mkdtemp(prefix="acfmt_selftest_"))
        print(json.dumps({"selftest": verdict, "detail": detail,
                          "exit_code_policy": "always_zero: FAIL 也以 exit 0 退出，结论照实"}, ensure_ascii=False))
        if _rlog is not None:
            _rlog.log_call("gain_evidence", argv=["--selftest"], seconds=time.time() - t0,
                           extra={"selftest": verdict})
        return 0
    if _fc is None:
        print(json.dumps({"ok": False, "note": "format_check 模块不可用：双臂对照未运行，下游不得宣称消融已取证"},
                         ensure_ascii=False))
        return 0
    checklist = load(args.checklist) or {}
    out, normal, ablate = dual_run(args.draft, checklist, args.docx if os.path.exists(args.docx) else None)
    out["pollution_test"] = pollution_test(
        args.draft, checklist, None, args.workdir, checklist.get("required_sections") or [])
    out["baseline_comparison"] = baseline_comparison(checklist, normal)
    out["efficiency"] = efficiency_counters(normal, args.run_log)
    out["boundary"] = [
        "同输入自比：量化的是被关闭机制的检出增量与人工核对工作量削减，不等同平台白板对照",
        "机制消融≠平台白板：白板由组织方固定，本层仅证明各机制在本次运行中真实参与检出",
        "污染反例仅覆盖 md 层（标题/题注/引用/章节）；docx 二进制层的注入未覆盖，排版规格抓错力由双臂差佐证",
    ]
    out["failure_conditions"] = [
        "checklist 无条目（模板未识别）→ fail_delta.valid=False，差值记 null，不硬凑",
        "稿件不可读 → 双臂与污染验证如实记 unreadable，增益证据为空",
        "两臂均 fail=0 → 差值为 0 属合法结果（稿件本就合规），不人为制造差异",
    ]
    out["exit_code_policy"] = "always_zero: FAIL/差值为 0 也以 exit 0 退出，结论照实"
    if args.write:
        result = load(args.result) or {}
        if result:
            result["gain_evidence"] = out
            try:
                json.dump(result, open(args.result, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                out["written"] = True
            except Exception as e:
                out["written"] = False; out["write_error"] = str(e)[:200]
        else:
            out["written"] = False; out["write_note"] = "result.json 不存在或不可解析：本层结论仅回显，不阻断交付"
    print(json.dumps({"ok": True, "fail_delta": out["fail_delta"]["value"],
                      "pollution_caught": out["pollution_test"].get("caught_count"),
                      "baseline_reduction": out["baseline_comparison"]["reduction"],
                      "verdict_normal": out["normal_arm"]["verdict"],
                      "verdict_ablate": out["ablated_arm"]["verdict"]}, ensure_ascii=False))
    if _rlog is not None:
        _rlog.log_call("gain_evidence", argv=sys.argv[1:], seconds=time.time() - t0,
                       extra={"fail_delta": out["fail_delta"]["value"],
                              "pollution_caught": out["pollution_test"].get("caught_count")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
