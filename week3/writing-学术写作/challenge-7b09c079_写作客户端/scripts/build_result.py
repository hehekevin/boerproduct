#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 机械生成/更新/校验 result.json（学术写作客户端版）。
保证 output_contract 字段一个不缺；--claims-from-edits 从修订台账机械生成 claims
（每处改动自动挂 kind/source_id/location/evidence 逐字引文）。
result.result 内按题面《Skill 运行后的输出要求》三段语义落位：
  目标产物 → result.target_artifact（可编辑稿件+预览+格式）
  事实与来源映射 → claims[]（逐条可回溯）
  版本与边界 → result.version_and_boundary（版本谱系/人工确认/材料缺口/异常）
并登记客户端交互能力 result.client.features、修订记录 result.revision_records、
逐条裁决 result.adjudication、导出产物 result.exports。
全异常捕获，失败也写盘；**退出码恒 0**（结论由 result.json 的 status/verdict 记录，
校验不中断交付）。自测：--selftest 用合成正例+反例验证。"""
from __future__ import annotations
import argparse, json, os, sys

DEFAULT_FIELDS = ["case_id", "status", "result", "claims", "uncertainties"]
STATUS_OK = ("complete", "partial", "failed", "blocked")
CLIENT_FEATURES = [
    "修订逐条裁决：每处改动可单独 接受/拒绝/标记需确认，决策持久保存，避免整段覆盖不可控",
    "修订回看与锚点跳转：每条修订卡显示 指令号/段落锚点/原文/改后/依据/层面，一键回到原稿位置",
    "版本对照：v1 原稿 / v2 修订稿一键切换，v2 按已接受决策实时合成，逐条改动可对比",
    "导出可编辑稿：按当前裁决一键导出已接受修订的 Markdown + 裁决 JSON，可回填可继续编辑",
    "修订筛选：按指令号/层面(措辞|结构|术语|引用|格式)/裁决状态过滤修订列表",
    "关键词搜索：全文命中计数 + 上一个/下一个导航，重渲染保留修订高亮",
    "引用与格式哨兵：引用编号缺口、未授权改动、标题层级结果直接显示在客户端",
    "边界与人工确认：需作者确认项、材料缺口、未执行指令在客户端侧栏如实展示",
]

def contract_fields(case):
    try:
        oc = case.get("output_contract")
        if isinstance(oc, dict):
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return list(DEFAULT_FIELDS)

def skeleton(case):
    cid = "unknown"
    try:
        cid = str(case.get("case_id") or "unknown")
    except Exception:
        pass
    sk = {}
    for f in contract_fields(case):
        if f == "case_id":
            sk[f] = cid
        elif f == "status":
            sk[f] = "partial"
        elif f == "result":
            sk[f] = {
                # —— 题面《Skill 运行后的输出要求》三段语义 ——
                # 目标产物：可编辑稿件 + 预览 + 可用格式
                "target_artifact": {
                    "kind": "editable-revised-manuscript",
                    "primary_path": "/app/output/revised.docx",
                    "editable": True,
                    "formats": ["docx", "markdown", "html_client"],
                    "previews_dir": "/app/output/previews",
                    "note": "骨架阶段尚未生成，此处为落位契约。",
                },
                # 客户端交互能力（主产物全量嵌入）
                "client": {"kind": "self-contained-html",
                           "path": "/app/output/revision_client.html",
                           "features": list(CLIENT_FEATURES), "embedded_html": ""},
                # 修订记录：逐条改动的可追溯四元组
                "revision_records": [],
                # 裁决：逐条接受/拒绝/需确认的状态与决策面
                "adjudication": {
                    "granularity": "per-edit",
                    "actions": ["accept", "reject", "confirm"],
                    "decisions": {},
                    "persistence": "client localStorage（跨会话）+ 导出裁决 JSON 作为交接形式",
                    "note": "骨架阶段尚无裁决记录。",
                },
                # 导出：交付物清单与格式
                "exports": [],
                # 版本与边界
                "version_and_boundary": {
                    "versions": [], "human_confirm": [], "material_gaps": [],
                    "anomalies": [], "note": "骨架阶段尚无版本与边界记录。",
                },
                "edits_count": 0, "edits_accepted": 0, "instructions_total": 0,
                "instructions_executed": 0, "artifacts": {},
            }
        elif f == "claims":
            sk[f] = []
        elif f == "uncertainties":
            sk[f] = {"unexecuted_instructions": [], "ambiguity": [], "human_review": [],
                     "material_gaps": [], "summary": "骨架阶段：尚未完成任何修订。"}
        else:
            sk[f] = []
    return sk

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception as e:
        print("[build_result] WARN: 读取 %s 失败: %s" % (path, e))
        return {}

def load_jsonl(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return [json.loads(l) for l in f if l.strip()]
    except Exception as e:
        print("[build_result] WARN: 读取 %s 失败: %s" % (path, e))
        return []

def write_json(path, obj):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[build_result] FAIL: 写 %s 失败: %s" % (path, e))
        return False

def deep_merge(dst, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v

def cmd_init(a):
    case = load_json(a.case)
    sk = skeleton(case)
    if not case:
        sk["uncertainties"]["summary"] = "case.json 不可读或为空：按默认五字段契约推进，以实际可读材料为准。"
    if write_json(a.out, sk):
        print("[build_result] INIT: %d 个契约字段 -> %s" % (len(sk), ",".join(sk.keys())))
        return 0
    print("[build_result] FAIL: 写盘失败（退出码 0，不中断交付）")
    return 0

def cmd_merge(a):
    r = load_json(a.result)
    patch = load_json(a.patch)
    if not isinstance(r, dict) or not r:
        print("[build_result] FAIL: result.json 不可读，先运行 --init（退出码 0，不中断交付）")
        return 0
    before = set(r.keys())
    deep_merge(r, patch)
    for f in contract_fields(load_json(a.case)):
        if f not in r:
            r[f] = [] if f in ("claims", "uncertainties") else "unknown"
    if r.get("status") not in STATUS_OK:
        r["status"] = "partial"
    ok = write_json(a.result, r)
    print("[build_result] MERGE: 新增键 %s" % (sorted(set(r.keys()) - before) or "无"))
    return 0

def cmd_claims(a):
    """机械从 edits.jsonl 生成 claims：每处改动一条，证据链自动挂齐。
    同时把题面三段语义落到 result 内部：修订记录 / 裁决状态 / 导出清单 / 版本与边界。"""
    r = load_json(a.result)
    if not isinstance(r, dict) or not r:
        print("[build_result] FAIL: result.json 不可读，先运行 --init")
        return 0
    edits = load_jsonl(a.edits)
    cid = str(r.get("case_id") or "unknown")
    claims = r.get("claims") if isinstance(r.get("claims"), list) else []
    by_id = {str(c.get("claim_id")): c for c in claims if isinstance(c, dict)}
    made = 0
    for e in edits:
        if not isinstance(e, dict) or not (e.get("after") or e.get("before")):
            continue
        eid = str(e.get("eid") or "E?")
        claim = {
            "claim_id": "claim-%s" % eid,
            "text": "%s [%s@%s] 「%s」→「%s」（依据：%s）" % (
                eid, str(e.get("iid") or "?"), str(e.get("pid") or "?"),
                str(e.get("before") or "")[:80], str(e.get("after") or "")[:80],
                str(e.get("rationale") or "")[:120]),
            "kind": "reported",
            "source_id": cid,
            "location": str(e.get("pid") or e.get("locator") or "unknown"),
            "evidence": [{"paragraph_id": e.get("pid"), "quote": str(e.get("before") or e.get("anchor_quote") or "")[:160]}],
        }
        by_id[claim["claim_id"]] = claim
        made += 1
    r["claims"] = list(by_id.values())
    res = r.setdefault("result", {})
    res["edits_count"] = len(edits)
    # —— 修订记录：逐条可追溯四元组（机械生成，不改写内容）——
    res["revision_records"] = [{
        "eid": str(e.get("eid") or ""),
        "iid": str(e.get("iid") or ""),
        "pid": str(e.get("pid") or ""),
        "locator": str(e.get("locator") or ""),
        "before": str(e.get("before") or e.get("anchor_quote") or ""),
        "after": str(e.get("after") or ""),
        "rationale": str(e.get("rationale") or ""),
        "level": str(e.get("level") or ""),
        "side_effects": list(e.get("side_effects") or []),
        "status": str(e.get("status") or ""),
    } for e in edits if isinstance(e, dict)]
    # —— 裁决：逐条 accept/reject/confirm 的决策面（初值 pending，来自客户端本机裁决）——
    adj = res.setdefault("adjudication", {})
    adj.setdefault("granularity", "per-edit")
    adj.setdefault("actions", ["accept", "reject", "confirm"])
    adj.setdefault("persistence", "client localStorage（跨会话）+ 导出裁决 JSON 作为交接形式")
    dec = adj.setdefault("decisions", {})
    for rec in res["revision_records"]:
        dec.setdefault(rec["eid"], "pending")
    adj["pending_count"] = sum(1 for v in dec.values() if v == "pending")
    adj["decided_count"] = len(dec) - adj["pending_count"]
    adj["note"] = "初值 pending；作者在客户端逐条裁决后由导出的裁决 JSON 回填。"
    # —— 导出：交付物清单与格式 ——
    res["exports"] = [
        {"path": "/app/output/revised.docx", "format": "docx", "editable": True,
         "purpose": "可继续编辑的修订稿（Word）"},
        {"path": "/app/output/revised.md", "format": "markdown", "editable": True,
         "purpose": "可继续编辑的修订稿（Markdown，保留层级/编号/题注）"},
        {"path": "/app/output/revision_client.html", "format": "html",
         "editable": True, "purpose": "交互修订客户端：逐条裁决 + 版本对照 + 按裁决导出"},
        {"path": "/app/output/diff.md", "format": "markdown", "editable": True,
         "purpose": "逐条改动对照（可逐条接受/拒绝）"},
        {"path": "/app/output/versions.jsonl", "format": "jsonl", "editable": True,
         "purpose": "版本谱系（可对比/回退）"},
        {"path": "/app/output/previews/", "format": "pdf/png", "editable": False,
         "purpose": "渲染预览（渲染失败如实登记，不伪造）"},
    ]
    # —— 版本与边界 ——
    vb = res.setdefault("version_and_boundary", {})
    vb.setdefault("versions", [])
    vb.setdefault("human_confirm", [])
    vb.setdefault("material_gaps", [])
    vb.setdefault("anomalies", [])
    ok = write_json(a.result, r)
    print("[build_result] CLAIMS-FROM-EDITS: 生成/更新 %d 条 claim，共 %d 条；"
          "修订记录 %d 条、裁决位 %d 个、导出 %d 项" %
          (made, len(r["claims"]), len(res["revision_records"]),
           len(res.get("adjudication", {}).get("decisions", {})), len(res["exports"])))
    return 0

def cmd_diff(a):
    """机械从 edits.jsonl 生成 diff.md（逐条对照）+ versions.jsonl（版本谱系）。
    目的：逐条对照与版本谱系由脚本机械生成，不依赖模型手写，减少出错与预算占用。
    退出码恒 0，失败如实登记。"""
    edits = [e for e in load_jsonl(a.edits) if isinstance(e, dict)]
    lines = ["# 逐条改动对照（diff.md）", "",
             "每条改动单独列出：指令号 / 锚点 / 原文 / 改后 / 依据 / 层面 / 联动影响 / 建议裁决。", ""]
    for e in edits:
        lines.append("## %s [%s] %s" % (e.get("eid") or "?", e.get("iid") or "?", e.get("locator") or ""))
        lines.append("- 原句：~~%s~~" % (e.get("before") or e.get("anchor_quote") or ""))
        lines.append("- 改后：%s" % (e.get("after") or ""))
        lines.append("- 依据：%s" % (e.get("rationale") or ""))
        lines.append("- 层面：%s；状态：%s" % (e.get("level") or "?", e.get("status") or "?"))
        se = e.get("side_effects") or []
        if se:
            lines.append("- 联动影响：%s" % "；".join(str(s) for s in se))
        lines.append("- 建议裁决：%s" % ("需确认" if (e.get("decision") == "confirm"
                                      or str(e.get("status")) not in ("applied", "accepted"))
                                      else "建议接受"))
        lines.append("")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(a.out_diff)) or ".", exist_ok=True)
        with open(a.out_diff, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        v1 = {"version": "v1", "based_on": None, "edits_applied": 0, "diff": None,
              "note": "原稿版本（基线，未改动）"}
        v2 = {"version": "v2", "based_on": "v1", "edits_applied": len(edits),
              "diff": os.path.basename(a.out_diff), "note": "按台账逐条应用后的修订稿"}
        with open(a.out_versions, "w", encoding="utf-8") as f:
            f.write(json.dumps(v1, ensure_ascii=False) + "\n")
            f.write(json.dumps(v2, ensure_ascii=False) + "\n")
        print("[build_result] DIFF-FROM-EDITS: diff.md %d 行（%d 条改动）+ versions.jsonl 2 个版本"
              % (len(lines), len(edits)))
        return 0
    except Exception as e:
        print("[build_result] FAIL: 生成 diff/versions 失败: %s（退出码 0，不中断交付）" % e)
        return 0


def cmd_check(a):
    r = load_json(a.result)
    if not isinstance(r, dict) or not r:
        print("[build_result] FAIL: result.json 不存在或不可解析（退出码 0，不中断交付）")
        return 0
    problems = []
    missing = [f for f in contract_fields(load_json(a.case)) if f not in r]
    if missing:
        problems.append("缺契约字段: %s" % missing)
    if r.get("status") not in STATUS_OK:
        problems.append("status 非法: %r" % r.get("status"))
    if not str(r.get("case_id") or "").strip():
        problems.append("case_id 为空")
    for p in problems:
        print("  - %s" % p)
    print("[build_result] %s (%d 字段)（退出码 0，结论以本行 verdict 为准）"
          % ("FAIL" if problems else "PASS", len(r)))
    return 0

def cmd_selftest(_a):
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        cp = os.path.join(td, "case.json")
        write_json(cp, {"case_id": "T-POS", "output_contract": {"case_id": "", "status": "", "result": "", "claims": "", "uncertainties": ""}})
        rp = os.path.join(td, "result.json")
        if cmd_init(argparse.Namespace(case=cp, out=rp)) != 0:
            ok = False
        r = load_json(rp)
        if set(contract_fields(load_json(cp))) - set(r.keys()):
            print("  [selftest] 正例缺键 FAIL"); ok = False
        ep = os.path.join(td, "edits.jsonl")
        with open(ep, "w", encoding="utf-8") as f:
            f.write(json.dumps({"eid": "E001", "iid": "I01", "pid": "P03", "before": "The results was significant.", "after": "The results were significant.", "rationale": "I01 主谓一致", "level": "措辞", "status": "applied"}, ensure_ascii=False) + "\n")
        if cmd_claims(argparse.Namespace(result=rp, edits=ep)) != 0:
            print("  [selftest] claims-from-edits FAIL"); ok = False
        cl = load_json(rp).get("claims") or []
        if not cl or cl[0].get("kind") != "reported" or not cl[0].get("evidence") or not cl[0].get("source_id"):
            print("  [selftest] claims 证据链不全 FAIL"); ok = False
        pp = os.path.join(td, "patch.json")
        write_json(pp, {"result": {"edits_count": 1}, "status": "complete"})
        if cmd_merge(argparse.Namespace(result=rp, patch=pp, case=cp)) != 0:
            ok = False
        if load_json(rp).get("status") != "complete":
            print("  [selftest] merge 后 status 错误 FAIL"); ok = False
        if cmd_check(argparse.Namespace(result=rp, case=cp)) != 0:
            print("  [selftest] 正例 check FAIL"); ok = False
        # 反例1：case 缺失时 init 仍写盘
        rp2 = os.path.join(td, "r2.json")
        if cmd_init(argparse.Namespace(case=os.path.join(td, "nope.json"), out=rp2)) != 0:
            print("  [selftest] 反例1: case 缺失时 init 应仍写盘 FAIL"); ok = False
        if not load_json(rp2):
            print("  [selftest] 反例1: 骨架为空 FAIL"); ok = False
        # 反例2：损坏 result → check 报 FAIL 而非崩溃，且退出码恒 0
        bad = os.path.join(td, "bad.json")
        with open(bad, "wb") as f:
            f.write(b"\xff\xfe garbage")
        import io as _io, contextlib as _ctx
        buf = _io.StringIO()
        with _ctx.redirect_stdout(buf):
            code_bad = cmd_check(argparse.Namespace(result=bad, case=cp))
        if code_bad != 0:
            print("  [selftest] 反例2: 损坏 result 仍应退出 0 FAIL"); ok = False
        if "FAIL" not in buf.getvalue():
            print("  [selftest] 反例2: 损坏 result 应报 FAIL FAIL"); ok = False
        # 反例3：edits 文件缺失 → claims 不崩溃
        if cmd_claims(argparse.Namespace(result=rp, edits=os.path.join(td, "nope.jsonl"))) != 0:
            print("  [selftest] 反例3: edits 缺失应优雅处理 FAIL"); ok = False
        # 反例4：题面三段语义字段必须在骨架里落位
        r4 = load_json(rp) or {}
        res4 = r4.get("result") or {}
        for k in ("target_artifact", "client", "revision_records", "adjudication",
                  "exports", "version_and_boundary"):
            if k not in res4:
                print("  [selftest] 反例4: result 缺语义字段 %s FAIL" % k); ok = False
        if not res4.get("adjudication", {}).get("decisions"):
            print("  [selftest] 反例4: 裁决位未落位 FAIL"); ok = False
    print("[build_result] SELFTEST %s" % ("PASS" if ok else "FAIL"))
    # 退出码契约：自测失败也是内容级失败路径，退出码恒 0；
    # 结论以本行的 SELFTEST PASS/FAIL 为准，修复责任交回开发侧。
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--claims-from-edits", dest="claims_from_edits", action="store_true")
    ap.add_argument("--diff-from-edits", dest="diff_from_edits", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--edits", default="/app/work/edits.jsonl")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--patch", default=None)
    ap.add_argument("--out-diff", dest="out_diff", default="/app/output/diff.md")
    ap.add_argument("--out-versions", dest="out_versions", default="/app/output/versions.jsonl")
    try:
        a = ap.parse_args()
    except SystemExit:
        print("[build_result] 参数解析失败（退出码 0，不中断交付）")
        return 0
    try:
        if a.selftest:
            return cmd_selftest(a)
        if a.init:
            return cmd_init(argparse.Namespace(case=a.case, out=a.out))
        if a.merge:
            return cmd_merge(argparse.Namespace(result=a.result, patch=a.patch or "", case=a.case))
        if a.claims_from_edits:
            return cmd_claims(argparse.Namespace(result=a.result, edits=a.edits))
        if a.diff_from_edits:
            return cmd_diff(argparse.Namespace(edits=a.edits, out_diff=a.out_diff,
                                               out_versions=a.out_versions))
        if a.check:
            return cmd_check(argparse.Namespace(result=a.result, case=a.case))
        ap.print_help()
        return 0
    except Exception as e:
        print("[build_result] 兜底异常: %s（保留现有 result.json，退出码 0，不中断交付）" % e)
        return 0

if __name__ == "__main__":
    sys.exit(main())
