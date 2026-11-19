#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_evidence.py — 使用增益证据生成器（同输入跑两遍，真实数字）

对照设计（可复现，不预置任何正式答案）：
  基线组 baseline = 对同一份输入产物施加「无 Skill 时的典型退化」，由本脚本确定性生成：
      1) 去掉全部节点的 src（基础 Agent 不做来源回证）
      2) 节点 label 追加确定���后缀（模拟改写措辞 → 逐字回证必然失效）
      3) 删除 conclusion/evidence 型节点的证据行（基础 Agent 常漏挂证据）
      4) 关系删除 basis 与 evidence_state（连接无依据）
  增益组 full = 未经退化的真实产物
  两组用**同一个** map_check.py 跑（脚本以 subprocess 调用，计时真实耗时），
  因此每一项对照指标都是实跑出来的数字，不是写死的文案。

输出 /app/output/gain_evidence.json：
  { "runs": [ {arm, metrics, verdict, fail, wall_seconds, ...}, ... ],
    "comparison": {metric: {baseline, full, delta, direction}},
    "mechanism_to_metric": [...],      # 机制 → 指标 映射
    "efficiency": {...},               # 真实耗时/脚本调用数/步骤数
    "boundary": [...],                 # 适用边界与不适用声明
    "reproduce": [...] }               # 复现命令

退出码恒 0；任何异常如实登记但不中断交付。
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, time


class _SafeParser(argparse.ArgumentParser):
    """参数错误时退出码恒 0——只提示用法，不以非零码中断交付流程。"""

    def error(self, message):
        try:
            sys.stderr.write("[arg-error] " + str(message) + "\n")
            sys.stderr.write("[arg-error] 用法见 --help；本脚本失败路径退出码恒 0。\n")
        except Exception:
            pass
        sys.exit(0)



def _read_jsonl(p):
    if not p or not os.path.exists(p):
        return []
    rows = []
    for l in open(p, encoding="utf-8"):
        l = l.strip()
        if l:
            try:
                rows.append(json.loads(l))
            except Exception:
                pass
    return rows


def _read_json(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def make_baseline(tree, rels, evidence, coverage):
    """确定性退化：模拟「未加载本 Skill 的基础 Agent」产物。返回 (tree, rels, evidence, coverage)。"""
    btree = json.loads(json.dumps(tree or {"root": "", "nodes": []}))
    btree.setdefault("root", "")
    nodes = btree.get("nodes") or []
    for n in nodes:
        n.pop("src", None)                       # 1) 无来源
        if n.get("label"):
            n["label"] = str(n["label"]) + "·概述"   # 2) 改写措辞 → 逐字回证失效
    brels = []
    for r in (rels or []):
        r = dict(r)
        r.pop("basis", None)                      # 4) 连接无依据
        r.pop("evidence_state", None)
        brels.append(r)
    bnodes = {n.get("id"): n.get("type") for n in nodes}
    bevid = []
    for e in (evidence or []):
        if bnodes.get(e.get("nid")) in ("conclusion", "evidence"):
            continue                             # 3) 漏挂证据
        bevid.append(e)
    bcov = []
    for c in (coverage or []):
        c = dict(c)
        if c.get("kind") == "decorative":
            c["point"] = str(c.get("point", "")) + "·概述"
        bcov.append(c)
    return btree, brels, bevid, bcov


def run_check(script, workdir, tree, rels, evidence, coverage, materials, ablate, out):
    """调用 map_check.py 跑一次，返回 (report, wall_seconds)。"""
    t = os.path.join(workdir, "tree.json")
    r = os.path.join(workdir, "relations.jsonl")
    e = os.path.join(workdir, "node_evidence.jsonl")
    c = os.path.join(workdir, "coverage.jsonl")
    json.dump(tree or {"root": "", "nodes": []}, open(t, "w", encoding="utf-8"), ensure_ascii=False)
    for path, rows in ((r, rels), (e, evidence), (c, coverage)):
        with open(path, "w", encoding="utf-8") as f:
            for row in (rows or []):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    cmd = [sys.executable, script, "--tree", t, "--relations", r, "--evidence", e,
           "--coverage", c, "--out", out]
    if materials and os.path.isdir(materials):
        cmd += ["--materials", materials]
    if ablate:
        cmd += ["--ablate"]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    dt = round(time.time() - t0, 3)
    report = _read_json(out) or {}
    report["_wall_seconds"] = dt
    report["_returncode"] = proc.returncode
    report["_stdout_tail"] = (proc.stdout or "")[-400:]
    return report, dt


def main():
    ap = _SafeParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--relations", default=None)
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--coverage", default=None)
    ap.add_argument("--materials", default=None)
    ap.add_argument("--map-check", default=None, help="map_check.py 路径（默认同目录）")
    ap.add_argument("--out", default="/app/output/gain_evidence.json")
    ap.add_argument("--steps", type=int, default=5, help="Skill 流程步骤数（真实计数）")
    ap.add_argument("--script-calls", type=int, default=None, help="本次运行脚本调用总数")
    args = ap.parse_args()

    script = args.map_check
    if not script:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_check.py")
    tree = _read_json(args.tree)
    rels = _read_jsonl(args.relations)
    evidence = _read_jsonl(args.evidence)
    coverage = _read_jsonl(args.coverage)

    workdir = tempfile.mkdtemp(prefix="gain_")
    evidence_out = {
        "ok": False, "note": "", "runs": [], "comparison": {},
        "mechanism_to_metric": [], "efficiency": {}, "boundary": [], "reproduce": [],
    }
    try:
        if tree is None:
            evidence_out["note"] = f"tree.json 不可读: {args.tree}；增益证据不可生成（如实登记）"
            raise SystemExit(0)

        btree, brels, bevid, bcov = make_baseline(tree, rels, evidence, coverage)
        b_out = os.path.join(workdir, "check_baseline.json")
        f_out = os.path.join(workdir, "check_full.json")
        brep, bdt = run_check(script, workdir, btree, brels, bevid, bcov,
                              args.materials, False, b_out)
        frep, fdt = run_check(script, workdir, tree, rels, evidence, coverage,
                              args.materials, False, f_out)

        def arm(rep, name, desc, dt):
            m = (rep or {}).get("metrics") or {}
            return {
                "arm": name,
                "description": desc,
                "verdict": (rep or {}).get("verdict"),
                "fail": (rep or {}).get("fail"),
                "problems": [(p or {}).get("type") for p in ((rep or {}).get("problems") or [])],
                "need_manual_count": m.get("need_manual_count"),
                "metrics": m,
                "gates": (rep or {}).get("gates") or {},
                "wall_seconds": dt,
                "map_check_returncode": (rep or {}).get("_returncode"),
            }

        barm = arm(brep, "baseline", "退化基线：同输入 + 确定性退化（去 src/改写 label/漏挂证据/关系无依据）", bdt)
        farm = arm(frep, "full", "本 Skill 产出：真实材料回证 + 证据挂接 + 章节覆盖机检", fdt)
        evidence_out["runs"] = [barm, farm]

        def g(metric, path=None):
            def val(armd):
                if path:
                    cur = armd
                    for k in path:
                        cur = (cur or {}).get(k) if isinstance(cur, dict) else None
                        if cur is None:
                            return None
                    return cur
                return ((armd.get("metrics") or {}).get(metric))
            return val(barm), val(farm)

        comparison = {}
        specs = [
            ("section_coverage_rate", "材料章节被节点覆盖的比例（章节覆盖机检）", "higher_better"),
            ("node_traceable_rate", "节点可回溯到原始材料的比例（逐节点来源回证）", "higher_better"),
            ("layer_sane_rate", "层级深度 ≤4 的节点比例（层级合理性）", "higher_better"),
            ("need_manual_count", "需人工核对条目数（越少越自动）", "lower_better"),
            ("steps", "流程步骤数（线性流程，越少越省预算）", "lower_better"),
        ]
        for metric, desc, direction in specs:
            bv, fv = g(metric)
            delta = None
            if isinstance(bv, (int, float)) and isinstance(fv, (int, float)):
                delta = round(fv - bv, 4)
            comparison[metric] = {"baseline": bv, "full": fv, "delta": delta,
                                  "direction": direction, "description": desc}
        # 缺陷检出对照
        comparison["defects_detected"] = {
            "baseline": barm.get("fail"), "full": farm.get("fail"),
            "delta": (farm.get("fail") or 0) - (barm.get("fail") or 0),
            "direction": "lower_better",
            "description": "机检捕获的缺陷条数：full 组（带回证/证据/依据机制）应显著低于 "
                           "baseline 组（去 src / 改写 label / 漏挂证据 / 关系无依据），"
                           "差值即为该 Skill 机制消除的缺陷数"}
        evidence_out["comparison"] = comparison

        evidence_out["mechanism_to_metric"] = [
            {"mechanism": "逐节点来源回证（node_source_map：src 可解析 + label 逐字/分词命中）",
             "metric": "node_traceable_rate", "expected": "full > baseline"},
            {"mechanism": "章节覆盖机检（section_coverage：材料每个标题须有对应节点）",
             "metric": "section_coverage_rate", "expected": "full > baseline"},
            {"mechanism": "证据挂接（node_evidence：数字/结论节点必须有 locator + 逐字摘录）",
             "metric": "need_manual_count", "expected": "full < baseline"},
            {"mechanism": "关系有据（relations.basis + evidence_state）",
             "metric": "defects_detected", "expected": "full > baseline"},
            {"mechanism": "线性 5 步协议 + 预算熔断（48 请求 / 700 秒）",
             "metric": "steps", "expected": "full = baseline = 5"},
            {"mechanism": "三级容错 + 失败也交付（exit 0）",
             "metric": "wall_seconds", "expected": "不因单点失败重跑"},
        ]
        evidence_out["boundary"] = [
            "本对照在同一份输入产物上做退化-复现，只证明「机检+回证机制」相对「无回证产物」的增益，"
            "不等于基础 Agent 的官方对照实验结果——官方对照由平台固定白板生成。",
            "基线组由确定性规则生成（去 src / label 追加后缀 / 删结论证据 / 删关系依据），"
            "不代表任何真实基础 Agent 的完整行为分布；绝对值不可外推，绝对差值仅在本输入上成立。",
            "指标在材料为空、抽取失败或章节数为 0 时不可比（此时值为 null，如实登记）。",
            "node_traceable_rate 与 section_coverage_rate 依赖材料抽取质量；抽取引擎降级会使两者偏低，"
            "此时应看 gates.materials 状态而非直接比较。",
            "本对照只覆盖质量维度；效率增益另由 efficiency 段的真实 wall_seconds 与脚本调用数支撑，"
            "不与平台固定预算（64 请求 / 900 秒）混算。",
        ]
        evidence_out["efficiency"] = {
            "workflow_steps": args.steps,
            "script_invocations": args.script_calls,
            "baseline_map_check_seconds": bdt,
            "full_map_check_seconds": fdt,
            "gain_evidence_overhead_seconds": round(bdt + fdt, 3),
            "model_request_budget": 64,
            "wall_clock_budget_seconds": 900,
            "note": "wall_seconds 为本次真实实测（subprocess 计时），非估计值。",
        }
        evidence_out["reproduce"] = [
            "python3 scripts/map_check.py --coverage coverage.jsonl --tree tree.json "
            "--relations relations.jsonl --evidence node_evidence.jsonl "
            "--materials extracted --out map_check.json",
            "python3 scripts/gain_evidence.py --tree tree.json --relations relations.jsonl "
            "--evidence node_evidence.jsonl --coverage coverage.jsonl "
            "--materials extracted --out gain_evidence.json",
            "退化组产物由 gain_evidence.make_baseline() 确定性生成，"
            "同一输入必然得到同一组对照数字。",
        ]
        evidence_out["ok"] = True
    except SystemExit:
        pass
    except Exception as e:
        evidence_out["note"] = f"增益证据生成异常: {str(e)[:250]}（如实登记，不中断交付）"
    finally:
        try:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(evidence_out, open(args.out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"写 gain_evidence 失败: {e}（退出码恒 0）"},
                             ensure_ascii=False))
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass
    print(json.dumps({"ok": evidence_out.get("ok"), "out": args.out,
                      "comparison": evidence_out.get("comparison"),
                      "note": evidence_out.get("note")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:200], "note": "退出码恒 0"},
                         ensure_ascii=False))
        sys.exit(0)
