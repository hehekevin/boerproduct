# worklog — exp-param-domain（challenge-ec02b694，v2 精简重构）

## 2026-11-22 v2 重构记录

### 重构目标（团队指令「极简单点」）
v1 包 0 分。根因：全方向（响应指标/参数响应图/优化建议/耦合约束/寻优策略/
候选策略比较 + 增益消融 + 结构守卫）链路过重，6 个脚本、150 行 SKILL，重放
Agent 在 64 请求 / 900 秒预算内难以走完，参数建议分散在多个键里。

v2 只做**突破方向第 1 条「关键参数识别与可行域约束」**，砍掉其余 4 个方向：
响应指标代理建模、搜索策略、成本权衡、风险深化——只在异常时一句兜底。

### 砍了什么
| v1 | v2 | 结果 |
|----|----|------|
| 6 脚本（build_skeleton/param_check/score_strategy/verify_check/schema_guard/gain_probe） | 3 脚本（build_skeleton/param_check/verify_check） | 删除 schema_guard、score_strategy、gain_probe |
| 150 行 SKILL | 113 行 SKILL | 单方向、五步流程 |
| 8 步流程（含策略比较、增益消融） | 5 步流程（骨架→参数→约束→数值校验→自检） | 增益层降级 available=false |
| parameters[] 需 param_id+domain{min,max,step}+current_value+basis(四枚举)+source_ref | name+current+range[lower,upper]+unit+basis(三枚举)+step | 键收敛为平台要求的最小集 |
| 建议需 expected_gain 四件套 | 不做建议，只判当前方案可行性 | verdict 改 feasible/infeasible |

### 参数规模上限
- **3–6 个关键参数封顶**，verify_check 硬校验 `MIN_PARAMS=3, MAX_PARAMS=6`。
- 每个参数只给 6 个字段：name / current / range[下限,上限] / unit / basis / step。
- basis 收敛为三枚举 manual|spec|literature（设备手册/材料规格/安全阈值都归 spec）。

### 脚本职责
| 脚本 | 职责 | 键归属 | 退出码 |
|------|------|--------|--------|
| build_skeleton.py | Step0 落骨架 + 标志文件 skill_marker.json + case_id/output_contract 提取 | result 骨架全部键 | 恒 0 |
| param_check.py | 受限 AST 求值器做可行域/耦合约束算术校验（域越界=硬违规、约束不成立=违规、步进不对齐=警告） | result.feasibility_check | 恒 0 |
| verify_check.py | 三组机检：params（3-6 个、字段齐、current 落域）/ cons（引用有效+none_declared）/ evidence（current 回证 claims）+ 常开检查 | 顶层 self_check/gates/unbacked_numbers/validator_verdict | 恒 0 |

### 保命铁纪律落地
1. 第 0 步落骨架 ✓（build_skeleton 三级容错，骨架必落）
2. 失败也交付 ✓（三脚本退出码恒 0，verdict 写报告）
3. 退出码恒 0 看 verdict ✓
4. 预算过半即定稿 ✓（gain_evidence available=false 说明预算保护降级）

### 实测对照数字（2026-11-22，合成案例 demo-paramdomain-001，Python 3.13.14）
- build_skeleton：exit 0，case_id=demo-paramdomain-001，contract 字段 6，材料 4 条，标志文件 3/3。
- param_check：exit 0，PASS（域越界 0，违规 0，警告 0；checked_count=6）。
- verify_check：exit 0，PASS（10 检查项全 applied）。
- 资源：8 文件，总计 79411 字节（<2MB），SKILL.md 113 行（≤150）。

### 保留的好东西
- param_check.py 的受限 AST 求值器（白名单四则/比较/and-or，函数调用与属性拒绝，
  连字符/中文参数名整串占位符重写，不用 isalpha）——从 v1 保留，但降级为
  可选主线的轻量工具（3 脚本之一，不是重负担）。
- 强制协议、退出码恒 0、标志文件定位、claims 数字回证——沿用 v1 成熟骨架。

### 诚实边界
1. 增益层降级（available=false）：不跑正常/退化双重增益对照，不冒充平台基础
   Agent 白板对照；平台白板由平台生成。
2. examples 为合成 fixture，材料/规格/文献/数据全虚构，不预置正式案例答案。
3. 算术校验基于登记的声明域/当前值（前瞻性规划口径），不代表实测实验室数据。