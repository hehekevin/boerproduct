# worklog

- 2026-11-11 完整读取 task.md，确认评分维度（实际效果40/使用增益25/创新增益15/可靠体验10/生态贡献10）、Harbor 运行契约（/input/case.json、/app/work、/app/output、result.json 含 case_id 与 output_contract 字段、64 次请求/900 秒/16384 tokens 预算、50 文件/500KB/2MB 资源限制）。
- 2026-11-11 设计决策：采用 事实底稿先行 架构，先建参数表、数据集表、环境表、对照表四张底稿再写正文，正文数值只能取自底稿，从机制上杜绝为行文顺畅补造数值。
- 2026-11-11 设计决策：确定三大创新机制：数字-来源映射表（每个数值可回溯到文件与定位）、符号表统一管理（一符一义、首次定义、公式与正文一致）、缺口显式化标注（[TODO] 与 [待确认] 双标记，禁止默认值编造）。
- 2026-11-11 设计决策：流程经济性优先，固定为 Phase 0 至 5 共六阶段，正常路径约 1 次目录列举加 1 到 2 次批量读取加 2 到 3 次写入，模型请求集中在成稿与自检两次，远低于 64 次预算；禁止逐段润色式反复调用。
- 2026-11-11 创建 submission/SKILL.md：英文 frontmatter description（是什么、何时用、触发语含中英文关键词），中文正文含用途、核心机制、适用条件、调用方式、六阶段流程、十类异常分支表、自检清单、资源索引。
- 2026-11-11 创建 submission/resources/methods-structure-template.md：数据、模型、流程、设置、指标、对照、复现、限制八区块结构模板，每区块含写作内容、过去时加被动的惯例句式与要素自查。
- 2026-11-11 创建 submission/resources/experiment-setup-checklist.md：五类 28 项要素清单（数据集 7、训练 7、软硬件 6、评测 6、对照 5），每项须带来源编号，兼作 Phase 4 要素覆盖检查依据。
- 2026-11-11 创建 submission/resources/reproducibility-checklist.md：复现十项核查清单，量化 具备/TODO 统计写入 result.json，作为复现完整度指标。
- 2026-11-11 创建 submission/resources/fact-source-map-template.md：来源登记表、事实映射表、参数表、缺口与冲突清单四部分，规定 已证实/冲突待确认/TODO/作者已确认 四种状态及来源优先级裁决规则（配置日志 > 结果表 > 实验记录 > 论文旧稿）。
- 2026-11-11 创建 submission/resources/symbol-table-template.md：符号表六字段与六条一致性规则（一符一义、一义一符、首次定义、公式一致、指标名视同符号、与材料写法一致）。
- 2026-11-11 创建 submission/resources/result-json-template.md：固定基础字段加 output_contract 契约字段双层结构，status 三值判定标准，早期写骨架保证中途失败也有诚实交付，契约字段无法满足时填 unknown 不编造。
- 2026-11-11 创建 submission/resources/gap-and-conflict-playbook.md：十类异常情形的识别信号、处置动作、禁止事项，统一 [TODO] 与 [待确认] 标注格式，含预算耗尽时的降级交付策略与 status 判定速查表。
- 2026-11-11 创建 submission/README.md：文件清单、安装触发、输入输出约定、流程概要、最小调用示例（明确标注 示意输出，非正式案例结果）、适用边界、失败处理与自查、维护信息。
- 2026-11-11 创建 submission/worklog.md（本文件）。
- 2026-11-11 自查确认：共 10 个 UTF-8 文本文件，远低于 50 文件限制；无脚本依赖；全部用简体中文，frontmatter description 为英文；无 emoji，无破折号；SKILL.md 流程与模板文件互相引用路径一致。
