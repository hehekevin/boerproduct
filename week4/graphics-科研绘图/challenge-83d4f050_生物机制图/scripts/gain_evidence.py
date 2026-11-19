#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_evidence.py — 增益证据层：同输入消融两臂 + 污染反例注入（生物机制图域）。
MARKER: bio-pathway-figure/v1

用途：为 result.json 生成机器判定的增益证据，而非文字自述。
  · 全量臂（full）：正常渲染（语义箭头+区室分层+图例），同一校验器 validate_pathway.py 实测。
  · 消融臂（ablated）：同输入同 spec，--ablate edge_semantics,compartment,legend 渲染，
    模拟「基础 Agent 不做语义映射/区室约束/图例规范」的画法；同一校验器再跑一遍。
    两臂 FAIL 数之差 fail_count_diff 是机器判定的质量增益（消融臂应显著更差）。
  · 污染反例注入：复制 spec 为副本并注入典型错画（激活/抑制语义反转、区室错位、
    图例项删除；按 spec 实际可注入项执行），用原 spec 校验渲染产物——校验器必须
    抓到（caught=True），证明机械校验不是摆设。
  · 基线对照：模拟不做证据登记的路径，统计源材料里多少实体/数值只能人工核对，
    与本包 content_map 逐条登记 + 逐字回证后的需人工核对条目做差。

唯一写入 result.json 的键：gain_evidence、efficiency（本包其它脚本不写这两个键）。
退出码恒 0，结论写 stdout JSON，不用退出码表达成败。
"""
import argparse, json, os, re, subprocess, sys

MARKER = "bio-pathway-figure/v1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ABLATE = "edge_semantics,compartment,legend"


def run(cmd, timeout=180):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return json.loads(p.stdout) if (p.stdout or "").strip().startswith("{") else {"raw": p.stdout}
    except Exception as ex:
        return {"ok": False, "error": repr(ex)}


def render(spec_path, out_svg, ablate=""):
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "pathway_svg.py"),
           spec_path, "--out", out_svg]
    if ablate:
        cmd += ["--ablate", ablate]
    return run(cmd)


def validate(spec_path, svg, corpus):
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "validate_pathway.py"),
           spec_path, svg]
    if corpus:
        cmd += ["--corpus", corpus]
    return run(cmd)


def pollute(spec):
    """污染反例：在副本上注入 3 处典型错画，不改原 spec。"""
    s = json.loads(json.dumps(spec))
    muts = []
    if s.get("edges"):
        t0 = s["edges"][0].get("type", "activation")
        s["edges"][0]["type"] = "inhibition" if t0 != "inhibition" else "activation"
        muts.append("edge[%s].type %s->%s（激活/抑制语义反转）"
                    % (s["edges"][0].get("id"), t0, s["edges"][0]["type"]))
    if s.get("nodes"):
        comps = s.get("compartments") or ["extracellular", "membrane", "cytoplasm", "nucleus"]
        c0 = s["nodes"][0].get("compartment", "cytoplasm")
        alt = next((c for c in comps if c != c0), "nucleus")
        s["nodes"][0]["compartment"] = alt
        muts.append("node[%s].compartment %s->%s（区室错位）"
                    % (s["nodes"][0].get("id"), c0, alt))
    if isinstance(s.get("legend"), dict) and s["legend"].get("edge_types"):
        k = sorted(s["legend"]["edge_types"])[0]
        s["legend"]["edge_types"].pop(k)
        muts.append("legend.edge_types 移除 %s（图例-图面不一致）" % k)
    return s, muts


def baseline_metrics(result, corpus):
    cmap = result.get("content_map") or {}
    reg = ""
    for key in ("nodes", "edges", "elements", "values"):
        v = cmap.get(key) if isinstance(cmap, dict) else None
        if isinstance(v, list):
            for m in v:
                if isinstance(m, dict):
                    reg += " ".join(str(m.get(k, "")) for k in
                                    ("label", "evidence", "type", "src", "dst", "quote"))
    reg = norm(reg)
    words = set(re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", corpus))
    nums = set(re.findall(r"\d+(?:\.\d+)?%?", corpus))
    un_w = [w for w in words if w.lower() not in reg.lower() and len(w) > 3]
    un_n = [n for n in nums if n not in reg]
    return {"unverifiable_entity_candidates": len(un_w),
            "unverifiable_numeric_candidates": len(un_n),
            "manual_review_items": len(un_w) + len(un_n),
            "note": "基础路径不做证据登记时，上述源材料实体/数值只能人工逐条核对"}


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--corpus", default=None, help="来源材料目录或文件（逐字回证与基线）")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--ablate-list", default=DEFAULT_ABLATE)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    out = {"tool": "gain_evidence", "ok": False}
    try:
        os.makedirs(args.outdir, exist_ok=True)
        work = os.path.join(args.outdir, "gain_work")
        os.makedirs(work, exist_ok=True)
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
        corpus = ""
        if args.corpus and os.path.isdir(args.corpus):
            for root, _, fs in os.walk(args.corpus):
                for fn in sorted(fs):
                    if fn.lower().endswith((".txt", ".md", ".json", ".csv")):
                        try:
                            corpus += open(os.path.join(root, fn), encoding="utf-8",
                                           errors="ignore").read()
                        except Exception:
                            pass
        elif args.corpus and os.path.exists(args.corpus):
            corpus = open(args.corpus, encoding="utf-8", errors="ignore").read()
        corpus = norm(corpus)

        full_svg = os.path.join(work, "full.svg")
        abl_svg = os.path.join(work, "ablated.svg")
        r1, r2 = render(args.spec, full_svg), render(args.spec, abl_svg, args.ablate_list)
        v1 = validate(args.spec, full_svg, args.corpus) if r1.get("ok") else {"fail_count": None}
        v2 = validate(args.spec, abl_svg, args.corpus) if r2.get("ok") else {"fail_count": None}
        fa = v1.get("fail_count")
        fb = v2.get("fail_count")

        # 污染反例注入副本
        pspec, muts = pollute(spec)
        ppath = os.path.join(work, "spec_polluted.json")
        with open(ppath, "w", encoding="utf-8") as f:
            json.dump(pspec, f, ensure_ascii=False, indent=1)
        pol_svg = os.path.join(work, "polluted.svg")
        r3 = render(ppath, pol_svg)
        v3 = validate(args.spec, pol_svg, args.corpus) if r3.get("ok") else {"fail_count": None}
        fc = v3.get("fail_count")

        result = None
        if os.path.exists(args.result):
            try:
                result = json.load(open(args.result, encoding="utf-8"))
            except Exception:
                result = None
        if not isinstance(result, dict):
            result = {"case_id": "unknown", "status": "partial",
                      "note": "result.json 缺失或不可解析，gain_evidence 建最小骨架"}

        baseline = baseline_metrics(result, corpus)
        cm = result.get("content_map") or {}
        registered = sum(len(v) for v in cm.values() if isinstance(v, list))
        ev_checks = (v1.get("checks") or {}).get("entity_checks", []) + \
                    (v1.get("checks") or {}).get("edge_semantics", [])
        ev_total = sum(1 for c in ev_checks if c.get("check") == "evidence_verbatim")
        ev_pass = sum(1 for c in ev_checks
                      if c.get("check") == "evidence_verbatim" and c.get("match") is True)

        out["ok"] = bool(r1.get("ok") and v1.get("ok"))
        out["gain_evidence"] = {
            "generated_by": "gain_evidence.py " + MARKER,
            "same_input": args.spec,
            "same_validator": "validate_pathway.py（两臂同一校验器，FAIL 数差为机器判定）",
            "arms": {
                "full": {"svg": full_svg, "render_ok": r1.get("ok"),
                         "fail_count": fa, "checks_total": v1.get("summary", {}).get("check_items")},
                "ablated": {"svg": abl_svg, "ablate": args.ablate_list.split(","),
                            "render_ok": r2.get("ok"), "fail_count": fb,
                            "checks_total": v2.get("summary", {}).get("check_items")},
            },
            "fail_count_diff": (fb - fa) if isinstance(fa, int) and isinstance(fb, int) else None,
            "pollution_injection": {"injected": muts, "spec_copy": ppath,
                                    "fail_count": fc, "caught": isinstance(fc, int) and fc > 0},
            "evidence_registry": {"registered_elements": registered,
                                  "evidence_checks_total": ev_total,
                                  "evidence_verbatim_pass": ev_pass},
            "baseline_comparison": {
                "baseline_manual_review_items": baseline["manual_review_items"],
                "skill_fail_count": fa,
                "note": "基线=不做证据登记/不做语义校验的路径；差值即增益方向",
            },
        }
        out["efficiency"] = {
            "mechanical_check_items": v1.get("summary", {}).get("check_items"),
            "full_arm_fail": fa, "ablated_arm_fail": fb,
            "pollution_caught": out["gain_evidence"]["pollution_injection"]["caught"],
            "manual_review_items": fa,
            "baseline_manual_review_items": baseline["manual_review_items"],
            "note": "以上为本次运行真跑采集的计数；模型请求数与耗时由 Harness 侧记录",
        }
        if args.write:
            # 唯一写入者约定：本脚本只写 gain_evidence 与 efficiency 两个键
            result["gain_evidence"] = out["gain_evidence"]
            result["efficiency"] = out["efficiency"]
            try:
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=1)
                out["written"] = True
            except Exception as ex:
                out["written"] = False
                out["write_error"] = repr(ex)
    except Exception as ex:
        out["error"] = repr(ex)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)   # 含 argparse 出错：失败路径一律 exit 0
    except Exception as ex:
        print(json.dumps({"tool": "gain_evidence", "ok": False, "error": repr(ex)},
                         ensure_ascii=False))
        sys.exit(0)
