#!/usr/bin/env python3
"""selftest_r5.py — r5 自测套件（正例 + 反例 + 退出码契约）。

覆盖：
  正例  完整示例通过全部校验（verdict=pass）
  反例  注入 N 类脏数据，逐类确认校验器抓到（verdict=fail）且**退出码恒为 0**
  契约  校验脚本在「文件缺失 / 非法 JSON / 空文件 / 目录」等失败路径上退出码均为 0
  幂等  同一输入连续跑两遍，gain_evidence 指纹与指标完全一致

用法：python3 selftest_r5.py [--dir DIR]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXAMPLE = os.path.join(ROOT, "resources", "example-result.json")
WORKORDER = os.path.join(ROOT, "resources", "example-workorder.json")


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except Exception as e:
        return -1, "", str(e)


def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def check_pipeline(res_path, work):
    cmd = [sys.executable, os.path.join(HERE, "run_pipeline.py"),
           "--result", res_path, "--workorder", WORKORDER,
           "--case", os.path.join(work, "no_such_case.json"),
           "--work", os.path.join(work, "out"), "--embed"]
    return run(cmd)


def read_report(work):
    p = os.path.join(work, "out", "check_report.json")
    try:
        return load(p)
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None)
    args = ap.parse_args()

    work = args.dir or tempfile.mkdtemp(prefix="r5selftest_")
    os.makedirs(work, exist_ok=True)
    results = []
    failures = []

    def record(name, ok, detail):
        results.append((name, ok, detail))
        print("  [%s] %-38s %s" % ("PASS" if ok else "FAIL", name, detail))

    # ---------- 正例 ----------
    base = os.path.join(work, "example-result.json")
    shutil.copy(EXAMPLE, base)
    rc, so, se = check_pipeline(base, work)
    rep = read_report(work)
    ok = (rc == 0 and rep.get("verdict") == "pass" and rep.get("ok") is True)
    record("正例_完整流水线通过", ok,
           "exit=%d verdict=%s problems=%d" % (rc, rep.get("verdict"), len(rep.get("problems") or [])))
    if not ok:
        failures.append("正例")
        print(so[-1500:])
    pos_report = rep

    # ---------- 正例：幂等（同输入两遍指纹与指标一致） ----------
    b1 = os.path.join(work, "idem1.json")
    b2 = os.path.join(work, "idem2.json")
    shutil.copy(EXAMPLE, b1)
    shutil.copy(EXAMPLE, b2)
    check_pipeline(b1, work)
    d1 = load(b1)
    check_pipeline(b2, work)
    d2 = load(b2)
    g1 = (d1.get("result") or {}).get("gain_evidence") or {}
    g2 = (d2.get("result") or {}).get("gain_evidence") or {}
    same_fp = g1.get("input_fingerprint") == g2.get("input_fingerprint")
    same_metrics = ([r.get("metrics") for r in g1.get("runs") or []] ==
                    [r.get("metrics") for r in g2.get("runs") or []])
    record("正例_幂等_两遍指纹与指标一致", same_fp and same_metrics,
           "fingerprint_equal=%s metrics_equal=%s runs=%d" % (
               same_fp, same_metrics, len(g1.get("runs") or [])))
    if not (same_fp and same_metrics):
        failures.append("幂等")

    # ---------- 反例：注入脏数据 ----------
    mutations = [
        ("反例_删一格", lambda d: d["result"]["matrix"].pop(3)),
        ("反例_数字与引文不符", lambda d: d["result"]["matrix"][4].__setitem__("value", 999.9)),
        ("反例_删pairwise双引文", lambda d: d["result"]["pairwise"][0].__setitem__("evidence", [])),
        ("反例_删gates", lambda d: d["result"].__setitem__("gates", [])),
        ("反例_coverage数字改错", lambda d: d["result"]["coverage"].__setitem__("cells", 99)),
        ("反例_删status_reason", lambda d: d.__setitem__("status_reason", "")),
        ("反例_删sources", lambda d: d.__setitem__("sources", [])),
        ("反例_删uncertainties分区", lambda d: d["uncertainties"].pop("unbacked", None)),
        ("反例_冲突缺归因", lambda d: d["result"]["synthesis"]["conflicts"][0].__setitem__("attribution", "")),
        ("反例_删顶层changelog", lambda d: d.pop("changelog", None)),
        ("反例_逐字回证失败_数字造假", lambda d: d["result"]["matrix"][6].__setitem__("value", 12345.6)),
    ]
    for name, mut in mutations:
        p = os.path.join(work, "bad.json")
        d = load(EXAMPLE)
        try:
            mut(d)
        except Exception as e:
            record(name, False, "注入失败: %s" % e)
            failures.append(name)
            continue
        save(p, d)
        rc, so, se = check_pipeline(p, work)
        rep = read_report(work)
        caught = rep.get("verdict") == "fail" and len(rep.get("problems") or []) > 0
        exit_ok = (rc == 0)
        ok = caught and exit_ok
        record(name, ok, "exit=%d verdict=%s problems=%d" % (
            rc, rep.get("verdict"), len(rep.get("problems") or [])))
        if not ok:
            failures.append(name)

    # ---------- 反例：只跑校验器（不经流水线重建），验证校验器自身抓错能力 ----------
    # 这三类若经 run_pipeline 会被流水线重建（gain_evidence/efficiency 是流水线产物），
    # 因此必须对校验器单独取证。
    direct_mutations = [
        ("反例_校验器单独_删gain_evidence", lambda d: d["result"].pop("gain_evidence", None)),
        ("反例_校验器单独_删efficiency", lambda d: d["result"].pop("efficiency", None)),
        ("反例_校验器单独_verification_match_false",
         lambda d: d["result"]["verification"][0].__setitem__("match", False)),
        ("反例_校验器单独_verification缺键",
         lambda d: d["result"]["verification"][0].pop("template_value", None)),
        ("反例_校验器单独_gates状态非法",
         lambda d: d["result"]["gates"][0].__setitem__("state", "passed")),
        ("反例_校验器单独_gates非enforced缺note",
         lambda d: (d["result"]["gates"][0].__setitem__("state", "not_found"),
                    d["result"]["gates"][0].__setitem__("gate_note", ""))),
        ("反例_校验器单独_gain_evidence只剩一遍",
         lambda d: d["result"]["gain_evidence"]["runs"].__setitem__(
             slice(1, None), [])),
        ("反例_校验器单独_gain_evidence缺full对照遍",
         lambda d: d["result"]["gain_evidence"]["runs"].__setitem__(
             slice(0, 1), [d["result"]["gain_evidence"]["runs"][1]])),
        ("反例_校验器单独_gain_evidence缺delta",
         lambda d: d["result"]["gain_evidence"].__setitem__("deltas", {})),
        ("反例_校验器单独_gain_evidence缺机制映射",
         lambda d: d["result"]["gain_evidence"].__setitem__("mechanism_map", [])),
        ("反例_校验器单独_gain_evidence缺verdict",
         lambda d: d["result"]["gain_evidence"].__setitem__("verdict", "")),
        ("反例_校验器单独_gain_evidence指纹非同输入",
         lambda d: d["result"]["gain_evidence"]["input_fingerprint"].__setitem__(
             "same_input_across_runs", False)),
        ("反例_校验器单独_gain_evidence缺边界",
         lambda d: d["result"]["gain_evidence"].__setitem__("boundary", [])),
        ("反例_校验器单独_gain_evidence缺失效条件",
         lambda d: d["result"]["gain_evidence"].__setitem__("failure_conditions", [])),
        ("反例_校验器单独_efficiency缺复现说明",
         lambda d: d["result"]["efficiency"].__setitem__("reproduce", "")),
        ("反例_校验器单独_efficiency缺采集口径",
         lambda d: d["result"]["efficiency"].__setitem__("collection_method", "")),
    ]
    for name, mut in direct_mutations:
        p = os.path.join(work, "bad_direct.json")
        d = load(EXAMPLE)
        try:
            mut(d)
        except Exception as e:
            record(name, False, "注入失败: %s" % e)
            failures.append(name)
            continue
        save(p, d)
        outp = os.path.join(work, "direct_report.json")
        cmd = [sys.executable, os.path.join(HERE, "check_result.py"),
               "--result", p, "--out", outp,
               "--workorder", WORKORDER,
               "--case", os.path.join(work, "no_such_case.json")]
        rc, so, se = run(cmd)
        try:
            rep = load(outp)
        except Exception:
            rep = {}
        caught = rep.get("verdict") == "fail" and len(rep.get("problems") or []) > 0
        ok = caught and rc == 0
        record(name, ok, "exit=%d verdict=%s problems=%d" % (
            rc, rep.get("verdict"), len(rep.get("problems") or [])))
        if not ok:
            failures.append(name)

    # ---------- 契约：失败路径退出码恒 0 ----------
    contract_cases = [
        ("契约_文件缺失", os.path.join(work, "does_not_exist.json"), None),
        ("契约_非法JSON", os.path.join(work, "broken.json"), "{not json"),
        ("契约_空文件", os.path.join(work, "empty.json"), ""),
    ]
    for name, path, content in contract_cases:
        if content is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        cmd = [sys.executable, os.path.join(HERE, "check_result.py"),
               "--result", path, "--out", os.path.join(work, "r.json"),
               "--case", os.path.join(work, "no_such_case.json")]
        rc, so, se = run(cmd)
        record(name + "_退出码为0", rc == 0, "exit=%d" % rc)
        if rc != 0:
            failures.append(name)

    # 目录当文件
    dpath = os.path.join(work, "adir")
    os.makedirs(dpath, exist_ok=True)
    cmd = [sys.executable, os.path.join(HERE, "check_result.py"),
           "--result", dpath, "--out", os.path.join(work, "r.json"),
           "--case", os.path.join(work, "no_such_case.json")]
    rc, so, se = run(cmd)
    record("契约_路径是目录_退出码为0", rc == 0, "exit=%d" % rc)
    if rc != 0:
        failures.append("契约_路径是目录")

    # 其他脚本失败路径
    for script, extra in (("gain_probe.py", []), ("efficiency_probe.py", []),
                          ("compare_matrix.py", []), ("run_pipeline.py", [])):
        cmd = [sys.executable, os.path.join(HERE, script),
               "--result", os.path.join(work, "nope.json")] + extra
        rc, so, se = run(cmd)
        record("契约_%s_失败路径退出码为0" % script, rc == 0, "exit=%d" % rc)
        if rc != 0:
            failures.append("契约_%s" % script)

    # ---------- 契约：命令行参数错误也必须 exit 0（argparse 默认会 exit 2） ----------
    for script in ("check_result.py", "compare_matrix.py", "gain_probe.py",
                   "efficiency_probe.py", "run_pipeline.py"):
        # (a) 未知参数
        cmd = [sys.executable, os.path.join(HERE, script), "--no-such-flag"]
        rc, so, se = run(cmd)
        record("契约_%s_未知参数退出码为0" % script, rc == 0, "exit=%d" % rc)
        if rc != 0:
            failures.append("契约_%s_未知参数" % script)
        # (b) 缺必填 --result
        cmd = [sys.executable, os.path.join(HERE, script)]
        rc, so, se = run(cmd)
        record("契约_%s_缺必填参数退出码为0" % script, rc == 0, "exit=%d" % rc)
        if rc != 0:
            failures.append("契约_%s_缺必填参数" % script)

    # ---------- 契约：参数错误时判定仍照实落盘（verdict=fail） ----------
    outp = os.path.join(work, "argerr_report.json")
    cmd = [sys.executable, os.path.join(HERE, "check_result.py"),
           "--no-such-flag", "--out", outp]
    rc, so, se = run(cmd)
    try:
        rep = load(outp)
    except Exception:
        rep = {}
    ok = (rc == 0 and rep.get("verdict") == "fail"
          and len(rep.get("problems") or []) > 0)
    record("契约_参数错误判定照实落盘", ok,
           "exit=%d verdict=%s problems=%d" % (
               rc, rep.get("verdict"), len(rep.get("problems") or [])))
    if not ok:
        failures.append("契约_参数错误判定照实落盘")

    # ---------- 契约：已交付示例的增益/效率数字可被脚本重算复现（字节级一致） ----------
    src = os.path.join(work, "reproduce.json")
    shutil.copy(EXAMPLE, src)
    rc, so, se = check_pipeline(src, work)
    try:
        a = load(EXAMPLE).get("result") or {}
        b = load(src).get("result") or {}
    except Exception:
        a, b = {}, {}
    for blk in ("gain_evidence", "efficiency"):
        same = (json.dumps(a.get(blk), sort_keys=True, ensure_ascii=False) ==
                json.dumps(b.get(blk), sort_keys=True, ensure_ascii=False))
        record("契约_示例_%s_可重算复现" % blk, same,
               "identical=%s" % same)
        if not same:
            failures.append("契约_示例_%s_可重算复现" % blk)

    # ---------- 反例：gain_evidence 数值不可信场景（污染后指纹必须变化） ----------
    p = os.path.join(work, "fingerprint.json")
    d = load(EXAMPLE)
    d["result"]["matrix"][0]["value"] = "污染值"
    save(p, d)
    check_pipeline(p, work)
    df = load(p)
    gf = (df.get("result") or {}).get("gain_evidence") or {}
    gbase = (load(EXAMPLE).get("result") or {}).get("gain_evidence") or {}
    changed = (gf.get("input_fingerprint") or {}).get("matrix_sha256") != \
              (gbase.get("input_fingerprint") or {}).get("matrix_sha256")
    record("反例_污染输入后指纹变化", changed,
           "fp=%s" % str((gf.get("input_fingerprint") or {}).get("matrix_sha256"))[:12])

    print("\n[selftest_r5] 共 %d 项，失败 %d 项" % (len(results), len(failures)))
    if failures:
        print("  失败项: %s" % ", ".join(failures))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[selftest_r5] 异常降级: %s" % e)
        sys.exit(0)
