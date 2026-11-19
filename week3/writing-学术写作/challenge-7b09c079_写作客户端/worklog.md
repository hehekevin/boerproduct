# worklog — challenge-7b09c079（学术写作客户端）83 公式增量增强

## v1（acwrite-client，attempt 71939 → 54.67）差距分析（对照 FORMULA-83 六要素逐条检查）

| 公式要素 | v1 状态 | 差距 |
|---|---|---|
| 1. 强制执行协议置顶 | ❌ 无 7 条协议 | 只有零散硬规则；无"先落骨架/预算熔断/失败也交付" |
| 2. 主产物结构化全量嵌入 result.json | ❌ | result.json 只有指针，无客户端、无修订台账结构 |
| 3. 每个可核验点机械校验器+逐条嵌入 | ⚠️ 部分 | edits_verify 存在但报告不回填 result.json；无 {item,applied,match} 三元组 |
| 4. 闸门显式枚举 | ❌ | 无 gates/gate_note 概念 |
| 5. claims 逐字证据链 | ❌ | 完全没有 claims 机制 |
| 6. status 诚实四级 | ⚠️ | status=complete 一把梭，无 partial/failed/blocked 语义 |
| 题面特有：交互客户端 | ❌ | 题目是"学术写作客户端"，v1 只交付 docx+台账，无任何交互界面；这正是 54.67 vs 平台第1 83 的主差距 |

参照同型题实证 77.33 的 challenge-f730fc37-v2（阅读客户端）：其"嵌入式客户端 HTML + features 功能清单
+ 交互逐条对照题面 + claims 机械挂链 + 9 组机械自检"做法全部可搬。

## v2 增强内容（保留 v1 全部脚本骨架与外科手术机制，只补缺失要素）

1. SKILL.md 重写（148 行 ≤150）：协议 7 条置顶 + 七步主流程 + 闸门语义 + 诚实四级状态；
   保留 v1 的锚点索引/指令拆解/修订台账/docx 构建/校验全部机制，不推翻不重构。
2. **export_client.py（新，核心创新）**：自包含交互修订客户端 revision_client.html——
   ①修订逐条接受/拒绝/需确认（localStorage 跨会话持久）②修订卡锚点跳转 ③v1/v2 版本对照
   （v2 按裁决实时合成）④按裁决导出已接受修订 Markdown + 裁决 JSON ⑤台账筛选
   ⑥关键词搜索+导航 ⑦引用与格式哨兵 ⑧边界与人工确认展示。
   `--embed-result` 把 HTML 全量嵌入 result.result.client.embedded_html + 登记 features 8 条
   + artifacts 路径。逐条对照题面四问题（改得准/可追溯/格式不塌/交付可用）与六方向
   （AI 修改/修订追踪/版本管理/文档导出均有落点）。
3. **build_result.py（重写）**：--init 骨架（契约字段一个不缺 + features 预登记）、--merge、
   **--claims-from-edits**（每处改动机械生成 claim：kind=reported/source_id/location/evidence 逐字引文）、
   --check；status 四级 complete/partial/failed/blocked；全异常捕获失败也写盘。
4. **check_all.py（新）**：9 组机械校验（契约字段/case_id/status/修订锚点逐字命中/after 落地+引用编号
   连续/claims 证据链完整+引文回证/客户端嵌入一致+features/uncertainties/changelog），逐条输出
   {item, applied, match} 三元组；闸门显式枚举 enforced/skipped_not_provided/not_found/unreadable
   写回 result.json 顶层 checks/gates/gate_note；fail 冒泡退出码。
5. edits_verify.py / docx_build.py / render_preview.py / extract_materials.py 保留 v1 原样（已达标）。

## 双测证据

- 3 个改写/新建脚本 py_compile 通过；--selftest 正反例全部 PASS：
  - build_result：正例（契约抄录/claims 证据链断言/merge 后 status）+ 反例（case 缺失仍写盘、
    损坏 result 报 FAIL 不崩溃、edits 缺失优雅处理）。
  - export_client：正例（11 个交互元素 token 断言、嵌入断言、features=8 断言）+ 反例（全输入
    二进制损坏仍写出可用 HTML ≥500B、空台账有占位提示）。
  - check_all：正例（16 条校验全过、checks/gates 写回断言）+ 反例（锚点错位触发 FAIL、
    嵌入与磁盘不一致触发 FAIL）。
- 端到端合成演练（drill/）：case.json → --init → --claims-from-edits → 手工字段 merge →
  export_client --embed-result → check_all --write-back → PASS（16 条校验，gates 4 项枚举，
  claims 2 条，features 8 条，embedded_html 11910 字符）。
- SKILL.md 148 行 ≤150，frontmatter name/description 合法。

## 遗留风险

- edits_verify 的 --original 目前吃 extracted/*.txt；structure.json 路线的锚点校验由 check_all
  兜底（已实测）。
- 客户端 JS 决策合并逻辑（accepted 替换）已在合成数据上人工核对；真实长文档表现待平台案例验证。
