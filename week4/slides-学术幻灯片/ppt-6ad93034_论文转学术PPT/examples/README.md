# examples — 示意数据（非正式案例）

本目录所有文件均为**接口演示用示意数据，非正式案例结果，不冒充平台固定案例**。
正式案例由平台在评测时提供（/input/case.json + material.json + artifacts/slide-workorder.json + 实际 PPTX）。

| 文件 | 用途 |
|---|---|
| fake_input/material.json | 示意科研材料（含可回证数字），供 extract_source.py 演示 material_json 提取链 |
| deck.json | 示意页计划（3 页，generate 模式），数字均有 evidence 逐字回证 |
| evidence.jsonl | 示意证据映射（quote 逐字对应 material.json 原文） |

自检演示流程见 SKILL.md 第 3、4 节；跑 `extract_source.py examples/fake_input/material.json --outdir <dir>`
生成 source_text.txt 后，PLAN 闸门对 deck.json + evidence.jsonl 应得 verdict=pass。
