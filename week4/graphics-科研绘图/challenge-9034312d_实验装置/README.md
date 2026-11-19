# apparatus-route-figure 使用说明

## 一、Skill 是什么
把实验装置描述或技术路线文字材料，转成**可溯源、可编辑、可复跑**的图稿：
- 实验装置图：部件 + 管路/光路/气路/电路连接 + 介质与方向标注
- 技术路线图：阶段编号 + 并行分支 + 判断节点 + 里程碑
- 交付：分层可编辑 SVG + PNG(300dpi) + PDF + result.json（含 content_map 逐元素溯源，每条带 element_id + source + evidence）

## 二、运行环境与调用方式
本 Skill 由平台装进官方 DeepSeek Harness 运行。运行时：
1. 输入在 `/input/`（case.json、task.md，可能有 artifacts/figure-workorder.json 与来源材料）
2. 工作目录 `/app/work`
3. 产物写 `/app/output/`，必须含 `result.json`

Agent 侧触发方式：把本目录作为 Skill 加载后，向 Agent 说明"请按 SKILL.md 处理 /input 下的案例"即可；SKILL.md 第1节的线性5步主流程是唯一执行路径。

## 三、5步主流程速览
1. 读 case.json / 工单 / 来源材料，抄 output_contract 全键与 case_id
2. 立即写 result.json 骨架（全键 + status=partial）
3. 结构抽取：部件清单 + 连接关系（装置图）/ 阶段清单 + 分支判据（路线图），生成 content_map——每条记录固定四字段：`element_id`（与 SVG 内 id 一一对应）、`text`、`source`（文件+页/行）、`evidence`（≤30字逐字摘录）
4. 写分层 SVG → `python3 scripts/render_svg.py out/figure.svg --outdir out --png --pdf --dpi 300` → `--check` 像素校验；编辑工单走 source-preserving edit
5. 填全 result.json：compliance_checks（含连接方向核对表等五项逐条记录）/ exceptions / status

## 四、可核验性设计（本 Skill 核心）
- **element_id 溯源链**：SVG 内每个部件 `<g id="part-01-反应器">`、每条连接 `<path id="edge-03">`、每个阶段 `<g id="stage-02-验证">`，与 content_map 的 element_id 一一对应，评审可从图面任一元素直接查到来源位置与原文摘录。
- **连接方向核对表**：每条连接写成三列「原文句子 → 判定方向 A→B → 图上 edge-id 指向」逐条比对；"A通入B"=A→B；来源未明示的推断连接画虚线并登记 exceptions，绝不画实线猜测。
- **线型语义**：来源明示连接=实线箭头；推断连接=虚线；回流虚线弧；废液出口断头终端。
- **图例完整性**：图面每种线型/颜色/箭头 ↔ legend 条目双向核对。
- **文字无溢出机械检查**：宽度估算 = 中文字符数×字号 + ASCII 字符数×0.55×字号，超宽即换行或缩短。
- **SVG 分层可编辑性机检**：`scripts/svg_verify.py` 机械检查五项（分层 layer-* ≥4类 / 语义 id 唯一 / 文字均为 `<text>` / legend 非空 / content_map ↔ SVG id 双向一致），逐项输出 `{item, template_value, applied, match}`，整份 verify_report 嵌入 result.json。
- **渲染证据嵌入**：PNG 宽高、非背景像素占比（nonbg_ratio）、PDF 字节数、校验器名写成 `render_evidence` 字段嵌入 result.json，可核验而非自述。
- **编辑工单逐元素 diff**：`svg_verify.py --diff original.svg` 对比原稿与改稿，每个语义 id 一条 `{element_id, changed, before, after}`；未触碰元素 changed=false 构成 source-preserving 证据，整份 edit_diff 嵌入 result.json。

## 五、输入约定
- 来源材料可以是论文方法段落、装置清单、工艺说明、研究计划（PDF/文本/markdown 均可）
- 部件/阶段名称一律用来源原文，不改写、不缩写、不意译；来源未给出的参数不标注数值
- 凡 content_map 中找不到证据条目的元素，一律不画

## 六、最小示意示例（标注为示意，非正式案例结果）

输入 method.txt（示意）：
> 载气（N2, 100 sccm）经质量流量计进入石英管反应器，尾气经冷阱排空。

示意 result.json（节选）：
```json
{
  "case_id": "demo-01",
  "status": "complete",
  "editable_source": "out/figure.svg",
  "export_artifact": {"png": "out/figure.png", "pdf": "out/figure.pdf"},
  "content_map": [
    {"element_id": "part-01-质量流量计", "text": "质量流量计", "source": "method.txt 第1段", "evidence": "载气（N2, 100 sccm）经质量流量计"},
    {"element_id": "edge-02", "text": "质量流量计→石英管反应器(载气)", "source": "method.txt 第1段", "evidence": "经质量流量计进入石英管反应器"}
  ],
  "compliance_checks": [
    {"check": "连接方向核对", "detail": "edge-02: 「经质量流量计进入石英管反应器」→ 流量计→反应器 → 图上 edge-02 指向反应器，一致"},
    {"check": "图例完整性", "detail": "图面实线箭头1种线型 ↔ legend 1条，一致"},
    {"check": "文字无溢出", "detail": "各标注框宽度估算通过"},
    {"check": "渲染校验", "detail": "PNG --check 通过（非全白、宽1200px）；PDF 12KB"}
  ],
  "exceptions": []
}
```

## 七、脚本与依赖
- `scripts/render_svg.py`：零第三方依赖的渲染与校验脚本（渲染器回退链 cairosvg → rsvg-convert → inkscape → chrome headless；像素检查用纯标准库 PPM 管道）
- 用法：`python3 scripts/render_svg.py input.svg --outdir out --png --pdf --dpi 300`；校验：`python3 scripts/render_svg.py out/figure.png --check`
- `scripts/svg_verify.py`：SVG 分层机检 + 编辑 diff（纯标准库 xml.etree）
- 机检：`python3 scripts/svg_verify.py out/figure.svg --map content_map.json --out out/verify_report.json`；编辑 diff：`python3 scripts/svg_verify.py out/figure_edited.svg --diff out/figure_original.svg --out out/edit_diff.json`
- Python ≥3.8；第三方渲染库任选其一，全缺失时脚本自动回退
- 调用脚本须 try/except 包裹（cairosvg 缺原生库时 import 抛 OSError，见 SKILL.md 第2节）

## 八、异常与失败处理
见 SKILL.md 第2节异常处理表：参数缺失→保守默认+登记；连接不明→虚线+登记；来源冲突→以更具体描述为准并双记；渲染全失败→只交 SVG+登记；字体缺失→换可用 CJK 字体重渲。

## 九、限制
- 不判断实验方案科学合理性；不做数据分析与数值拟合；不做期刊排版适配
- 图面内容严格限于来源材料；来源没写的不出现（或以虚线+登记方式呈现）
- 预算触顶（>48 请求 / >700 秒）时按协议收尾，可能产出 partial 结果

## 十、文件清单
| 文件 | 说明 |
|---|---|
| SKILL.md | Skill 本体（协议+主流程+异常+自检，≤150 行） |
| scripts/render_svg.py | 渲染与像素校验脚本 |
| scripts/svg_verify.py | SVG 分层可编辑性机检 + 编辑逐元素 diff |
| README.md | 本说明 |
| worklog.md | 开发时间线 |


## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（评测沙箱 3.12；本 Skill 脚本仅用标准库，无需 pip 安装）；无浏览器/无外部渲染器时按降级链处理。 |
| 安装与运行 | 平台把提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json`（+ 材料），产物写 `/app/output/result.json`。 |
| 输入 / 输出解释 | 输入=案例标识、来源材料、图稿工单与导出约束；输出=result.json（契约全字段 + content_map + compliance_checks 三元组 + gain_evidence + efficiency + exceptions）。 |
| 目标用户与场景 | 科研绘图的作者与评审：需要「可编辑源文件 + 可溯源要素 + 可核验导出件」，用于机制图/流程图/技术路线图/数据图的成稿与复核。 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②content_map 元素数=图面元素数且逐条带 source+evidence；③compliance_checks 三组三元组齐全、非 enforced 均有 gate_note；④gain_evidence 含两套对照指标与削减量。 |
| 常见问题 | 图面元素无来源→按材料补登记或删除该元素；关系方向不明→按原文陈述方向，存疑记 exceptions；导出件缺失→按降级链如实登记 renderer_unavailable。 |
| 已知限制 | 无渲染器环境只能交付 SVG 源文件与降级记录；像素级校验需在有渲染器的环境复跑 `--check`。 |
| 失败处理 | 任一步异常：写盘已有产出、status 如实降级、exceptions 记录失败点与已尝试回退链；机检结论照实记录，**不中断交付**。 |
| 复用建议 | 把本目录 scripts/ 直接复制到新项目；content_map 与 compliance_checks 的字段结构可直接套用到其它绘图任务。 |
| 版本与维护 | 见 worklog.md 的版本小节；结构变更时同步更新本表与 SKILL.md 的输出字段说明。 |

## 最小可运行自检清单（复制即跑，用于确认环境可用）

```bash
python3 -c "import sys;print(sys.version)"   # 1) 解释器可用
ls scripts/                                    # 2) 脚本在位
python3 scripts/gain_evidence.py --help         # 3) 增益脚本可执行
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 4) 产物可解析且键齐全
```
