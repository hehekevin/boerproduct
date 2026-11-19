#!/usr/bin/env python3
"""verify_check.py — 业务校验器（lib-file-organizer 最终自检）。

五组机械检查（analyze() 纯函数不写盘，ablate 参数支持逐项消融做增益对照）：
  rules      分类规则事前声明（declared_at 非空、规则非空、id 唯一、命名正则可编译）
             + 逐文件重放规则匹配，category 与重算不一致判 FAIL
  judged     覆盖完整性：每文件 judged=true（有 category+rule_hit 或 skip_reason），
             枚举合法（action/sha256_status/verdict/run_status.state/op.status）
  duplicates 重算 sha256 分组与 result.duplicates 比对；duplicate_of 指向正本；
             版本链成员哈希互异、按 mtime 升序
  audit      ops 链哈希逐条重算、prev_op_id 连续、每条有 replay、target 存在、
             非 keep 文件都有操作记录
  evidence   claims 证据回证：quote 在所指文件的 path/sha256/category 中逐字命中；
             duplicates/versions 引用的哈希必须真实存在于清单（unbacked_numbers）
校验结论写 verdict（organized/partially_organized/not_organized/cannot_verify），
退出码恒为 0——判据是报告 verdict 与 problems，不是退出码。

用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        --out /app/work/verify_check.json [--emit-into] [--dry-run] [--ablate rules,duplicates,audit]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

ACTION_ENUM = {"keep", "move", "rename", "move_rename", "merge", "skip", None}
SHA_ENUM = {"ok", "ok_inline", "no_content", "unreadable"}
VERDICT_ENUM = {"organized", "partially_organized", "not_organized", "cannot_verify"}
STATE_ENUM = {"success", "partial", "unable_to_determine", "refused", None}
OP_STATUS_ENUM = {"planned", "done", "failed", "skipped"}
OP_TYPE_ENUM = {"classify", "move", "rename", "merge", "register", "skip"}
ALL_GROUPS = ("rules", "judged", "duplicates", "audit", "evidence")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def norm_ws(s):
    return re.sub(r"\s+", "", str(s or ""))


def replay_rules(inner):
    """按事前规则重放归类，返回 {file_id: (期望 category, rule_hit)} 与规则问题。"""
    problems, expect = [], {}
    decl = inner.get("classification_rules") or {}
    if not decl.get("declared_at"):
        problems.append("分类规则未事前声明（declared_at 为空）：归类无据")
        return problems, expect
    rlist = sorted(decl.get("rules") or [], key=lambda r: (r.get("priority") or 999, str(r.get("rule_id"))))
    if not rlist:
        problems.append("分类规则列表为空")
    ids = [str(r.get("rule_id")) for r in rlist]
    if len(ids) != len(set(ids)):
        problems.append("rule_id 重复")
    conv = decl.get("naming_convention") or {}
    regex = conv.get("regex")
    if regex:
        try:
            re.compile(regex)
        except re.error as e:
            problems.append("命名规范 regex 无法编译: %s" % e)
    for r in rlist:
        if not (r.get("category")):
            problems.append("规则 %s 缺 category" % r.get("rule_id"))
        m = r.get("match") or {}
        if not any([m.get("ext"), m.get("path_contains"), m.get("name_contains")]):
            problems.append("规则 %s 三类匹配条件全空（永不命中）" % r.get("rule_id"))
    for f in inner.get("files") or []:
        if f.get("skip_reason"):
            continue
        path, name = f.get("path") or "", os.path.basename(f.get("path") or "")
        ext = f.get("file_type") or ""
        hit = None
        for r in rlist:
            m = r.get("match") or {}
            m_ext = {x.lower() if x.startswith(".") else "." + x.lower() for x in (m.get("ext") or [])}
            if (m_ext and ("." + ext.lower()) in m_ext) or \
               any(sub and sub in path for sub in (m.get("path_contains") or [])) or \
               any(sub and sub in name for sub in (m.get("name_contains") or [])):
                hit = r
                break
        expect[f.get("file_id")] = (str(hit["category"]) if hit else str(decl.get("fallback_category") or "unsorted"),
                                    str(hit["rule_id"]) if hit else "fallback")
    return problems, expect


def recompute_groups(inner):
    """重算重复组与版本链真值（独立于 duplicate_check 实现）。"""
    dup_true = {}
    by_hash = {}
    for f in inner.get("files") or []:
        if f.get("sha256") and str(f.get("sha256_status", "")).startswith("ok"):
            by_hash.setdefault(f["sha256"], []).append(f)
    for h, members in by_hash.items():
        if len(members) >= 2:
            members_sorted = sorted(members, key=lambda f: (f.get("mtime") or "9999", f.get("file_id")))
            dup_true[h] = {"keep_id": members_sorted[0]["file_id"],
                           "member_ids": sorted(f["file_id"] for f in members)}
    ver_true = {}
    tok = re.compile(r"[\s_\-.]*(v\d+|final|draft|copy|backup|old|new|rev\d*|定稿|终稿|初稿|草稿|修改稿?|副本|备份|旧版?|新版?|\(\d+\)|\[\d+\]|-\d{8}|_\d{8})[\s_\-.]*$", re.IGNORECASE)
    by_stem = {}
    for f in inner.get("files") or []:
        if f.get("duplicate_of"):
            continue
        stem = os.path.splitext(os.path.basename(f.get("path") or ""))[0]
        prev = None
        while prev != stem:
            prev = stem
            stem = tok.sub("", stem)
        stem = re.sub(r"[\s_\-.]+", "", stem).lower()
        if stem:
            by_stem.setdefault(stem, []).append(f)
    for s, members in by_stem.items():
        if len(members) >= 2 and len({f.get("sha256") for f in members}) >= 2:
            members_sorted = sorted(members, key=lambda f: (f.get("mtime") or "9999", f.get("file_id")))
            ver_true[s] = [f["file_id"] for f in members_sorted]
    return dup_true, ver_true


def analyze(result, case=None, ablate=()):
    """纯函数校验：返回 (problems, group_counts, metrics, coverage)。ablate 为关闭的检查组。"""
    problems = []
    counts = {g: 0 for g in ALL_GROUPS}
    metrics = {"rules_miss": 0, "judged_miss": 0, "dup_miss": 0, "version_miss": 0,
               "audit_miss": 0, "evidence_miss": 0}
    inner = result.get("result") if isinstance(result, dict) else None
    if not isinstance(inner, dict):
        return ["result 不是对象（骨架缺失）"], counts, metrics, {}
    files = inner.get("files") or []

    # ---- rules ----
    if "rules" not in ablate:
        r_probs, expect = replay_rules(inner)
        for p in r_probs:
            problems.append("[rules] " + p)
            counts["rules"] += 1
        for f in files:
            exp = expect.get(f.get("file_id"))
            if exp and not f.get("skip_reason"):
                if f.get("category") != exp[0]:
                    metrics["rules_miss"] += 1
                    problems.append("[rules] %s category=%s 与规则重放 %s 不一致"
                                    % (f.get("file_id"), f.get("category"), exp[0]))
                    counts["rules"] += 1
                elif f.get("rule_hit") != exp[1] and not (exp[1] == "fallback" and f.get("rule_hit") == "fallback"):
                    metrics["rules_miss"] += 1
                    problems.append("[rules] %s rule_hit=%s 与重放 %s 不一致"
                                    % (f.get("file_id"), f.get("rule_hit"), exp[1]))
                    counts["rules"] += 1

    # ---- judged（不可消融：覆盖底线）----
    total = len(files)
    judged = 0
    for f in files:
        ok = bool(f.get("skip_reason")) or (f.get("judged") and f.get("category") and f.get("rule_hit"))
        if f.get("judged") and not ok:
            problems.append("[judged] %s 标 judged 但缺 category/rule_hit/skip_reason" % f.get("file_id"))
            counts["judged"] += 1
            metrics["judged_miss"] += 1
        elif not ok:
            metrics["judged_miss"] += 1
            problems.append("[judged] %s 未判定（既无归类也无 skip_reason）" % f.get("file_id"))
            counts["judged"] += 1
        else:
            judged += 1
        if f.get("action") not in ACTION_ENUM:
            problems.append("[judged] %s action 枚举非法: %s" % (f.get("file_id"), f.get("action")))
            counts["judged"] += 1
        if f.get("sha256_status") not in SHA_ENUM:
            problems.append("[judged] %s sha256_status 枚举非法: %s" % (f.get("file_id"), f.get("sha256_status")))
            counts["judged"] += 1
        if f.get("action") == "merge" and not f.get("duplicate_of"):
            problems.append("[judged] %s action=merge 但无 duplicate_of" % f.get("file_id"))
            counts["judged"] += 1
        if (f.get("version_rank") is not None) != bool(f.get("version_group")):
            problems.append("[judged] %s version_group/version_rank 不成对" % f.get("file_id"))
            counts["judged"] += 1
    verdict_state = inner.get("run_status") or {}
    if verdict_state.get("state") is not None and verdict_state.get("state") not in STATE_ENUM:
        problems.append("[judged] run_status.state 枚举非法: %s" % verdict_state.get("state"))
        counts["judged"] += 1
    if inner.get("verdict") is not None and inner.get("verdict") not in VERDICT_ENUM:
        problems.append("[judged] verdict 枚举非法: %s" % inner.get("verdict"))
        counts["judged"] += 1

    # ---- duplicates / versions ----
    if "duplicates" not in ablate:
        dup_true, ver_true = recompute_groups(inner)
        declared = {d.get("hash"): d for d in inner.get("duplicates") or []}
        for h, t in dup_true.items():
            d = declared.get(h)
            if not d:
                metrics["dup_miss"] += 1
                problems.append("[duplicates] 重复组 %s… 漏登记" % str(h)[:12])
                counts["duplicates"] += 1
            else:
                if sorted(d.get("member_ids") or []) != t["member_ids"]:
                    metrics["dup_miss"] += 1
                    problems.append("[duplicates] 组 %s… 成员不符" % str(h)[:12])
                    counts["duplicates"] += 1
                if d.get("keep_id") != t["keep_id"]:
                    metrics["dup_miss"] += 1
                    problems.append("[duplicates] 组 %s… 正本应为 %s" % (str(h)[:12], t["keep_id"]))
                    counts["duplicates"] += 1
        for f in files:
            if f.get("duplicate_of"):
                d = (declared.get(f.get("sha256")) or {})
                if f["duplicate_of"] != d.get("keep_id"):
                    problems.append("[duplicates] %s duplicate_of 应为 %s" % (f.get("file_id"), d.get("keep_id")))
                    counts["duplicates"] += 1
        for v in inner.get("versions") or []:
            s = v.get("logical_name")
            true_order = ver_true.get(s)
            if not true_order:
                metrics["version_miss"] += 1
                problems.append("[duplicates] 版本链 %s 不成立（主干无多版本或哈希相同）" % s)
                counts["duplicates"] += 1
            elif v.get("order_by_mtime") != true_order:
                metrics["version_miss"] += 1
                problems.append("[duplicates] 版本链 %s 顺序与 mtime 重算不符" % s)
                counts["duplicates"] += 1
        for s in ver_true:
            if s not in {v.get("logical_name") for v in inner.get("versions") or []}:
                metrics["version_miss"] += 1
                problems.append("[duplicates] 版本链 %s… 漏登记" % s[:16])
                counts["duplicates"] += 1

    # ---- audit ----
    if "audit" not in ablate:
        ops = inner.get("ops") or []
        prev_hash, prev_id = "GENESIS", None
        file_ids = {f.get("file_id") for f in files}
        touched = set()
        for i, op in enumerate(ops):
            stored = op.get("chain_hash")
            check = {k: v for k, v in op.items() if k != "chain_hash"}
            expect = hashlib.sha256((prev_hash + canon(check)).encode("utf-8")).hexdigest()
            if stored != expect:
                metrics["audit_miss"] += 1
                problems.append("[audit] ops[%d] chain_hash 重算不符（断链）" % i)
                counts["audit"] += 1
            if op.get("prev_op_id") != prev_id:
                metrics["audit_miss"] += 1
                problems.append("[audit] ops[%d] prev_op_id 断链" % i)
                counts["audit"] += 1
            if not op.get("replay"):
                metrics["audit_miss"] += 1
                problems.append("[audit] ops[%d] 缺 replay 复放命令" % i)
                counts["audit"] += 1
            if op.get("op_type") not in OP_TYPE_ENUM or op.get("status") not in OP_STATUS_ENUM:
                problems.append("[audit] ops[%d] op_type/status 枚举非法" % i)
                counts["audit"] += 1
            if op.get("target_id") not in file_ids:
                problems.append("[audit] ops[%d] target_id 不在清单" % i)
                counts["audit"] += 1
            touched.add(op.get("target_id"))
            prev_hash, prev_id = stored, op.get("op_id")
        for f in files:
            if f.get("action") not in (None, "keep") and f.get("file_id") not in touched:
                metrics["audit_miss"] += 1
                problems.append("[audit] %s 有操作 %s 但审计链无记录" % (f.get("file_id"), f.get("action")))
                counts["audit"] += 1
        op_ids = [op.get("op_id") for op in ops]
        if len(op_ids) != len(set(op_ids)):
            problems.append("[audit] op_id 重复")
            counts["audit"] += 1

    # ---- evidence（claims 回证）----
    if "evidence" not in ablate:
        fmap = {f.get("file_id"): f for f in files}
        all_hashes = {f.get("sha256") for f in files if f.get("sha256")}
        for d in inner.get("duplicates") or []:
            if d.get("hash") not in all_hashes:
                metrics["evidence_miss"] += 1
                problems.append("[evidence] 重复组哈希 %s… 在清单中无回证" % str(d.get("hash"))[:12])
                counts["evidence"] += 1
        for c in result.get("claims") or []:
            src = fmap.get(c.get("source_id"))
            if src is None:
                continue
            blob = norm_ws("|".join([src.get("path") or "", src.get("sha256") or "",
                                     src.get("category") or "", src.get("file_type") or ""]))
            for ev in c.get("evidence") or []:
                q = norm_ws(ev.get("quote"))
                if q and q not in blob:
                    metrics["evidence_miss"] += 1
                    problems.append("[evidence] claim %s 证据未逐字回证（%s）"
                                    % (c.get("claim_id"), ev.get("paragraph_id")))
                    counts["evidence"] += 1

    coverage = {"total_files": total, "judged_files": judged, "classified": 0,
                "duplicates_groups": len(inner.get("duplicates") or []),
                "version_groups": len(inner.get("versions") or []),
                "skipped": sum(1 for f in files if f.get("skip_reason")),
                "ops_count": len(inner.get("ops") or []),
                "ratio": round(judged / total, 4) if total else None}
    coverage["classified"] = sum(1 for f in files if f.get("category") and not f.get("skip_reason"))
    return problems, counts, metrics, coverage


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 coverage/verdict/validator_verdict/self_check/gates/unbacked_numbers 写回 result.json")
        ap.add_argument("--dry-run", action="store_true")
        ap.add_argument("--ablate", default="", help="逗号分隔关闭的检查组（仅用于增益对照）")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败: %s" % e)
        return 0

    result = None
    try:
        result = load_json(args.result)
    except Exception as e:
        print("[verify_check] FAIL: result.json 读取/解析失败: %s（不中断交付）" % e)
        _dump(args.out, {"verdict": "FAIL", "problems": ["result.json 不可读: %s" % e]})
        return 0

    ablate = tuple(x.strip() for x in args.ablate.split(",") if x.strip())
    try:
        problems, counts, metrics, coverage = analyze(result, None, ablate)
    except Exception as e:
        problems, counts, metrics, coverage = (["analyze 异常: %s" % e],
                                               {g: 0 for g in ALL_GROUPS}, {}, {})
    verdict = "FAIL" if problems else "PASS"
    report = {"verdict": verdict, "ablate": list(ablate), "problems": problems,
              "group_counts": counts, "metrics": metrics, "coverage": coverage}
    _dump(args.out, report)

    # verdict 分级（业务语义，与 PASS/FAIL 独立）
    inner = result.get("result") or {}
    total = coverage.get("total_files") or 0
    judged = coverage.get("judged_files") or 0
    if total and judged == total and verdict == "PASS":
        v = "organized"
    elif judged > 0:
        v = "partially_organized"
    elif total:
        v = "not_organized"
    else:
        v = "cannot_verify"

    if args.emit_into:
        try:
            inner["coverage"] = coverage
            inner["verdict"] = v
            inner["verdict_basis"] = "%d/%d 文件已判定，校验器 %s（%s 组检查）" % (
                judged, total, verdict, "正常" if not ablate else "消融:" + ",".join(ablate))
            result["unbacked_numbers"] = [p for p in problems if p.startswith("[evidence]")]
            result["validator_verdict"] = verdict
            result["self_check"] = [
                {"item": "分类规则事前声明且逐文件可重放", "template_value": "rules problems=0",
                 "applied": "rules" not in ablate, "match": counts["rules"] == 0},
                {"item": "重复/版本按内容哈希判断", "template_value": "duplicates problems=0",
                 "applied": "duplicates" not in ablate, "match": counts["duplicates"] == 0},
                {"item": "操作审计链完整可复放", "template_value": "audit problems=0",
                 "applied": "audit" not in ablate, "match": counts["audit"] == 0},
                {"item": "证据逐字回证", "template_value": "evidence problems=0",
                 "applied": "evidence" not in ablate, "match": counts["evidence"] == 0},
            ]
            gates = [{"gate": "case_contract", "state": "enforced" if os.path.exists(args.case) else "not_found",
                      "note": "" if os.path.exists(args.case) else "case.json 缺失，契约字段按骨架保留"},
                     {"gate": "rules_declared", "state": "enforced" if (inner.get("classification_rules") or {}).get("declared_at") else "skipped_not_provided",
                      "note": "" if (inner.get("classification_rules") or {}).get("declared_at") else "规则未声明，归类不落库"},
                     {"gate": "hash_available", "state": "enforced" if any(
                         str(f.get("sha256_status", "")).startswith("ok") for f in inner.get("files") or []) else "skipped_not_provided",
                      "note": "" if any(str(f.get("sha256_status", "")).startswith("ok") for f in inner.get("files") or []) else "无可读文件内容，重复/版本判断降级为登记"}]
            result["gates"] = gates
            if not args.dry_run:
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("  WARN: 回写 result.json 失败: %s" % e)

    print("[verify_check] verdict=%s | 业务 verdict=%s | problems=%d | 组计数=%s | metrics=%s"
          % (verdict, v, len(problems), json.dumps(counts), json.dumps(metrics)))
    for p in problems[:30]:
        print("  - %s" % p)
    if len(problems) > 30:
        print("  ... 共 %d 处" % len(problems))
    print("[verify_check] 完成（退出码恒 0，判据是 verdict）")
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
        print("[verify_check] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
