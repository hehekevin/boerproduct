#!/usr/bin/env python3
"""make_example_deck.py — 生成最小调用示例（示意，非正式案例结果）。

运行: python3 examples/make_example_deck.py /app/work
产出: /app/work/deck.json + /app/work/evidence_map.jsonl（示例数据，
      quote 均为占位文本，实际运行时必须换成逐字来自论文原文的引用）
"""
import json
import os
import sys

DECK = {
    "deck_meta": {"title": "示例论文标题（示意，非正式案例）"},
    "slides": [
        {"no": 1, "role": "title", "layout": "title", "title": "示例论文标题",
         "subtitle": ["组会汇报 · 示意"], "notes": "开场强调工作定位；过渡到问题页；预判问题：与基线的区别。（示意）"},
        {"no": 2, "role": "result", "layout": "bullets", "title": "结果：成本降 X%，误差 Y% 内",
         "bullets": ["B-7 套件墙钟时间下降 61%", "相对误差保持 0.8% 以内", "流水线见 Fig.1"],
         "notes": "61% 与 0.8% 须逐字回证论文；过渡：代价是什么；预判问题：覆盖工况。（示意）"},
    ],
}
EV = [
    {"slide_no": 1, "claim": "工作名", "type": "section", "locator": "title p.1",
     "quote": "Adaptive Sampling for Sparse Scientific Workflows"},
    {"slide_no": 2, "claim": "主结果", "type": "quote", "locator": "§Results p.3",
     "quote": "AS-2 cut wall-clock time by 61% and kept relative error under 0.8%"},
]


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "deck.json"), "w", encoding="utf-8") as f:
        json.dump(DECK, f, ensure_ascii=False, indent=1)
    with open(os.path.join(outdir, "evidence_map.jsonl"), "w", encoding="utf-8") as f:
        for r in EV:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("example deck + evidence written to", outdir, "（示意，非正式案例结果）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
