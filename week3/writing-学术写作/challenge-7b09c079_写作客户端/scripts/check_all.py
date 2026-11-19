#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_all.py — 终局机械自检（学术写作客户端版）。
逐条输出 {item, applied, match, detail} 校验三元组 + 闸门显式枚举
（enforced / skipped_not_provided / not_found / unreadable），全部嵌入 result.json
顶层 checks / gates 字段。
**退出码契约**：任何路径（通过 / 失败 / 缺料 / 异常）都退出 0 ——校验结论由
result.json 的 verdict + checks[] + gates 照实记录，绝不因校验失败中断交付；
修复责任交给第 7 步的"按报告逐条修复再跑"。自测：--selftest。"""
from __future__ import annotations
import argparse, glob, json, os, re, sys

STATUS_OK = ("complete", "partial", "failed", "blocked")

def norm(s):
    return re.sub(r"\s+", "", str(s or ""))

def load(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return None

def load_jsonl(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return [json.loads(l) for l in f if l.strip()]
    except Exception:
        return []

def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None

def gate_of(path):
    """闸门状态显式枚举。"""
    if path is None:
        return "skipped_not_provided"
    if not os.path.exists(path):
        return "not_found"
    if load(path) is None and not read_text(path):
        return "unreadable"
    return "enforced"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--edits", default="/app/work/edits.jsonl")
    ap.add_argument("--structure", default="/app/work/structure.json")
    ap.add_argument("--revised", default="/app/output/revised.md")
    ap.add_argument("--edits-verify", dest="edits_verify", default="/app/output/edits_verify.json")
    ap.add_argument("--render-log", dest="render_log", default="/app/output/previews/render_log.json")
    ap.add_argument("--client", default="/app/output/revision_client.html")
    ap.add_argument("--gain-evidence", dest="gain_evidence", default="/app/output/gain_evidence.json")
    ap.add_argument("--write-back", action="store_true", help="把 checks/gates 写回 result.json")
    ap.add_argument("--selftest", action="store_true")
    try:
        args = ap.parse_args()
    except SystemExit:
        print("[check_all] 参数解析失败（退出码 0，不中断交付）")
        return 0
    if args.selftest:
        return cmd_selftest(args)

    checks = []
    def add(item, match, detail="", applied=True):
        checks.append({"item": item, "applied": bool(applied), "match": bool(match),
                       "detail": str(detail)[:300]})

    r = load(args.result) or {}
    case = load(args.case) or {}
    contract = case.get("output_contract")
    fields = list(contract.keys()) if isinstance(contract, dict) else \
        ([str(x) for x in contract] if isinstance(contract, list) else
         ["case_id", "status", "result", "claims", "uncertainties"])

    if not r:
        add("result_readable", False, "result.json 不存在或不可解析")
    else:
        add("result_readable", True)
        missing = [f for f in fields if f not in r]
        add("contract_fields_complete", not missing, "缺: %s" % missing if missing else "契约字段齐全")
        add("case_id_present", bool(str(r.get("case_id") or "").strip()))
        add("status_legal", r.get("status") in STATUS_OK, "status=%r" % r.get("status"))
        add("case_id_consistent", (not case) or (str(r.get("case_id")) == str(case.get("case_id") or r.get("case_id"))))

    # ④ 修订锚点：before/anchor_quote 逐字命中原稿（structure 段落 or 原稿目录）
    orig_text = ""
    st = load(args.structure)
    if isinstance(st, dict):
        orig_text = "\n".join(str(p.get("text") or "") for p in st.get("paragraphs", []))
    elif os.path.isdir(args.structure):
        orig_text = "\n".join(read_text(f) or "" for f in sorted(glob.glob(os.path.join(args.structure, "*.txt"))))
    edits = load_jsonl(args.edits)
    if not edits:
        add("edits_present", False, "修订台账为空或不可读")
    else:
        anchor_bad = [e.get("eid") for e in edits
                      if norm(e.get("before") or e.get("anchor_quote") or "")[:40]
                      and norm(e.get("before") or e.get("anchor_quote") or "")[:40] not in norm(orig_text)]
        add("edit_anchors_verbatim", not anchor_bad, "锚点失效: %s" % anchor_bad[:10])

    # ⑤ 改动落地：applied 的 after 逐字命中修订稿
    rev_raw = read_text(args.revised) if os.path.exists(args.revised) else None
    if rev_raw is None:
        add("revised_md_exists", False, "revised.md 不存在")
    else:
        add("revised_md_exists", True)
        rev_n = norm(rev_raw)
        applied_bad = [e.get("eid") for e in edits
                       if e.get("status") == "applied" and norm(e.get("after") or "")[:40]
                       and norm(e.get("after") or "")[:40] not in rev_n]
        add("edits_applied_in_revised", not applied_bad, "未落地: %s" % applied_bad[:10])
        nums = sorted({int(m.group(1)) for m in re.finditer(r"\[(\d{1,3})\]", rev_raw)})
        gaps = sorted(set(range(1, max(nums) + 1)) - set(nums)) if nums else []
        add("citation_numbering_continuous", not gaps, "引用缺口: %s" % gaps)

    # ⑥ claims 证据链
    claims = r.get("claims") if isinstance(r.get("claims"), list) else []
    bad_claims = [c.get("claim_id") for c in claims if not isinstance(c, dict)
                  or not (c.get("kind") and c.get("source_id") and c.get("location") and c.get("evidence"))]
    add("claims_chain_complete", bool(claims) and not bad_claims, "异常: %s" % bad_claims[:10])
    orig_n = norm(orig_text)
    unbacked = []
    for c in claims:
        if not isinstance(c, dict):
            continue
        for ev in (c.get("evidence") or []):
            q = norm(ev.get("quote") or "")[:40]
            if q and q not in orig_n and rev_raw and norm(q) not in norm(rev_raw):
                unbacked.append(c.get("claim_id"))
    add("claims_evidence_verbatim", not unbacked, "unbacked: %s" % unbacked[:10])

    # ⑦ 客户端嵌入 + features
    client_html = read_text(args.client) if os.path.exists(args.client) else None
    emb = ((r.get("result") or {}).get("client") or {}).get("embedded_html") or ""
    feats = ((r.get("result") or {}).get("client") or {}).get("features") or []
    add("client_html_exists", bool(client_html), args.client)
    add("client_embedded_in_result", bool(emb) and (not client_html or norm(emb) == norm(client_html)),
        "embedded_html 与磁盘 %s" % ("一致" if emb else "为空"))
    add("client_features_registered", len(feats) >= 8, "features=%d 条" % len(feats))

    # ⑧ 校验报告与闸门嵌入（本次运行即将写入 checks/gates）
    gates = {
        "edits_verify": gate_of(args.edits_verify),
        "render_preview": gate_of(args.render_log) if args.render_log else "skipped_not_provided",
        "structure_index": gate_of(args.structure),
        "revised_md": gate_of(args.revised),
        "gain_evidence": gate_of(args.gain_evidence),
    }
    warns = [k for k, v in gates.items() if v in ("not_found", "unreadable", "skipped_not_provided")]
    gate_note = ("下游不得对未 enforced 的闸门宣称已核对：%s" % warns) if warns else ""

    # ⑨ uncertainties / changelog
    unc = r.get("uncertainties")
    add("uncertainties_summary", bool(isinstance(unc, dict) and str(unc.get("summary") or "").strip()))
    add("changelog_present", bool(r.get("changelog")))

    # ⑩ gain_evidence / efficiency：使用增益的同输入对照证据
    ge = load(args.gain_evidence) if os.path.exists(args.gain_evidence) else None
    eff = r.get("efficiency") if isinstance(r, dict) else None
    if not ge:
        add("gain_evidence_present", False, "gain_evidence.json 缺失或不可解析（同输入对照证据缺失）")
    else:
        add("gain_evidence_present", True)
        runs = (ge.get("runs") or {})
        full = runs.get("full") or {}
        deg = runs.get("degraded") or {}
        has_full = bool((full.get("metrics") or {}))
        has_deg = bool((deg.get("metrics") or {}))
        add("gain_evidence_two_conditions", has_full and has_deg,
            "full=%s degraded=%s" % (has_full, has_deg))
        cmp_ = ge.get("comparison") or []
        add("gain_evidence_comparison_nonempty", bool(cmp_), "对照项 %d 条" % len(cmp_))
        mm = {c.get("metric"): c for c in cmp_ if isinstance(c, dict)}
        trace = mm.get("revision_traceability_rate") or {}
        add("gain_evidence_traceability_measured",
            isinstance(trace.get("full"), (int, float)) and isinstance(trace.get("degraded"), (int, float)),
            "full=%s degraded=%s" % (trace.get("full"), trace.get("degraded")))
        add("gain_evidence_mechanism_mapping", bool(ge.get("mechanism_to_metric")),
            "映射条目 %d 条" % len(ge.get("mechanism_to_metric") or []))
        add("gain_evidence_boundaries_declared", bool(ge.get("boundaries")),
            "边界声明 %d 条" % len(ge.get("boundaries") or []))
    if not isinstance(eff, dict) or not eff:
        add("efficiency_field_present", False, "result.json 缺 efficiency 字段")
    else:
        add("efficiency_field_present", True)
        add("efficiency_reproduce_documented", bool(eff.get("reproduce")),
            "复现说明 %d 条" % len(eff.get("reproduce") or []))
        add("efficiency_steps_recorded", isinstance(eff.get("steps_total"), (int, float)),
            "steps_total=%s" % eff.get("steps_total"))

    verdict = "pass" if all(c["match"] for c in checks) else "fail"
    report = {"verdict": verdict, "checks": checks, "gates": gates, "gate_note": gate_note}
    rep_path = os.path.join(os.path.dirname(args.result) or ".", "check_report.json")
    try:
        os.makedirs(os.path.dirname(rep_path) or ".", exist_ok=True)
        json.dump(report, open(rep_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass
    if args.write_back and r:
        try:
            r["checks"] = checks
            r["gates"] = gates
            r["verdict"] = verdict
            if gate_note:
                r["gate_note"] = gate_note
            res = r.setdefault("result", {})
            res.setdefault("client", {})
            json.dump(r, open(args.result, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as e:
            print("[check_all] WARN: 写回 result.json 失败: %s" % e)
    for c in checks:
        if not c["match"]:
            print("  - FAIL %s: %s" % (c["item"], c["detail"]))
    for k, v in gates.items():
        if v != "enforced":
            print("  - GATE %s=%s" % (k, v))
    print("[check_all] %s（%d 条校验，%d 闸门非 enforced）；退出码恒 0，结论见 result.json verdict"
          % (verdict.upper(), len(checks), len(warns)))
    return 0

def cmd_selftest(_a):
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        rp, cp, sp, ep, rv, cv = (os.path.join(td, n) for n in
                                  ("result.json", "case.json", "structure.json", "edits.jsonl", "revised.md", "client.html"))
        json.dump({"case_id": "T1", "output_contract": {"case_id": "", "status": "", "result": "", "claims": "", "uncertainties": ""}},
                  open(cp, "w", encoding="utf-8"))
        json.dump({"paragraphs": [{"pid": "P01", "text": "The results was significant."}]}, open(sp, "w", encoding="utf-8"))
        with open(ep, "w", encoding="utf-8") as f:
            f.write(json.dumps({"eid": "E001", "pid": "P01", "before": "The results was significant.",
                                "after": "The results were significant.", "status": "applied"}, ensure_ascii=False) + "\n")
        open(rv, "w", encoding="utf-8").write("The results were significant. [1]")
        open(cv, "w", encoding="utf-8").write("<html>client</html>")
        result = {"case_id": "T1", "status": "complete", "claims": [
            {"claim_id": "claim-E001", "kind": "reported", "source_id": "T1", "location": "P01",
             "evidence": [{"paragraph_id": "P01", "quote": "The results was significant."}]}],
            "result": {"client": {"embedded_html": "<html>client</html>", "features": ["f"] * 8}},
            "uncertainties": {"summary": "无"}, "changelog": [{"ts": "t", "action": "x"}]}
        json.dump(result, open(rp, "w", encoding="utf-8"), ensure_ascii=False)
        # 正例
        sys.argv = ["check_all", "--result", rp, "--case", cp, "--edits", ep, "--structure", sp,
                    "--revised", rv, "--client", cv, "--gain-evidence", os.path.join(td, "nope.json"),
                    "--write-back"]
        code = run_main()
        if code != 0:
            print("  [selftest] 退出码应恒为 0 FAIL"); ok = False
        r2 = json.load(open(rp, encoding="utf-8"))
        if not r2.get("checks") or not r2.get("gates"):
            print("  [selftest] checks/gates 未写回 FAIL"); ok = False
        if r2.get("verdict") not in ("pass", "fail"):
            print("  [selftest] verdict 未写回 FAIL"); ok = False
        # 反例1：锚点错位（before 不在原稿）→ verdict=fail，但退出码仍为 0
        ep2 = os.path.join(td, "e2.jsonl")
        with open(ep2, "w", encoding="utf-8") as f:
            f.write(json.dumps({"eid": "E999", "pid": "P01", "before": "NONEXISTENT TEXT XYZ", "after": "a", "status": "applied"}, ensure_ascii=False) + "\n")
        sys.argv = ["check_all", "--result", rp, "--case", cp, "--edits", ep2, "--structure", sp,
                    "--revised", rv, "--client", cv, "--gain-evidence", os.path.join(td, "nope.json")]
        if run_main() != 0:
            print("  [selftest] 反例1: 校验失败仍应退出 0 FAIL"); ok = False
        r3 = json.load(open(rp, encoding="utf-8"))
        if r3.get("verdict") != "fail":
            print("  [selftest] 反例1: 锚点错位应记 verdict=fail FAIL"); ok = False
        # 反例2：客户端嵌入与磁盘不一致 → verdict=fail，退出码仍为 0
        open(cv, "w", encoding="utf-8").write("<html>changed</html>")
        sys.argv = ["check_all", "--result", rp, "--case", cp, "--edits", ep, "--structure", sp,
                    "--revised", rv, "--client", cv, "--gain-evidence", os.path.join(td, "nope.json")]
        if run_main() != 0:
            print("  [selftest] 反例2: 校验失败仍应退出 0 FAIL"); ok = False
        r4 = json.load(open(rp, encoding="utf-8"))
        if r4.get("verdict") != "fail":
            print("  [selftest] 反例2: 嵌入不一致应记 verdict=fail FAIL"); ok = False
        # 反例3：污染输入（二进制 result.json）→ 不崩、退出 0
        badp = os.path.join(td, "bad.json")
        with open(badp, "wb") as f:
            f.write(b"\xff\xfe\x00garbage")
        sys.argv = ["check_all", "--result", badp, "--case", cp, "--edits", ep, "--structure", sp,
                    "--revised", rv, "--client", cv, "--gain-evidence", os.path.join(td, "nope.json")]
        if run_main() != 0:
            print("  [selftest] 反例3: 污染 result 应仍退出 0 FAIL"); ok = False
    print("[check_all] SELFTEST %s" % ("PASS" if ok else "FAIL"))
    # 退出码契约：自测失败也是内容级失败路径，退出码恒 0；
    # 结论以本行的 SELFTEST PASS/FAIL 为准，修复责任交回开发侧。
    return 0

def run_main():
    """selftest 专用：重置 argparse 后执行 main。"""
    import io, contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return main()
    except SystemExit as e:
        return int(e.code or 0)

if __name__ == "__main__":
    sys.exit(main())
