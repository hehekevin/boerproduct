#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schema_guard.py — result.json 结构守卫与包自检

职责（全部机械可判定，校验式存在性检查，不用 find|head -1）：
  1) result.json 可解析、含 case_id、output_contract 字段一个不缺（只增不删）；
  2) status 属于合法枚举；必需顶层键存在；
  3) --selftest：包结构自检——脚本齐备、SKILL.md frontmatter 合法且 ≤150 行、
     examples 带免责声明。
结论写 guard_report.json / stdout JSON；无论 PASS/FAIL 退出码恒为 0。
"""
import argparse
import json
import os
import re
import sys

SCRIPTS_EXPECTED = ["build_skeleton.py", "claim_split.py", "evidence_bind.py",
                    "strength_gate.py", "verify_check.py", "schema_guard.py",
                    "gain_probe.py"]
STATUS_ENUM = ("complete", "partial", "failed", "blocked", "in_progress")
FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S | re.M)


def load_json(p):
    try:
        return json.load(open(p, encoding="utf-8")), None
    except FileNotFoundError:
        return None, "file_missing"
    except Exception as e:
        return None, "parse_error: %s" % e



class _ArgParser(argparse.ArgumentParser):
    """参数错误也退出码 0：结论写 JSON，不以退出码表达成败（硬约束）。"""
    def error(self, message):
        print(json.dumps({"ok": False, "error": "argparse: %s" % message,
                          "note": "参数错误照实记录，退出码 0"}, ensure_ascii=False))
        self.exit(0)

def contract_fields(contract):
    if isinstance(contract, list):
        return [k for k in contract if isinstance(k, str)]
    if isinstance(contract, dict):
        for key in ("fields", "required", "required_fields", "output_contract"):
            v = contract.get(key)
            if isinstance(v, list):
                return [k for k in v if isinstance(k, str)]
            if isinstance(v, dict):
                return list(v.keys())
    return []


def guard(result, case):
    rows = []
    fields = contract_fields((case or {}).get("output_contract") or {})
    rows.append({"item": "case_id_present", "match":
                 bool(result.get("case_id")) and result["case_id"] != "unknown_case"})
    for f in fields:
        rows.append({"item": "contract_field:%s" % f,
                     "match": f in result, "gate": "enforced"})
    rows.append({"item": "status_valid", "match":
                 result.get("status") in STATUS_ENUM})
    for k in ("target_artifact", "fact_source_mapping", "version_and_boundary"):
        rows.append({"item": "bucket:%s" % k,
                     "match": k in result, "gate": "enforced"})
    rows.append({"item": "uncertainty_present", "match":
                 isinstance(result.get("uncertainty"), list)})
    return rows, fields


def selftest(pkg_dir):
    rows = []
    for s in SCRIPTS_EXPECTED:
        p = os.path.join(pkg_dir, "scripts", s)
        rows.append({"item": "script:%s" % s, "match": os.path.isfile(p)})
    sk = os.path.join(pkg_dir, "SKILL.md")
    ok_fm, ok_lines = False, False
    if os.path.isfile(sk):
        try:
            text = open(sk, encoding="utf-8").read()
            m = FRONTMATTER.match(text)
            ok_fm = bool(m and re.search(r"^name:\s*\S+", m.group(1), re.M)
                         and re.search(r"^description:\s*\S+", m.group(1), re.M))
            ok_lines = len(text.splitlines()) <= 150
        except Exception:
            pass
    rows.append({"item": "skill_frontmatter_valid", "match": ok_fm})
    rows.append({"item": "skill_lines_le_150", "match": ok_lines})
    ex = os.path.join(pkg_dir, "examples")
    ex_files = os.listdir(ex) if os.path.isdir(ex) else []
    disclaimer = False
    for fn in ex_files:
        if fn.lower().endswith((".md", ".json")):
            try:
                t = open(os.path.join(ex, fn), encoding="utf-8").read()
                if "示意" in t and "非正式" in t:
                    disclaimer = True
                    break
            except Exception:
                pass
    rows.append({"item": "examples_disclaimer", "match": disclaimer})
    return rows


def main():
    ap = _ArgParser()
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/guard_report.json")
    ap.add_argument("--pkg", default=None, help="包根目录（--selftest 用）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    try:
        if args.selftest:
            pkg = args.pkg or os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))
            rows = selftest(pkg)
            fails = sum(1 for r in rows if not r["match"])
            report = {"selftest": "PASS" if fails == 0 else "FAIL",
                      "fail_count": fails, "results": rows,
                      "note": "自检结论只写 JSON，退出码恒 0"}
            if args.out:
                os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
                json.dump(report, open(args.out, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
            print(json.dumps(report, ensure_ascii=False))
            return 0

        result, err1 = load_json(args.result)
        case, err2 = load_json(args.case)
        if err2:
            case = {}
        if result is None:
            report = {"ok": False, "error": err1 or "result 不可解析",
                      "note": "result.json 缺失/损坏，请先跑 build_skeleton.py 落骨架"}
        else:
            rows, fields = guard(result, case)
            fails = sum(1 for r in rows if not r["match"])
            report = {"ok": True, "verdict": "PASS" if fails == 0 else "FAIL",
                      "fail_count": fails, "contract_fields": len(fields),
                      "results": rows}
        if args.out:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        print(json.dumps(report, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e),
                          "note": "守卫失败照实记录，退出码 0"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
