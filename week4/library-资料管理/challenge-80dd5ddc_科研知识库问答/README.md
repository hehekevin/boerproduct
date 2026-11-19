# kbqa-cite — 科研知识库问答 Skill（带句级来源引用与诚实缺证）

面向"科研知识库问答"场景的 Skill 包（Bohrium 第 4 期 · 科研资料管理赛道，challenge-80dd5ddc）。
对知识库条目（FAQ/文档/笔记/文件）完成**问题拆解 → 机械检索 → 逐问逐句带来源作答 → 未命中登记与缺口清单**，全部机检可回证。

## 1. 用途与场景
科研人员需要一个稳定完成多文件检索、带来源引用问答、证据回链与不确定性提示的工具。本 Skill 保证：答案里每个关键论断落到具体条目、具体正文位置；知识库没有依据的问题如实说"没有"并给缺口清单；他人拿记录能按引用回原文重新核对。

## 2. 适用与不适用边界
- **适用**：输入为条目集合（内联 JSON 或目录下文本文件）+ 问题清单；条目数 1–500；问题数 1–20；文本类条目（txt/md/csv/json/yaml 等）。
- **不适用**：外部数据库实时检索、全文翻译与语义精读、PDF 版式还原（扫描件只按不可读登记）、需要写入源知识库的整理操作。
- 不预置正式答案；examples 全部为合成数据并已标注示意。

## 3. 调用方式（平台运行时）
Skill 挂载于 `/skills/weekly-skill`，平台输入 `/input/case.json` + `task.md`，产出 `/app/output/result.json`。Agent 按 SKILL.md 七步流程线性执行：

```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json --input-root /input --out /app/output/result.json --work-dir /app/work
python3 /skills/weekly-skill/scripts/kb_index.py --result /app/output/result.json --case /input/case.json --work-dir /app/work
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json --case /input/case.json --work-dir /app/work --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json --case /input/case.json --out /app/work/schema_guard.json
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```

## 4. 输入输出约定
- **输入**：case.json（知识库条目键 kb_entries/entries/documents/notes/faqs/files…，问题键 questions/queries…，output_contract）+ /input 目录下的条目文件。以实际文件为准，不依标签假设。
- **输出**：/app/output/result.json，含 case_id 与 output_contract 全字段；核心结构：knowledge_base（条目盘点）/ questions（逐问拆解）/ answers（逐子问题、逐句带 source_entry+quote+quote_location）/ gaps（缺口清单）/ coverage / conflicts / steps / run_status / verdict / gain_evidence / efficiency。
- **失败与恢复**：所有脚本退出码恒为 0，结论看报告 verdict；任何中断都保证 result.json 存在（status=partial + 中断位置）。

## 5. 目录约定
```
SKILL.md            技能说明（七步流程 + 协议 + schema）
README.md           本文件（使用与方法说明）
worklog.md          开发对照记录（真实数字）
scripts/
  build_skeleton.py  Step0 骨架 + 知识库盘点 + 条目正文台账(/app/work/entries.json)
  kb_index.py        Step2 确定性检索（中文 2-gram+英文词，idf 加权）→ /app/work/retrieval.json
  verify_check.py    四组机检：答案句-来源对齐/拆解覆盖/未命中登记/claims 回证
  schema_guard.py    结构守卫（output_contract + 业务 schema）
  gain_probe.py      消融双跑 + 污染注入 → gain_evidence/efficiency
examples/
  example-case.json  合成案例（虚构条目与问题）
  example-result.json 示意输出（已标注非正式答案）
```

## 6. 依赖与版本
- Python ≥ 3.8，**仅标准库**（json/os/re/math/copy/time/argparse），零外部依赖，不装 pip 包。
- 不依赖任何个人文件或手工操作；脚本全捕获容错。

## 7. 配置
无必填配置。可选参数：kb_index `--topk`(默认 3) `--threshold`(默认 0.02)；verify_check `--ablate none|all|alignment,coverage,miss,evidence`；gain_probe `--emit-into` `--inject-pollution`。

## 8. 最小调用示例
见 `examples/` 与 SKILL.md「最小调用示例」节；示意输出 example-result.json 演示了 5 子问题（4 answered + 1 miss）的句级引用与缺口登记结构。

## 9. 最小自检清单（全部实测，见 worklog.md）
1. 5 个脚本 `python3 …` 运行退出码均 = 0（含输入缺失等失败路径）✔
2. verify_check 对 example-result.json 判 PASS（14 检查项全 applied）✔
3. schema_guard 判 PASS（结构完整）✔
4. gain_probe 消融双跑跑通，steps_count delta=14；污染副本注入 4 项被正常模式抓到（caught_by_normal_mode=true）✔
5. 篡改引文 fixture：verify_check 抓到「引文未回证到条目正文 + claims 无回证」2 处 FAIL ✔

## 10. 维护与扩展
- 改检索策略：只动 kb_index.py 的 tokens/score（保持不写 result.json 的键归属约定）。
- 改机检口径：verify_check.analyze 为纯函数，gain_probe 经 objective_violations 独立复算作漏检真值——两处需同步改口径。
- 新条目类型：build_skeleton 的 TEXT_EXTS 与 KB_KEYS 增补即可；条目正文超过 300KB 不入台账（引用降级为 claims 链内回证，闸门可见）。
- GitHub 公开链接：提交时由主控在提交目录根放置 GITHUB_URL.txt（本包不含，避免伪造链接）。

## 已知限制
- 词面检索只是召回策略，语义相关性须 Agent 逐条读原文核对（retrieval.json 内已注明）。
- 台账缺失时引文回证降级，alignment 真值口径放宽（boundaries 已声明）。
- 消融对照是本校验层 normal vs degraded，不等于平台基础 Agent 白板对照。
