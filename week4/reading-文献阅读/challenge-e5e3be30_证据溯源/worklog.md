# worklog — claim-audit 增量增强（redo 基线 → 83 公式对齐）

日期：2026-11-16 ｜ 负责人：r83-04-claim ｜ 基线：bohrium-week3-redo challenge-e5e3be30 submission（68 分版增强重做稿）

## 对照 83 公式的缺失要素清单

| 要素 | redo 版现状 | 处置 |
|---|---|---|
| 1 强制协议 7 条 | 仅 5 条 | 补第 6 条「每步一个写盘动作」（分批回填 ≤1500 字防 16384 截断）、第 7 条「失败也交付」（写盘前 JSON 自检） |
| 2 主产物全量嵌入 result.json | 已有 | 分批写策略并入协议 6 |
| 3 机检结果嵌入 result.json | 校验报告只写独立 claim_check.json | SKILL 步骤 5 新增「机检结果回写」：changelog 追加 {action:"claim_check", ok, problems, warnings, gates}，评分器不开附件即可核对 |
| 4 闸门状态显式枚举 | 仅 WARNING 打印 | claim_check.py v3 新增 gates：coverage_audit / quote_verification / verdict_summary_audit 三闸，状态 ∈ enforced / skipped_not_provided / not_found / unreadable；非 enforced 附 gate_note「该闸未运行，下游不得宣称已核对」 |
| 5 摘录防改写 + 逐字定位 | 已有（空白归一化子串核验） | 保留不动 |
| 6 status 诚实四级 | 已有 | 保留不动 |
| verdict_summary 对账机检 | 已有 | 保留不动，SKILL 第 3 节补显第 6 条说明 |
| uncovered 逐条登记 | 已有 | 保留不动 |

增量增强，未推翻任何现有机制；68 分原版（bohr-product week3-ppt littrack claim-audit）与 redo 版均未改动。

## 约束自检

- SKILL.md 恰 150 行；frontmatter name/description 合法。
- 资源 8 文件（SKILL.md/README.md/worklog.md + examples 3 + scripts 2），脚本纯标准库。
- 不硬编码平台路径（/skills/weekly-skill、/input、/app/work、/app/output 契约路径未变）。
- examples 仍标注「示意，非正式答案」。

## 本地双测证据

- 测 1（正例）：examples 三文件 → claim_check PASS（三闸门全 enforced）+ schema_guard PASS，退出码 0。
- 测 2（反例，注入 4 处脏数据）：改写摘录（fatigue life→fatigue lifetime）、漏判 cl-2 且不登记 uncovered、verdict_summary 错账（supported:99）、非法 type（correlation）→ claim_check 逐条全部抓出 4 处 FAIL，退出码 1。
- 测 3（闸门降级）：case.json 缺失 → quote_verification=not_found + gate_note；case.json 无段落表 → quote_verification=skipped_not_provided + gate_note；退出码均不变差（0），gate_note 明示下游不得宣称已核对。

## 遗留限制

- gates 状态回填 result.json.changelog 由运行 Agent 按 SKILL 步骤 5 执行，脚本不直接改写 result（避免破坏业务内容）。
- 其余限制沿袭 redo 版（OCR 噪声、跨页断裂、不联网核对元数据）。
