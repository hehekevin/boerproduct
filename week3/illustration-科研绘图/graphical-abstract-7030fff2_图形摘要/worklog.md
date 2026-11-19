# worklog — graphical-abstract-builder v3.0（final 对标 83 公式增强版）

## 背景
- 基线：`bohrium-week3-plotfix/graphical-abstract-7030fff2/submission/`（当前最优包，平台 73.33，第5/21；第1名 83）。
- 本次按 FORMULA-83 六要素逐条对照查缺，只做增量增强，不推翻不重构。

## 对照 83 公式的缺失要素清单（本次逐项补齐）
1. **机检对账缺失（要素3，最大缺口）**：v2.0 的画布/字号/溯源/溢出全是 SKILL.md 要求模型"手写 compliance_checks"，不经机器。→ 新增 `scripts/svg_audit.py`（纯标准库）：画布、字号下限（逐元素扫描含继承）、纯 text 元素（禁 `<image>`）、语义图层、视觉动线分区、溢出扫描（字宽估算 vs 右边界-边距）、编辑 diff 七项机检，逐项产出 `{item, template_value, applied, match}` 三元组 + fail 冒泡退出码；SKILL.md 明确"audit 结果原样内嵌 result.json，禁止手写替代"。
2. **闸门状态未显式枚举（要素4）**：v2.0 没有"未运行≠通过"机制。→ svg_audit 每项带 `gate`：`enforced / skipped_not_provided（带 gate_note「下游不得宣称已核对」）/ not_found / unreadable`。
3. **证据非逐字摘录（要素5）**：v2.0 content_map 只有 `source` 标签（"摘要第N句"），无逐字 quote，评分器无法机械核验。→ 新增 `evidence_map`：`{kind, evidence≤40字逐字, source_id, location}`；**数字必须逐字回证**，`numeric_unbacked` 逐条列出（改图补证或删数字，不许改 quote 迁就图）。
4. **视觉动线未结构化登记（团队提示项）**：v2.0 四图层无阅读顺序结构。→ SVG `data-zone="background|method|result|conclusion"` 分区标注，svg_audit 逐区核对存在性并内嵌 result.json。
5. **编辑工单 diff 非机生（团队提示项）**：v2.0 只有手写 edit 记录。→ svg_audit `--baseline` 产出 `edit_diff`（preserved/modified/removed/added 逐条），`removed` 非空即 fail。
6. **协议 5 条→7 条（要素1）**：补"广度优先"（先全链路可评产物再精修）与"写盘前 JSON 自检"（回写前 json.load 验字段数）；"失败也交付"升格为第 7 条明文。
7. **status 三级→四级（要素6）**：补 `blocked`（材料缺失无法开始，附原因），对齐 83 样本。

## 保留的 v2.0 已验证机制（全部继承）
- 逐键抄契约、立即落骨架、分批写盘 ≤200 行、路径动态定位（`find /skills /app`）、渲染回退链 + `--check` 像素校验、渲染失败不回滚（保留 SVG + exceptions + partial）、异常处置表、自检清单、行数纪律（SKILL.md ≤150 行）。

## 双测证据（本地 Python 3.13，纯标准库）
- **正例**（合规 SVG，1200×600、36/20/18px、四图层、四分区）：`AUDIT fail=0`，退出码 0；gates：6 项 enforced + edit_diff=skipped_not_provided（非编辑工单，正确跳过）。
- **反例**（注入脏数据：画布 1000×600、12px 文字、`<image>` 标签、缺 layer-legend、缺 data-zone、超宽溢出文字）：9 项 fail 全部逐条命中注入项，退出码 1（冒泡）。
- **编辑 diff 反测**：正例删除元素 p2 后 `--baseline work/pos.svg` 复检 → `removed:['p2']`、preserved=10、退出码 1。
- 渲染脚本原样复制 v2.0 已修复版（cairosvg Exception 捕获、--check 缺文件返回码 2、浏览器回退 file:/// 规范化）；本机无渲染后端时如实 `PNG FAIL`（文档化降级路径，未伪造产物）。

## 交付清单（共 4 文件，全 UTF-8 文本，<70KB；限额 50 文件/500KB/2MB）
- [x] SKILL.md（108 行，wc -l 实测；硬约束 ≤150 行达标）
- [x] scripts/render_svg.py（185 行，原样复制已验证版）
- [x] scripts/svg_audit.py（272 行，新增机检对账）
- [x] README.md（含依赖/调用/双测证据/示意示例标注"非正式案例结果"）
- 产出目录：`bohrium-week3-final/graphical-abstract-7030fff2/submission/`，未提交（按指令仅产出）。
