# worklog — template-fit-skill 重做（ppt-710fbc72）

日期：2026-11-13 ｜ 执行者：redo-templatefit

## 一、瓶颈分析（历史 61→69→69→62，卡在 Solid 档）

1. **产物完整性不足**：旧版流程 6 阶段 + result.json 骨架协议不够强制，中途超时/失败时 result.json 字段残缺甚至缺失，评分器读不到 output_contract 全键与 case_id，直接掉档。
2. **可核验性不足**：旧版虽有 layout_log 逐页记录继承证据，但"模板原始值→应用值→依据"的适配决策链没有结构化嵌入 result.json——评分器主要读 result.json，仅给文件路径引用不够；且未明确禁止编造模板规范。
3. **效率损耗**：6 阶段非线性流程 + 10 个资源文件，Agent 执行时易在流程调度上消耗请求预算；缺少明确的预算熔断点，导致"快完成了却没交"。
4. **status 语义模糊**：旧版三级（complete/partial/failed）无法表达"输入缺失导致无法开始"的 blocked 场景。

## 二、本次重做策略（对照已验证方法）

| 已验证方法 | 应用位置 |
|---|---|
| 执行协议置顶（抄全键+case_id、立即写骨架、字段一个不缺） | SKILL.md「执行协议」6 条，置于主流程之前 |
| 广度优先 | 执行协议第 3 条：先全流程低配完整产物再精修 |
| 48 请求/700 秒熔断 | 执行协议第 4 条：到点即保存收口，status 如实降级 |
| 写盘前 JSON 自检、失败也写 result.json | 执行协议第 5、6 条 |
| 线性主流程 ≤5 步、SKILL.md ≤250 行、祈使句 | 6 阶段压缩为线性 5 步；SKILL.md 约 170 行 |
| 资源 ≤8 文件 | 10 个脚本精简为 7 脚本 + 1 参考 = 8 文件（脚本全部为已验证版本复用） |
| 主产物决策完整嵌入 result.json | 新增 `template_rule_map`（逐页：模板原始值→应用值→依据→inheritance）与 `font_color_layout_mapping`（字体/颜色/版式三组映射）直接内嵌 |
| 适配决策逐条可核验、不编造模板规范 | rule_map 的 template_original 必须抄自 probe_template.py 探查报告，rationale 必须回溯探查报告或题目约束 |
| 脚本三级容错 | pptx_build: python-pptx → stdlib pptx_minimal → 学术默认版式；probe/extract 同样容错 |
| SKILL.md 不硬编码平台路径 | 全部参数化传入，仅保留运行时契约路径（/input、/app/work、/app/output） |
| status 诚实四级 | complete/partial/failed/blocked，语义逐级写明 |

## 三、新版关键改进

1. **模板规则映射升为一等产物**：deck.json 每页带 rule_map；构建后完整内嵌 result.json 的 `template_rule_map` 与 `font_color_layout_mapping` 字段——评分器无需打开 pptx 即可逐页核验继承与适配决策（针对"可核验性 5 分 + 结果完整性 5 分"两个卡分项）。
2. **执行协议强制置顶**：result.json 骨架在任何探查之前落盘，保证任何中断点交出的都是字段完整的可评结果（针对"产物完整性"卡分项）。
3. **预算熔断点显式化**：48 请求/700 秒即收口，杜绝超预算零交付。
4. **流程与资源瘦身**：主流程 5 步、资源 8 文件，减少调度损耗，为内容质量留预算。

## 四、产出文件清单

```
submission/
├── SKILL.md                              # 重写：执行协议置顶 + 5 步主流程 + rule_map schema
├── README.md                             # 用途/调用/方法/异常/最小示意示例（标注示意）+ 资源清单
├── worklog.md                            # 本文件
├── references/page-plan-and-evidence.md  # 页计划与证据映射 schema（复用已验证版）
└── scripts/
    ├── probe_template.py     # 模板探查（复用）
    ├── extract_pdf.py        # 材料提取（复用）
    ├── pptx_build.py         # 真实继承构建（复用）
    ├── pptx_minimal.py       # stdlib 兜底（复用）
    ├── pptx_verify.py        # 结构/证据校验（复用）
    ├── consistency_check.py  # 整册一致性（复用）
    └── render_preview.py     # PDF/PNG 渲染（复用）
```

## 五、遗留风险与建议

- 脚本为已验证版本原样复用，未做代码改动；rule_map 依赖 Agent 在第 3 步响应中如实抄探查值，若模型抄写不全会降低可核验性——可考虑后续在 pptx_build.py 中自动从 template_report.json 回填 rule_map 的 template_original 字段（本次未改，控制回归风险）。
- 历史提交次数已多，本次为关键一搏；建议主控提交后若仍卡 69，下一步优先做"build 自动回填 rule_map"以彻底消除模型抄写环节。
