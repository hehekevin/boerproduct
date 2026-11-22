# worklog — claim-audit 重做（68 → 目标 ≥70）

日期：2026-11-13 ｜ 负责人：redo2-lit-claim ｜ 基线：week3 littrack claim-audit 第一版（平台聚合 68.00，run 72099）

## 相对 68 分版的改动

1. **摘录防改写核验（核心增强）**
   - 旧版 claim_check.py 只对 contradicted 的证据做逐字子串匹配；supported/partially_supported
     的摘录不校验，存在"改写后贴上来"的风险，直接对应评分点"证据片段是否真实存在于所标位置"。
   - 新版对 **所有** 带证据的子判断做空白归一化（删除全部空白）子串匹配；匹配失败=FAIL。
     paragraph_id 不在段落表时降级为 WARNING（跨段/表文字化情形），不误杀。
2. **覆盖对账：无静默跳过**
   - 新增 `uncertainties.uncovered`（{claim_id, reason}）字段；每个待核 claim_id 必须落在
     "有 verdict" 或 "登记 uncovered" 两条路之一，否则 FAIL。旧版漏判只报"漏核验"，
     新版给运行 Agent 提供了合规的第二条路，避免为了凑 answered 而硬判。
3. **强制执行协议置顶**：SKILL.md 开头即五条强制协议（主产物完整嵌入 result.json、
   摘录防改写、无静默跳过、不编造、先落骨架），运行时最先被读到。
4. **流程改为线性五步**（读输入落骨架 → 拆解 → 取证判定 → 汇总覆盖对账 → 校验交付），
   并把"摘录与原文并排自检"写进步骤 3，把"覆盖对账"写进步骤 4。
5. **脚本三级容错**：L1 输入文件缺失/不可读 → 降级为 WARNING 继续校验 result.json 结构；
   L2 解析异常捕获不抛 traceback；L3 业务规则失败记 problems 退出码 1；result.json 自身
   不可用才退出码 2。报告新增 warnings 列表。
6. **schema_guard.py**：沿用共享守卫（output_contract 全字段校验），未改动。

## 未改动的机制（保底）

四级判定定义与四条判定纪律（主题相关≠支持、未报告≠被证伪、保留限定、冲突并列）、
骨架先行（pending 起步逐条回填）、顶层五字段契约、examples 最小示例。

## 本地双测记录

- 测 1（正例）：examples 三文件跑 claim_check.py + schema_guard.py → 双 PASS。
- 测 2（负例）：构造改写摘录 + 漏判论断，确认 claim_check.py 逐条抓出并退出码 1。
- 容错测：缺失 case.json / 损坏 JSON 输入 → 降级 WARNING，无 traceback。

## 已知限制

- 摘录核验基于空白归一化，OCR 字符噪声会暴露为 FAIL——设计如此，逼运行 Agent 回原文修正。
- uncovered 与 verdict 二选一的覆盖对账依赖 claims-to-verify.json 的 claim_id 稳定。
