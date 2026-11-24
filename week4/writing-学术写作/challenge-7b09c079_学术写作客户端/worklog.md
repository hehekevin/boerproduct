# worklog — acwrite-client 重做（challenge-7b09c079）

## 旧版失分点分析
旧版（attempt 72500:52.33、71939:54.67，更早 attempt 0 分/未出分）存在以下问题：

1. **执行协议未置顶**：旧 SKILL.md 把 result.json 组装放在最后一个 Stage 6，流程中断/预算耗尽时 result.json 缺失或字段不全 → 契约字段缺失直接扣分；早期 attempt 全 0 疑似即 result.json 未产出/非法。
2. **预算管理过激**：旧版按 64 请求/900 秒满额推进，7 阶段+多次修复重跑极易触线，导致收尾阶段（恰恰是 result.json 组装）没执行完。新版自设 48 请求/700 秒熔断，广度优先，先保骨架后加深。
3. **output_contract 键处理不完整**：旧 build_result.py 只处理 list 型或 dict 含 fields/required 的契约；若运行时 contract 是普通 dict（键即字段名），骨架键会漏建 → 字段缺失。
4. **主产物未嵌入 result.json**：旧版 result.json 只放 deliverable 指针，未把修订稿全文/台账内容嵌入契约字段的字符串值，复核者拿不到可核验主结果。
5. **脚本容错不足**：edits_verify 对缺文件/脏 JSONL 直接 traceback 崩溃（`json.loads` 逐行解析无保护），脏输入下管线中断且无报告产出。
6. **主流程 7 阶段过长**：响应预算被 Stage 划分切碎，实际执行中阶段跳跃/合并混乱。新版压缩为 5 步线性主流程。
7. **无 JSON 写盘自检与"失败也写 result.json"硬规则**：非法 JSON 或半成品直接落盘。

## 新版关键改进
1. **P 节强制执行协议置顶**：第 1 步逐字抄 case_id+output_contract 全键；第 2 步立即写 result.json 骨架（build_result.py 自动建全键 null 字段）；任何时刻契约键一个不缺；填不了的置 null+uncertainty 说明。
2. **主产物双通道交付**：修订稿全文与 edits 台账摘要嵌入 result.json 契约字段字符串，同时另存 revised.docx/md 外部文件；长产物分批写避免 16384 token 单响应上限。
3. **预算熔断**：48 请求/700 秒自设线（低于平台 64/900），广度优先：先保 3 案例骨架与部分诚实结果，再回头加深。
4. **脚本三级容错**：全部脚本 __main__ 加兜底守卫（任何异常输出 JSON 错误报告不崩溃）；edits_verify 对缺文件/脏 JSONL/非对象行逐条降级记录，verdict=fail 而非 traceback；build_result 契约键处理覆盖 dict/list/嵌套 fields/required。
5. **主流程压缩为 5 步**（定契约→快照+拆解→台账→构建→校验收尾），SKILL.md 129 行（<250），祈使句。
6. **来源映射与缺口标注**：每条 edit 的 rationale 追溯到指令条目/材料位置；材料不足标 needs_confirmation，工单（organizer-edit-workorder.json）存在时以其为准。
7. **status 四级诚实**（complete/partial/failed/blocked）+ 失败也写 result.json 硬规则。

## 产出文件清单
```
submission/
├── SKILL.md                    # Skill 本体（协议置顶 + 5 步主流程，129 行）
├── README.md                   # 使用与方法说明（含最小示意示例，标注示意）
├── worklog.md                  # 本文件（旧版失分点分析）
├── examples/example_input.json # 最小示意输入
└── scripts/                    # 7 个脚本（均三级容错）
    ├── extract_materials.py
    ├── fact_ledger.py
    ├── docx_build.py
    ├── edits_verify.py
    ├── consistency_check.py
    ├── render_preview.py
    └── build_result.py         # 契约全键骨架 + 分键回填
```

## 测试记录
- 语法编译：7 脚本 py_compile 全通过。
- 正例：构造 4 段稿件 + 3 条指令 → 全流程跑通，edits_verify verdict=pass。
- 反例（脏输入）：缺文件 / 非法 JSONL / 非对象行 / 空 edits → 不崩溃，verdict=fail 且 load_errors 逐条记录。
