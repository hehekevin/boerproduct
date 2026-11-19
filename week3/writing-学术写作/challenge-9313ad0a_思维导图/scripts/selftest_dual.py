#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest_dual.py — 本地双测 + 污染反例（真实运行，退出码恒 0）

三段测试：
  A) 正例：完整链路 init→extract→ledger→build→render→check→gain→embed→verify
  B) 退化对照：gain_evidence 内部 baseline vs full 两遍真实数字
  C) 污染反例：注入脏 src / 材料外 label / 删章节 / 删证据 → 校验器必须抓到，且退出码恒 0
"""
import json, os, shutil, subprocess, sys, tempfile, time

PKG = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(tempfile.gettempdir(), "mmtest")
PY = sys.executable
SD = os.path.join(PKG, "scripts")


def run(args, cwd=None):
    t0 = time.time()
    p = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    return {"rc": p.returncode, "out": (p.stdout or "").strip(),
            "err": (p.stderr or "").strip()[-600:], "sec": round(time.time() - t0, 2)}


def jrun(args, cwd=None):
    r = run(args, cwd)
    try:
        r["json"] = json.loads(r["out"].splitlines()[-1]) if r["out"] else None
    except Exception:
        r["json"] = None
    return r


COVERAGE = [
    {"sid": "M01", "locator": "M01:line5", "point": "血脑屏障限制药物递送", "kind": "core_concept"},
    {"sid": "M01", "locator": "M01:line9", "point": "转铁蛋白修饰脂质体", "kind": "method"},
    {"sid": "M01", "locator": "M01:line13", "point": "穿透率为对照组的3.2倍", "kind": "evidence"},
    {"sid": "M01", "locator": "M01:line17", "point": "小鼠模型与人体差异限制转化", "kind": "risk"},
    {"sid": "M01", "locator": "M01:line17", "point": "建议先开展大动物验证", "kind": "conclusion"},
    {"sid": "M01", "locator": "M01:line21", "point": "大动物验证成本高", "kind": "risk"},
    {"sid": "M02", "locator": "M02:line9", "point": "先做毒理预试验", "kind": "task"},
    {"sid": "M02", "locator": "M02:line9", "point": "毒理预试验由张三负责", "kind": "task"},
    {"sid": "M02", "locator": "M02:line13", "point": "毒理预试验延期将影响整体排期", "kind": "risk"},
    {"sid": "M01", "locator": "M01:line5", "point": "具有显著临床转化意义", "kind": "decorative"},
]
TREE = {
    "root": "血脑屏障纳米给药研究",
    "nodes": [
        {"id": "N01", "parent": None, "label": "血脑屏障限制药物递送", "type": "core_concept", "src": "M01", "note": "研究背景：血脑屏障限制药物递送"},
        {"id": "N02", "parent": "N01", "label": "转铁蛋白修饰脂质体", "type": "method", "src": "M01", "note": "方法：制备转铁蛋白修饰脂质体"},
        {"id": "N03", "parent": "N01", "label": "穿透率为对照组的3.2倍", "type": "evidence", "src": "M01", "note": "结果：n=12，p<0.05"},
        {"id": "N04", "parent": "N01", "label": "小鼠模型与人体差异限制转化", "type": "risk", "src": "M01", "note": "局限：模型外推限制"},
        {"id": "N05", "parent": "N01", "label": "建议先开展大动物验证", "type": "conclusion", "src": "M01", "note": "结论：建议先开展大动物验证"},
        {"id": "N06", "parent": "N05", "label": "大动物验证成本高", "type": "risk", "src": "M01", "note": "风险：大动物验证成本高、周期长"},
        {"id": "N07", "parent": "N01", "label": "毒理预试验由张三负责", "type": "task", "src": "M02", "note": "待办：毒理预试验由张三负责"},
        {"id": "N08", "parent": "N07", "label": "先做毒理预试验", "type": "task", "src": "M02", "note": "结论：先做毒理预试验"},
        {"id": "N09", "parent": "N08", "label": "毒理预试验延期将影响整体排期", "type": "risk", "src": "M02", "note": "风险：延期影响整体排期"},
    ],
}
RELS = [
    {"rel": "R01", "from": "N02", "to": "N03", "type": "causal",
     "basis": "M01:line13 转铁蛋白修饰脂质体使穿透率提升", "evidence_state": "fact"},
    {"rel": "R02", "from": "N04", "to": "N05", "type": "contrast",
     "basis": "M01:line17 小鼠模型局限，建议先做大动物验证", "evidence_state": "summary"},
    {"rel": "R03", "from": "N08", "to": "N09", "type": "dependency",
     "basis": "M02:line13 毒理预试验延期影响排期", "evidence_state": "fact"},
]
EVID = [
    {"nid": "N03", "type": "fact", "locator": "M01:line13", "quote": "穿透率为对照组的3.2倍"},
    {"nid": "N05", "type": "summary", "locator": "M01:line17", "quote": "建议先开展大动物验证"},
    {"nid": "N07", "type": "fact", "locator": "M02:line9", "quote": "毒理预试验由张三负责"},
    {"nid": "N09", "type": "fact", "locator": "M02:line13", "quote": "毒理预试验延期将影响整体排期"},
]


def wjsonl(p, rows):
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


FIXTURE_CASE = {
    "case_id": "demo-case-001",
    "task_instruction": "整理思维导图",
    "output_contract": {
        "case_id": "原样保留",
        "deliverable": "可编辑的目标文稿/结构化产物",
        "preserved_facts": "数字、条件、术语和来源不可凭空改变",
        "evidence_map": "关键论断到来源定位的映射",
        "change_log": "修改动作、原因、人工确认项和未解决问题",
    },
}
FIXTURE_PAPER = """# 血脑屏障纳米给药研究

## 研究背景

血脑屏障限制药物递送，转铁蛋白修饰脂质体可提升穿透率。

## 方法

制备转铁蛋白修饰脂质体，细胞摄取实验测定穿透率（n=12，p<0.05）。

## 结果

穿透率为对照组的3.2倍，显著高于游离药物组。

## 局限

小鼠模型与人体差异限制转化，建议先开展大动物验证。

## 风险

大动物验证成本高、周期长。
"""
FIXTURE_NOTES = """# 项目会议纪要

## 议题

讨论转铁蛋白修饰脂质体后续大动物验证方案。

## 结论

先做毒理预试验，再上大动物。

## 待办

毒理预试验由张三负责，2026年3月前完成。

## 风险

毒理预试验延期将影响整体排期。
"""


def setup_fixture():
    """自建合成输入（不依赖任何外部文件），保证脚本开箱即跑。"""
    ind = os.path.join(ROOT, "input", "materials")
    os.makedirs(ind, exist_ok=True)
    json.dump(FIXTURE_CASE, open(os.path.join(ROOT, "input", "case.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    open(os.path.join(ind, "paper.md"), "w", encoding="utf-8").write(FIXTURE_PAPER)
    open(os.path.join(ind, "notes.md"), "w", encoding="utf-8").write(FIXTURE_NOTES)


def main():
    setup_fixture()
    work = os.path.join(ROOT, "work")
    out = os.path.join(ROOT, "output")
    for d in (work, out):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
    rep = {"pkg": PKG, "tests": []}

    # ---------- A) 正例全链路 ----------
    steps = []
    steps.append(("init", jrun([PY, os.path.join(SD, "build_result.py"), "init",
                                "--case", os.path.join(ROOT, "input", "case.json"),
                                "--out", os.path.join(out, "result.json")])))
    steps.append(("extract", jrun([PY, os.path.join(SD, "extract_materials.py"),
                                   "--input", os.path.join(ROOT, "input"),
                                   "--outdir", os.path.join(work, "extracted")])))
    steps.append(("ledger", jrun([PY, os.path.join(SD, "fact_ledger.py"), "build",
                                  "--sources", os.path.join(work, "extracted"),
                                  "--out", os.path.join(work, "fact_ledger.jsonl")])))
    man = json.load(open(os.path.join(work, "extracted", "materials_manifest.json"), encoding="utf-8"))
    sid_of = {}
    for m in man["materials"]:
        sid_of["notes.md" if "notes" in m["path"] else "paper.md"] = m["id"]
    global PAPER, NOTES
    PAPER, NOTES = sid_of.get("paper.md", "M01"), sid_of.get("notes.md", "M02")
    for row in COVERAGE:
        row["sid"] = row["sid"].replace("M01", PAPER).replace("M02", NOTES)
        row["locator"] = row["locator"].replace("M01", PAPER).replace("M02", NOTES)
    for n in TREE["nodes"]:
        n["src"] = (PAPER if n["src"] == "M01" else NOTES)
    for r in RELS:
        r["basis"] = r["basis"].replace("M01", PAPER).replace("M02", NOTES)
    for e in EVID:
        e["locator"] = e["locator"].replace("M01", PAPER).replace("M02", NOTES)
    wjsonl(os.path.join(work, "coverage.jsonl"), COVERAGE)
    json.dump(TREE, open(os.path.join(work, "tree.json"), "w", encoding="utf-8"), ensure_ascii=False)
    wjsonl(os.path.join(work, "relations.jsonl"), RELS)
    wjsonl(os.path.join(work, "node_evidence.jsonl"), EVID)
    steps.append(("build", jrun([PY, os.path.join(SD, "map_build.py"),
                                 "--tree", os.path.join(work, "tree.json"),
                                 "--relations", os.path.join(work, "relations.jsonl"),
                                 "--evidence", os.path.join(work, "node_evidence.jsonl"),
                                 "--outdir", out])))
    steps.append(("render", jrun([PY, os.path.join(SD, "render_preview.py"),
                                  "--svg", os.path.join(out, "mindmap.svg"),
                                  "--outdir", os.path.join(out, "previews")])))
    steps.append(("check", jrun([PY, os.path.join(SD, "map_check.py"),
                                 "--coverage", os.path.join(work, "coverage.jsonl"),
                                 "--tree", os.path.join(work, "tree.json"),
                                 "--relations", os.path.join(work, "relations.jsonl"),
                                 "--evidence", os.path.join(work, "node_evidence.jsonl"),
                                 "--materials", os.path.join(work, "extracted"),
                                 "--out", os.path.join(out, "map_check.json")])))
    steps.append(("gain", jrun([PY, os.path.join(SD, "gain_evidence.py"),
                                "--tree", os.path.join(work, "tree.json"),
                                "--relations", os.path.join(work, "relations.jsonl"),
                                "--evidence", os.path.join(work, "node_evidence.jsonl"),
                                "--coverage", os.path.join(work, "coverage.jsonl"),
                                "--materials", os.path.join(work, "extracted"),
                                "--out", os.path.join(out, "gain_evidence.json")])))
    steps.append(("embed", jrun([PY, os.path.join(SD, "build_result.py"), "embed",
                                 "--case", os.path.join(ROOT, "input", "case.json"),
                                 "--out", os.path.join(out, "result.json"), "--auto",
                                 "--tree", os.path.join(work, "tree.json"),
                                 "--relations", os.path.join(work, "relations.jsonl"),
                                 "--evidence", os.path.join(work, "node_evidence.jsonl"),
                                 "--coverage", os.path.join(work, "coverage.jsonl"),
                                 "--ledger", os.path.join(work, "fact_ledger.jsonl"),
                                 "--outline", os.path.join(out, "outline.md"),
                                 "--check", os.path.join(out, "map_check.json"),
                                 "--render-log", os.path.join(out, "previews", "render_log.json"),
                                 "--gain", os.path.join(out, "gain_evidence.json"),
                                 "--artifact", os.path.join(out, "mindmap.mm"),
                                 "--artifact", os.path.join(out, "mindmap.opml"),
                                 "--artifact", os.path.join(out, "mindmap.svg"),
                                 "--artifact", os.path.join(out, "outline.md"),
                                 "--artifact", os.path.join(out, "previews", "mindmap.png"),
                                 "--script-calls", "9", "--steps", "5",
                                 "--set", "status=complete",
                                 "--uncertainty", "小鼠模型外推性需人工确认",
                                 "--changelog", "节点取舍与修改记录"])))
    steps.append(("verify", jrun([PY, os.path.join(SD, "build_result.py"), "verify",
                                  "--case", os.path.join(ROOT, "input", "case.json"),
                                  "--out", os.path.join(out, "result.json")])))
    rep["tests"].append({"name": "A_positive", "steps": [
        {"name": n, "rc": r["rc"], "sec": r["sec"], "json": r["json"],
         "err": r["err"][:200]} for n, r in steps]})
    res = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    rep["result_keys"] = sorted(res.keys())
    rep["contract_nonempty"] = {k: (len(res.get(k)) if isinstance(res.get(k), (list, dict, str))
                                    else res.get(k)) for k in
                                 ["deliverable", "preserved_facts", "evidence_map", "change_log"]}
    rep["verify_verdict"] = steps[-1][1]["json"]

    # ---------- B) 增益对照数字 ----------
    g = json.load(open(os.path.join(out, "gain_evidence.json"), encoding="utf-8"))
    rep["gain_runs"] = [{"arm": r["arm"], "verdict": r["verdict"], "fail": r["fail"],
                         "metrics": r["metrics"], "wall_seconds": r["wall_seconds"]}
                        for r in g.get("runs", [])]
    rep["gain_comparison"] = g.get("comparison")
    rep["gain_efficiency"] = g.get("efficiency")

    # ---------- C) 污染反例 ----------
    bad = os.path.join(ROOT, "bad")
    shutil.rmtree(bad, ignore_errors=True)
    os.makedirs(bad, exist_ok=True)
    btree = json.loads(json.dumps(TREE))
    btree["nodes"][0]["src"] = "M99"                       # 脏 src
    btree["nodes"][3]["label"] = "完全不在材料中的虚构节点"  # 材料外 label
    json.dump(btree, open(os.path.join(bad, "tree.json"), "w", encoding="utf-8"), ensure_ascii=False)
    brels = [dict(r) for r in RELS]
    brels[1].pop("basis")                                   # 关系无依据
    wjsonl(os.path.join(bad, "relations.jsonl"), brels)
    bevid = [e for e in EVID if e["nid"] != "N03"]          # 删证据
    wjsonl(os.path.join(bad, "node_evidence.jsonl"), bevid)
    wjsonl(os.path.join(bad, "coverage.jsonl"), COVERAGE)
    r_bad = jrun([PY, os.path.join(SD, "map_check.py"),
                  "--coverage", os.path.join(bad, "coverage.jsonl"),
                  "--tree", os.path.join(bad, "tree.json"),
                  "--relations", os.path.join(bad, "relations.jsonl"),
                  "--evidence", os.path.join(bad, "node_evidence.jsonl"),
                  "--materials", os.path.join(work, "extracted"),
                  "--out", os.path.join(bad, "map_check.json")])
    badrep = json.load(open(os.path.join(bad, "map_check.json"), encoding="utf-8"))
    rep["tests"].append({"name": "C_polluted", "rc": r_bad["rc"], "json": r_bad["json"],
                         "problems": [p.get("type") for p in badrep.get("problems", [])],
                         "fail": badrep.get("fail"),
                         "need_manual": len(badrep.get("need_manual") or [])})

    # C2) 缺文件 / 脏 JSON 反例（必须不崩、退出码 0）
    r_miss = jrun([PY, os.path.join(SD, "map_check.py"), "--tree",
                   os.path.join(bad, "nonexistent.json"), "--out",
                   os.path.join(bad, "check_missing.json")])
    open(os.path.join(bad, "broken.json"), "w", encoding="utf-8").write("{not json")
    r_broke = jrun([PY, os.path.join(SD, "map_check.py"), "--tree",
                    os.path.join(bad, "broken.json"), "--out",
                    os.path.join(bad, "check_broken.json")])
    r_bd = jrun([PY, os.path.join(SD, "build_result.py"), "embed", "--out",
                 os.path.join(bad, "result.json"), "--auto",
                 "--tree", os.path.join(bad, "broken.json"),
                 "--artifact", os.path.join(out, "mindmap.mm")])
    r_rn = jrun([PY, os.path.join(SD, "render_preview.py"), "--svg",
                 os.path.join(bad, "nope.svg"), "--outdir", os.path.join(bad, "prev")])
    rep["tests"].append({"name": "C2_degenerate", "cases": [
        {"name": "missing_tree", "rc": r_miss["rc"], "json": r_miss["json"]},
        {"name": "broken_json", "rc": r_broke["rc"], "json": r_broke["json"]},
        {"name": "embed_broken", "rc": r_bd["rc"], "json": r_bd["json"]},
        {"name": "render_no_svg", "rc": r_rn["rc"], "json": r_rn["json"]}]})

    # 产物清单
    rep["artifacts"] = sorted(os.listdir(out))
    rep["preview_files"] = sorted(os.listdir(os.path.join(out, "previews"))) \
        if os.path.isdir(os.path.join(out, "previews")) else []
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
