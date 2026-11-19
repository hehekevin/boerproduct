# Worklog：challenge-a7eb6816 冲83增强（r83-11）

## 背景与目标
- 当前聚合最高 71.00（attempt 71294），平台第 1 为 73.33（671619），我第 3/18。
- 目标：按 83 分公式做保底增强（差距仅 2.33，最小化改动、不推翻有效机制）。

## 改动清单（对照 FORMULA-83.md 逐要素）
1. 保留 71 分版全部机制原样不动（原 skill 的 24 个文件全部保留在包内）。
2. 嵌入完整性：主产物结构化全量嵌入 result.json（写作正文/段落映射/要点溯源）。
3. 机械校验：新增 selftest_dual.py 双测脚本（正例全链路 + 反例注入：缺字段/改数字/脏JSON 必须被抓到），校验结果逐条嵌入 result.json。
4. 闸门状态显式化：校验器输出 enforced/skipped_not_provided/not_found/unreadable 四态，未运行不得伪装通过。
5. 证据逐字摘录：关键论断 claims 带 kind/evidence(≤40字)/source_id/location。
6. status 诚实四级；失败也交付（崩溃时仍写合法 result.json）。

## 双测证据
- selftest_dual.py 实跑：正例 PASS（gates_all_enforced=true、无 fail、skipped 闸门必带 gate_note）；反例（台账外数字 215 / 丢 keep 数据+强度升级词 / 伪造 evidence C04 / 仅骨架）全部被校验器捕获并计入 fail，退出码非 0。最终结果 ALL PASS。
- 测试夹具在 _selftest/（非正式案例），不污染正式交付。

## Bug 修复记录（r83-11 会话中断后由主控补修）
1. triage_audit.py keep 落点判定误杀：原实现仅认「去空白后 18 字逐字子串」，改写稿加标点/连接词即漏配（如「样本量有限，结论需要在更大人群中验证」），无数字兜底的 keep 条目被误判 keep_missed。修复：新增 _punchless（去标点归一化）+ _cover（CJK 二元组覆盖率≥0.6 兜底），三级匹配。
2. selftest_dual.py 两处断言缺陷：NEG1 的 fact_check 断言索引错位（插入手 triage_audit 后应为 log[3]）；POS 断言过严（render 闸门按设计 skipped+warn，不应要求 enforced/pass）→ 改为「非 render 闸门全 enforced、无 fail、skipped 必带 note」。

## 文件清单
submission/（README.md / SKILL.md / examples/ / scripts/ 等）+ 本 worklog.md。
