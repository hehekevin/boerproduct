# bio-pathway-figure 使用说明（生物机制图与通路图）

## 用途
从机制材料出发生成**每个实体、每条边可逐字回证**的生物机制图/通路图：相互作用语义映射为可区分箭头样式，区室/跨膜位置按约束布局，图例与图面一一对应，交付分层可编辑 SVG + PNG(300dpi)/PDF，全部机械校验逐条写入 result.json，附同校验器消融两臂增益证据。

## 文件清单（9 个，全 UTF-8，总量 81KB，远小于 2MB / 50 文件）

| 文件 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体：强制协议、六步主流程、机械校验六组、异常表、自检清单（127 行 ≤150） |
| `README.md` | 本说明 |
| `scripts/pathway_svg.py` | spec→分层 SVG 渲染器：区室带/跨膜中线/语义箭头/图例，`--ablate` 消融开关，零依赖 |
| `scripts/validate_pathway.py` | 机械校验器：实体/边语义/方向点积/区室/图例/导出六组逐条判定，退出码恒 0 |
| `scripts/render_svg.py` | SVG→PNG/PDF 渲染回退链 + PNG 像素检查，零第三方依赖 |
| `scripts/gain_evidence.py` | 增益证据层：同输入消融两臂 + 污染反例注入 + 基线对照，唯一写 `gain_evidence`/`efficiency` 键 |
| `examples/example-spec.json` | 示意 spec（**示意，非正式案例**）：EGF-EGFR-RAS-ERK 通路 |
| `examples/example-source.txt` | 示意材料原文（供逐字回证演示） |
| `worklog.md` | 制作时间线与真实对照数字 |

## 依赖与安装
- Python 3.8+（仅标准库，无 pip 安装；评测沙箱 3.12 已验证接口）。
- 可选渲染器（任一即可）：cairosvg / rsvg-convert / inkscape / chromium headless（render_svg.py 内置回退链）；全失败时交付 SVG 源并如实登记。
- 安装：平台把提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json` + task.md，工作目录 `/app/work`，产物写 `/app/output/`（必含 `result.json`）。

## 调用方式（主流程摘自 SKILL.md）
1. 读 case.json → 抄 `case_id` 与 `output_contract` 全键
2. 立即写 `/app/output/result.json` 骨架（status=partial，一个键不缺）
3. 逐句抽取实体/关系 → `/app/work/pathway_spec.json`（evidence 为材料逐字引文；方向按原文陈述）
4. `pathway_svg.py` 渲染分层 SVG → `render_svg.py` 导出 PNG(300dpi)+PDF
5. `validate_pathway.py` 六组机械校验，match=false 改 spec 重跑
6. 填 result.json 全字段；`gain_evidence.py --write` 回填增益证据与效率计数

## 最小示意示例（标注：以下为示意，非正式案例结果）

```bash
# 以 examples/ 为输入跑通全链路
python3 scripts/pathway_svg.py examples/example-spec.json --out figure.svg
python3 scripts/render_svg.py figure.svg --outdir . --png --pdf --dpi 300
python3 scripts/validate_pathway.py examples/example-spec.json figure.svg --corpus examples/example-source.txt
python3 scripts/gain_evidence.py --spec examples/example-spec.json --corpus examples \
  --result result.json --outdir . --write
```

示意输出（实测节选，非正式案例）：全量臂 `fail_count=0`（141 项校验全过）；消融臂（关语义箭头/区室/图例）`fail_count=21`，`fail_count_diff=21`；污染反例注入 2 处错画被抓 `caught=true`（6 项 FAIL）；基线需人工核对 74 项 → 登记后 0 项。

## 生态贡献：依赖、安装运行、目标用户与验收（十项）

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（沙箱 3.12；脚本仅标准库）；可选渲染器按降级链处理；无浏览器环境照样交付 SVG 源 |
| 安装与运行 | 平台装入 `/skills/weekly-skill`；输入 `/input/case.json`(+材料)；产物 `/app/output/result.json` + 渲染产物 |
| 输入 / 输出解释 | 输入=案例标识、机制材料、工单；输出=result.json（契约全字段 + content_map 双层 + compliance_checks 六组 + gain_evidence + efficiency + exceptions） |
| 目标用户与场景 | 机制图/通路图作者与评审：需「可编辑源文件 + 逐字回证 + 可核验导出件」的成稿与复核 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②content_map 元素=SVG 图元且逐条带 source+evidence；③compliance_checks 六组逐条明细齐全；④gain_evidence 两臂差值与污染 caught=true 为真跑数字 |
| 常见问题 | 图元无来源→按材料补登记或删除；关系方向不明→按原文，存疑记 exceptions；导出失败→按降级链如实登记 |
| 已知限制 | 无渲染器环境只能交付 SVG 源 + 降级记录；像素级校验需在有渲染器环境复跑 `--check`；通路数据编码（颜色→表达量映射）仅做图例一致性校验，数值语义属相邻课题 |
| 失败处理 | 任一步异常：写盘已有产出、status 如实降级、exceptions 记录失败点与已试回退链；机检结论照实记录，不中断交付 |
| 复用建议 | `scripts/` 可直接复制到新绘图任务；spec 结构（nodes/edges/compartments）与六组校验字段可套用到任意机制图任务 |
| 版本与维护 | 见 worklog.md；结构变更时同步更新本表与 SKILL.md |

## 最小可运行自检清单（逐条实测 exit 0）

```bash
python3 -c "import sys;print(sys.version)"                     # 1) 解释器可用
ls scripts/                                                     # 2) 4 个脚本在位
python3 scripts/pathway_svg.py --badflag; echo $?               # 3) 失败路径 exit 0
python3 scripts/pathway_svg.py examples/example-spec.json --out /tmp/f.svg   # 4) 渲染 ok:true
python3 scripts/validate_pathway.py examples/example-spec.json /tmp/f.svg --corpus examples  # 5) fail_count=0
python3 scripts/gain_evidence.py --spec examples/example-spec.json --corpus examples --result /tmp/r.json --outdir /tmp --write  # 6) diff>0 且 caught=true
```
