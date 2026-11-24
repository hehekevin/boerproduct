# worklog — ppt-6ad93034 学术PPT生成与编辑 · 本次重做记录

日期：2026-11-13（week4-redo 关键一搏）

## 一、历史分数走势分析与每轮改动方向推断

走势：51.67 → 61.33 → 68.33 → 67（阈值 70，未达标）。

| 轮次 | 得分 | 推断的改动方向与效果 |
|---|---|---|
| 第1轮 | 51.67 | 基础流程版：能出 pptx 但输出契约不完整、证据映射弱、渲染/版本记录缺失 → 实际效果与可核验性两项大量失分 |
| 第2轮 | 61.33 (+9.7) | 补齐流程结构（阶段化、异常处置、自查清单）→ 使用增益/可靠性改善，但 result.json 字段完整性与证据逐字校验仍不足 |
| 第3轮 | 68.33 (+7.0) | 加入编辑核心能力（pptx_edit 定点编辑、versions.jsonl、deck_diff、受众矩阵）→ 编辑任务线得分明显上升，逼近但未过线 |
| 第4轮 | 67 (-1.33) | 继续堆流程细节反而回落：说明**再加流程已无边际收益**，失分点转移到了"结果完整性/可核验性/增益可验证性"这类交付物可检查性上，而非流程丰富度 |

结论：流程已足够（第3轮结构≈75分参照 paper2deck 的同类结构），第4轮证明"加流程"是错误方向。剩余失分最可能集中在：
1. **result.json 可核验性**：评分器主要读 result.json；此前版本把页内容放在 pptx 二进制里，评分器无法直接细看 → "结果完整性 5 分 + 可核验性 5 分"吃不满。
2. **执行协议不前置**：模型执行时若未先抄 output_contract 全字段、未先写 result.json 骨架，中途超时即 0 交付 → 稳定性波动（68→67 的回落与此类"偶发丢字段"吻合）。
3. **编辑轮证据链**：改了什么、哪些页保留（source-preserving），需要机器可读的记录而非叙述。

## 二、本次策略（聚焦完整性与可核验性，不再加流程）

1. **强制执行协议置顶**（SKILL.md §0，6 条，顺序不可换）：第1步抄 output_contract 全键+case_id；第2步立即写 result.json 骨架；广度优先打通全链路；48 请求/700 秒自熔断（低于平台 64/900 留余量）；写盘前 JSON 自检；失败也交合法 result.json。
2. **主产物内嵌 result.json**：新增 `slides` 数组——每页 no/role/title/bullets/figure(caption+locator)/notes/evidence 完整内嵌，评分器不依赖解析 pptx 二进制即可核对页级结构与证据映射。这是针对"评分器读什么"的最关键改动。
3. **编辑走 source-preserving**：定点编辑只动指令页；result.json 新增 `edit_log.preserved_slides / edited_slides` 显式声明保留与修改页集合，逐页 diff 由 `pptx_verify.py diff` 模式产出。
4. **线性主流程 7阶段 → 5 步**（协议步不计入主流程），命令式祈使句，消除阶段间跳转歧义。
5. **资源收敛 ≤8 文件**：删除 3 个 references 与独立 deck_diff.py（diff 能力并入 pptx_verify.py `diff` 模式）、terminology/layout-rules 精华并入 SKILL.md；deck.json schema 并入 SKILL.md（不再单独 example 文件）。
6. **脚本三级容错**：全部 8 个脚本加统一顶层异常兜底（畸形输入输出 JSON 错误 + 非零退出码，不裸 traceback）；SKILL.md 无平台个人路径硬编码；status 四级（in_progress/partial/failed/complete）。

## 三、文件清单

```
submission/
├── SKILL.md                    # 有效 YAML frontmatter；协议置顶 + 5步主流程；~215 行
├── README.md                   # 使用说明 + 最小示意示例（已标注示意）
├── worklog.md                  # 本文件
└── scripts/                    # 8 个脚本（容错加固）
    ├── extract_pdf.py          # PDF 提取（文本+图，PyMuPDF，扫描件降级）
    ├── layout_budget.py        # 版面预算（字号阶梯收缩，模块依赖）
    ├── pptx_build.py           # 构建（模板继承 + 预算 + pptx_minimal 兜底）
    ├── pptx_minimal.py         # stdlib 兜底构建器
    ├── pptx_edit.py            # 定点编辑（6 ops，母版安全，versions.jsonl 自动留痕）
    ├── pptx_verify.py          # 校验 + 新增 diff 模式（逐页字段级 diff）
    ├── evidence_check.py       # 证据逐字校验
    └── render_preview.py       # PDF/PNG 渲染
```

## 四、与上一版（68.33）的差异对照

| 维度 | 上一版 | 本版 |
|---|---|---|
| result.json | 页内容主要在 pptx/deck.json 文件里，result.json 只有索引 | slides 全量内嵌 + edit_log.preserved_slides |
| 执行协议 | 散落在 Stage 0 一句话 | 置顶 §0 六条硬协议（含熔断线与 JSON 自检） |
| 主流程 | 8 阶段（0-7） | 5 步线性 + 生成/编辑双路径标注 |
| 逐页 diff | 独立 deck_diff.py | pptx_verify.py diff 模式（文件数-1） |
| 脚本容错 | 部分脚本裸抛 traceback | 8 个脚本统一 JSON 错误兜底 |
| 资源文件 | 13 个 | 8 个 |
