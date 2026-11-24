# worklog — cite-trace v2（challenge-60a8202d）

开发记录、真实对照数字与诚实边界。数字来自本地实跑（Windows 11 / Python，
Git Bash），可按 README §6 复现。

## 一、重构决策（从 16 分的六分面包 → 极简单点单方向包）

| 原 v1（16 分） | v2（本次） | 原因 |
|---------------|-----------|------|
| 六分面：双向追踪 + 关联发现 + 引用网络 + 路径解释 + 去重合并 + 增益探针 | 只做**前后向追踪**一个方向 | 题面"突破方向"第 1 条即前向/后向追踪；六面摊薄每面质量 |
| 4 个脚本（含 gain_probe 486 行） | 3 个精简脚本（build_skeleton / verify_check / schema_guard） | 砍增益探针，预算 <50% 才双跑 |
| verify_check 834 行 / 135 项检查 | 约 200 行 / 4 类检查 | 只校验追踪口径必需项 |
| 每层无上限、深层扩展 | 1–2 层、每层 ≤5 篇即停止 | 停止判断明确，避免预算耗尽 |
| gain_evidence 必跑双模式 | 默认 available=false | 铁纪律第 4 条：预算过半即定稿 |

## 二、追踪规模上限（硬约束）

- 方向：仅 backward（后向，种子参考文献→方法/数据出处）+ forward（前向，施引文献→改进/批评）。
- 层级：**最多 2 层**；每层每方向按相关性选最重要的 **3–5 篇（≤5）**。
- 总量：`trace_results[]` **10–20 封顶**。
- 停止：到第 2 层 或 每层满 5 篇即停止；`stop_rule` + `per_layer_cap=5` 事前写进 trace_summary。

## 三、脚本职责

| 脚本 | 职责 | 行数 |
|------|------|------|
| build_skeleton.py | Step 0 落骨架（case_id/contract/seed/材料清单）+ skill_marker.json 标志文件，三级容错 | ~220 |
| verify_check.py | 校验 trace 方向/层级/关联依据/来源回指/计数一致/枚举合法；--ablate all 退化；--emit-into 回写自检键 | ~200 |
| schema_guard.py | output_contract 全字段 + 业务 schema 结构守卫 | ~130 |

## 四、实跑对照数字

正例（合成 demo-cite-002：后向 3 + 前向 3 + 1 条 pending 缺 DOI）：

```
build_skeleton.py  exit=0  case_id=demo-cite-002，定位种子 S0，引文材料 1 个
verify_check.py    exit=0  PASS（4 类检查，problems=0）
schema_guard.py    exit=0  PASS
```

退化模式（--ablate all）：只跑结构检查，业务检查全部跳过 → 用于预算 <50% 时的
增益对照（正常多抓的 violations 即增益）。本包默认不跑增益层（available=false）。

负例（校验器必须抓到的 FAIL，全部 exit 0）：
- 清空某条 source_ref → FAIL：trace_results[].source_ref
- coverage.backward_count 改成 99 → FAIL：trace_summary 计数不符
- direction 写 "sideways" → FAIL：direction 枚举非法
- layer 写 0 → FAIL：layer 应为 >=1 整数
- pending=true 无 pending_reason → FAIL

## 五、保命铁纪律落地（4 条）

1. 第 0 步落骨架：SKILL Step 0 第一条动作即 build_skeleton.py。
2. 失败也交付：脚本三级容错 + 备用写盘路径，result.json 恒可解析。
3. 退出码恒 0 看 verdict：三脚本所有失败路径 exit 0，结论在报告 verdict。
4. 预算过半即定稿：预算 ≥32 请求/450 秒停止扩展，gain/efficiency 直接 available=false。

## 六、硬约束自查

- SKILL.md 行数 ≤150 ✓；frontmatter 合法（name/description 英文）✓
- 脚本 3 个 ≤8 ✓；零依赖（json/os/sys/argparse）✓；命令 python3 ✓
- 挂载 /skills/weekly-skill、输入 /input/case.json+task.md、产出 /app/output/result.json
  （含 case_id + output_contract 全字段，schema_guard 校验）✓
- 不预置答案：examples 全合成并标注"示意" ✓
- 标志文件定位：skill_marker.json 由 build_skeleton 落盘 ✓
- 禁 isalpha 汉字陷阱：本包不做标题语言启发式，标题逐字摘录不进归一化判定 ✓

## 七、诚实边界

- 追踪质量取决于输入材料覆盖度：材料没给的引用边一律登记缺口，不联网补。
- 增益对照默认关闭（available=false），仅预算宽裕时以 verify_check 双跑量化；
  不等于平台"基础 Agent vs 参赛 Skill"白板对照。
- 正式案例的实际追踪覆盖率须等平台运行后由白板对照判定。