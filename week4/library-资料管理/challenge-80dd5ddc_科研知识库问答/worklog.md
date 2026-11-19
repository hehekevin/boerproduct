# worklog — kbqa-cite（challenge-80dd5ddc）

作者：w8-lib4 ｜ 日期：2026-11-19 ｜ 骨架参考：challenge-2dd1f64c（lit-screen-rank）

## 交付物
- SKILL.md（148 行，合法 YAML frontmatter：name=kbqa-cite）
- scripts/ 5 个：build_skeleton.py / kb_index.py / verify_check.py / schema_guard.py / gain_probe.py
- examples/ 2 个：example-case.json（合成案例，虚构条目）/ example-result.json（示意输出，标注非正式答案）
- README.md（生态十项 + 最小自检清单）
- 共 9 个文件，仅标准库，零外部依赖

## 领域设计（对应题面机检点）
| 机检点 | 实现 |
|---|---|
| 答案句-来源对齐（引用回证） | 每句 source_entry 必须存在 + quote 空白归一化后逐字回证条目正文台账（entries.json）；claims 链内 text+quote 双回证 |
| 检索未命中登记 | status=miss ⇒ miss_reason 非空 + gaps 登记（missing_topic/needed_action/kind）；partial 须显式声明缺口 |
| 问题拆解覆盖 | case 每问必须出现在 result.questions 且拆出子问题；每子问题必须有 answers 条目；coverage 计数与 ratio 机械复算 |
| 无来源句识别 | source_entry 为空/指向不存在条目 → FAIL（对齐组） |

## 真实对照数字（全部实测，2026-11-19，Python 3.13.14，Windows）
### 干净输入消融双跑（同输入 examples/example-case.json + example-result.json）
| 指标 | normal | degraded(--ablate all) | delta |
|---|---|---|---|
| alignment_missed | 0 | 0 | 0 |
| coverage_missed | 0 | 0 | 0 |
| miss_missed | 0 | 0 | 0 |
| evidence_missed | 0 | 0 | 0 |
| manual_review_items | 0 | 0 | 0 |
| steps_count | 21 | 7 | **14** |
| clarification_rounds | 0 | 0 | 0 |

干净输入四类漏检 delta=0 属预期：结果本身无违规可检（解释规则随 gain_evidence 落盘）；增益区分度由污染反例与篡改 fixture 证明。

### 污染反例副本（--inject-pollution，注入 4 项：无来源句+编造答案 / 清 miss_reason / 清 gaps / 清 claims）
| 指标 | polluted_normal | polluted_degraded | missed_detection_delta |
|---|---|---|---|
| problems | 8（FAIL） | 0（PASS） | **-8** |
| alignment_missed | 0 | 1 | **+1** |
| miss_missed | 0 | 1 | **+1** |
| evidence_missed | 2 | 6 | **+4** |

caught_by_normal_mode=true；原 result.json 未被修改。

### 篡改引文 fixture（Q1-1 首句 quote 改为"称取样品 5 g（篡改后的引文）"）
verify_check FAIL 2 处：「引文未回证到条目正文: E01」「claims 证据链无逐字回证」→ 台账级回证真实生效。

### exit 0 实测（失败路径全部不中断交付）
ablate=alignment/coverage/miss/evidence/all 各跑：exit=0；result.json 缺失（verify_check/schema_guard/gain_probe）：exit=0；case 缺失（build_skeleton/kb_index）：exit=0。干净链路：verify_check PASS（14 检查项）→ schema_guard PASS → gain_probe 双跑 → 复检 PASS，全程 exit=0。

### 效率计数（gain_probe 自动采集）
wall_clock_seconds_total=0.0084；entries_with_content=6；subquestions_total=5；manual_review_items normal/degraded=0/0；checker_runs=2。

## 硬约束自检（逐条）
1. SKILL.md 148 行 ≤150，frontmatter 仅 name+description ✔
2. 脚本 5 个 ≤8；文件 9 个 ≤50；包体积远小于 2MB；python3 命令 ✔
3. 挂载 /skills/weekly-skill；输入 /input/case.json；产出 /app/output/result.json（含 case_id 与 output_contract 全字段，build_skeleton 自动回填缺失契约键）✔
4. 所有失败路径 exit 0，语义值写 verdict/problems ✔（实测见上）
5. 未预置正式答案；examples 标注示意（_note 字段 + README 声明）✔
6. 定位标志文件校验式命中：entries.json / retrieval.json 台账缺失时闸门 entries_manifest / retrieval_index 记 not_found 并 warn「下游不得宣称已核对」✔
7. 多脚本键归属互斥（SKILL.md 明文约定）；kb_index 用正则切词不用 str.isalpha（汉字 isalpha()==True 陷阱）✔

## 诚实边界
- 干净输入消融 delta=0：增益区分度靠污染副本与篡改 fixture 证明，不在干净结果上编造指标差。
- 增益对照是本校验层 normal vs degraded，不是平台基础 Agent 白板对照；白板由平台生成。
- 台账（entries.json）缺失时引文回证降级为 claims 链内回证，alignment 真值口径放宽——闸门可见，交付说明须注明。
- 词面检索（2-gram + idf）只是召回策略，不解决语义相关性；Agent 须逐条读原文核对。
- 追问轮次按每轮 3 条折算，估计量非实测。
- 本包不含 GITHUB_URL.txt（无真实链接，由主控提交时放置，避免伪造）。

## 剩余风险
- 正式案例的条目键名/问题键名若不在常见键列表内，build_skeleton 会 WARN 并要求 Agent 手工兜底（协议第 1/2 条覆盖）。
- 若正式案例条目以非文本格式（PDF/二进制）提供且无预抽取文本层，台账将为空，回证降级——已在闸门与 boundaries 声明。
