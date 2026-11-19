# worklog — research-stat-audit（challenge-9e7302fd）

## 时间线（2026-11-19）

1. 读题面 `week4-dl/challenge-9e7302fd/task.md` 与第 4 期已交付同类包
   `bohrium-week4-final/challenge-0999879e/submission/`（骨架参考）。
2. 领域适配设计：本题特有机检点 = 检查项覆盖 / 统计量复算一致 /
   缺陷与报告不全区分 / 证据定位回证。据此在骨架上新增两套机制：
   - `stat_recompute.py`（新脚本）：六种统计一致性复算（r_to_t / t_to_p /
     ci_from_se / ci_vs_null / df_vs_n / group_shares），只写
     `result.stat_recompute` 一个键；
   - `defect_class` 字段（findings 必填）：method_defect / reporting_gap /
     cannot_classify / not_applicable，verify_check 强制映射。
3. 六分面改为领域分面：research_design / variable_definition / stat_method /
   sample_power / result_reporting / norms_consistency（对应题面五个检查面 +
   规范一致性；六类审查面中的事实核验并入 norms_consistency 的数值一致性，
   引用支持并入各分面的文献核对——这是范围取舍，见"边界"节）。
4. 写 6 个脚本 + 2 个示例 + SKILL.md / README.md，全链路实测后回填增益证据。

## 实测对照数字（真实运行，非手填）

- 环境：Windows 11 / Python 3.13.14 / 仅标准库。
- `stat_recompute` 对合成案例 4 条 stat_claim：**3 矛盾 + 1 一致 + 0 无法判定**
  （F02 r=0.32,n=48 复算 t≈2.29、p≈0.022 与宣称 p<0.001 矛盾；F03 df=52 超出
  n-1=35 与两组设计 n=36 矛盾；F04 CI 宽 0.10 vs 2*1.96*SE=0.392 相对差 74.5%；
  F11 t=2.10↔p=0.04 正态近似 p≈0.0357 容差内一致）。
- `verify_check`（干净输入，ablate=none）：**PASS，49 条检查项全部 applied**。
- `schema_guard`：**PASS**（case_id=demo-researchstat-001）。
- `gain_probe` 同输入双跑：normal PASS / degraded PASS，干净输入六类漏检全 0，
  steps_count normal=57 vs degraded=8（delta +49）。
- 污染反例（副本注入 7 项，含**把 CI 与 SE、df 与样本量矛盾的复算记录翻转为
  「一致」**的统计量篡改）：
  - normal：verdict=**FAIL**，15 处问题，六类漏检全 0（stat_missed=0）；
  - degraded：verdict=**PASS**，0 处问题，漏检 location=1 / evidence=9 /
    pending=1 / **stat=2**；problems delta=−15。
  - caught_by_normal_mode=true；原 result.json 未被改动。
- 失败路径：六脚本对缺失 result.json / 缺 case.json / 未知参数
  **全部退出码 0**（实测，含 argparse SystemExit 捕获补丁）。
- `SKILL.md` 150 行（≤150 达标）；整包 11 个文件、约 100 KB（<2 MB、≤50 文件达标）。

## 开发中修掉的 bug

1. **`cleared` 未定义**（骨架参考包 coverage_audit.py 遗留缺陷）：audit() 引用
   未定义变量导致整函数异常、coverage 无法回写。本包已修复为 `clearances` 集合。
2. **stat_recompute 格式串 `% C` 陷阱**："95% CI..." 中的 `% C` 被 `%` 格式化
   解析为非法格式符 → 改为 `95%%`（与包内"isalpha 汉字陷阱"同类的机械陷阱防御）。
3. **argparse 失败路径退出码 2**：未知/缺失参数时 argparse 直接 SystemExit(2)，
   违反"所有失败路径 exit 0"。六脚本统一打补丁：`parse_known_args` 容忍未知参数
   + `__main__` 捕获 SystemExit 强制 exit 0（实测覆盖）。
4. **零发现分面豁免语义不一致**：coverage_audit 认 clearances，verify_check 原版
   不认 → 已登记豁免仍判 FAIL。verify_check 的零分面规则改为与 coverage_audit
   同一口径（scope=facet:* 豁免生效）。

## 设计取舍与诚实边界

- **六分面 vs 题面六类审查面**：题面评分表同时提到"五个检查面"（研究设计—变量
  定义—统计方法—样本量—结果报告）与六类审查面（事实核验/引用支持/…）。本包
  采用五检查面 + 规范与一致性合成的六分面；事实核验并入 norms_consistency 的
  前后数值一致性，引用支持由各分面的文献核对条目承担。若平台案例的 output_contract
  要求原六类枚举，需按 case.json 实际字段在运行时适配（脚本枚举表集中定义，单点可改）。
- **正态近似**：标准库无 t 分布分位数，p 值复算是近似核验（容差 0.01/0.015）；
  极端边界值可能误判，故设 indeterminate 三值兜底，不冒充精确检验。
- **复算 ≠ 事实核查**：复算只证明"报告的数字组合在算术上不成立/成立"，不能验证
  原始数据真伪；定性由 Agent 按 severity_rubric 判断，复算值仅作对照证据。
- **缺陷/报告不全的边界情形**："报告了但报错"按 fact_error（method_defect）处理
  并写明依据；"拿不准"标 cannot_classify 并转 pending，不强行二选一。
- **增益对照边界**：normal vs degraded 是本校验层两模式对照，不等于平台
  "基础 Agent vs Skill Agent"白板对照；后者由平台生成，本包不代替、不冒充。
- **统计量污染注入只翻记录**：污染副本把复算记录 consistent=false 翻成 true
  （模拟"复算结果被篡改/未如实记录"），不改动 stat_claim 本身——篡改 claim 会让
  复算与新值一致，反而测不出校验层价值。
- examples/ 全部为合成案例并标注"示意/非正式答案"，不预置正式答案。

## 遗留风险

1. 题面六类审查面枚举若与六分面不一致（见上），运行时需按 case.json 适配——
   枚举表在 build_skeleton/coverage_audit/verify_check 三处同步定义，改漏一处会
   被 verify_check 自己抓出（facet 枚举非法），属可发现故障。
2. 正态近似对 df<15 且 p 值精度要求高的断言区分度下降（容差已放宽并注明）。
3. 缺陷/报告不全映射对"部分报告但报告错了"的混合情形只能取主类别，语义粒度
   有限（已写进 SKILL.md 已知限制）。
4. result.json 中 gain_evidence/efficiency/self_check 由脚本实测回填；平台真实
   运行时的 model_requests 需 Agent 侧回填，缺失保持 null（不臆造）。
