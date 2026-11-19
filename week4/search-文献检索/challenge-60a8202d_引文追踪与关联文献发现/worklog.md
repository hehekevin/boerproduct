# worklog — cite-trace v1（challenge-60a8202d）

开发记录、真实对照数字与诚实边界。所有数字均来自 2026-11-19 本地实跑
（Windows 11 / Python 3.13，Git Bash），可按 README §15 命令复现。

## 一、设计决策（照第 3 周冠军包机制，领域逻辑全新）

| 继承机制 | 本题落地 |
|---------|---------|
| Step 0 落骨架 + build_skeleton | 保留；改为定位种子文献 + 引文材料清单 + declared_rules.json 模板 |
| 事前声明台账 | `declared_tolerances` → `declared_rules`（置信度阈值/剪枝停止/去重键/空方向处置，验算前写定） |
| 双候选强制运行 | → 双向追踪强制：backward/forward 任一为空必须登记原因（机检 coverage.backward/forward_registered） |
| 容差一致性 | → coverage 计数 = 列表长度（机器复算）；path hop_count = len(hops)；direct = (hop_count==1) |
| claims 逐字回证 | 论文数字回证 → 节点标题/年份须在 quote（norm_title 口径）+ 覆盖计数须在 claim text；unbacked 计入 FAIL |
| 三元组 + 闸门 + unbacked 回写 | 保留（self_check / gates / unbacked_numbers / validator_verdict 四键，verify_check 独写） |
| gain_probe 双模式 | 消融模式改为本题三机制：reasons（关联理由+回证）/ dedup（合并证据+键冲突）/ direction（方向覆盖+悬空端点/跳），--ablate all 默认 |
| 污染反例自测 | 注入 5 类本题污染：清空 source_ref / 虚增覆盖计数 / 清空合并证据 / 清空关联理由 / 清空 claims |

## 二、实跑对照数字（examples 链路，真实测量）

正例（合成案例 demo-cite-001：12 节点 / 8 边 / 后向 3 前向 5 / 2 组合并 / 1 环 / 1 孤立节点）：

```
build_skeleton.py  exit=0  case_id=demo-cite-001，定位种子 S0，引文材料 2 个
verify_check.py    exit=0  PASS（135 项检查，unbacked_numbers=0，unbacked_titles=0）
schema_guard.py    exit=0  PASS（case_id=demo-cite-001）
gain_probe.py      exit=0  正常 verdict=PASS ｜ 退化(all) verdict=PASS
```

gain_probe 五项指标（normal vs degraded，delta = normal − degraded）：

| 指标 | normal | degraded(all) | delta | 解读 |
|------|--------|---------------|-------|------|
| backed_edge_ratio_pct | 100.0 | 100.0 | 0.0 | 干净输入两边都判满，无区分度（区分度看污染自测） |
| violations_missed | 0 | 0 | 0 | 干净输入无违规可漏（同上） |
| manual_review_items | 14 | 27 | **-13** | 退化模式人工复核条目多 13 条（负值=退化更差=机制带来增益） |
| steps_count | 142 | 79 | 63 | 正常模式多执行 63 项机器检查（higher_is_better=null：步骤少≠质量高） |
| clarification_rounds | 5 | 9 | -4 | 退化模式追问轮次多 4 轮 |

污染反例自测（5 类污染注入副本，最有说服力的同校验器双跑 FAIL 差）：

| 模式 | verdict | problems | unbacked_numbers | violations_missed |
|------|---------|----------|------------------|-------------------|
| normal | FAIL | **7** | **13** | **0** |
| degraded(all) | FAIL | 2 | 0 | **3** |

- `caught_by_normal_mode = true`；`missed_detection_delta`：violations_missed +3、
  problems -5（即正常模式多抓 5 处）、unbacked_numbers -13（正常模式多回证 13 处）。
- 结论：同一校验器双跑，正常模式抓全 5 类污染（7 处问题 + 13 个未回证位），
  退化模式漏检 3 处客观违规、回证全部失效——增益证据成立。

## 三、负例测试（校验器必须抓到，全部 FAIL）

| 负例 | 注入 | 结果 |
|------|------|------|
| neg1 | 清空一条边的 source_ref | FAIL：edges[0].source_ref |
| neg2 | coverage.backward_edges=99 | FAIL：coverage.counts |
| neg3 | merge 证据清空 | FAIL：merges[0].evidence |
| neg4 | 关联理由清空 | FAIL：related[0].reason |
| neg5 | 节点标题改为 claims 中不存在的串 | FAIL：titles_backed（unbacked=1） |
| neg6 | 边端点指向未登记节点 GHOST | FAIL：edges[3].endpoints |
| neg7 | pending 边不进 pending_review | FAIL：edges[1].pending_registered |
| neg8 | 复制同标题节点、无合并记录 | FAIL：dedup.title_collision |
| neg9 | path 引用不存在的 ghost-edge | FAIL：paths[1].hops + hop_count（共 3 处） |
| neg10 | verdict=complete 但 forward 清空 | FAIL（共 5 处，含 verdict_complete_basis） |

## 四、汉字陷阱测试（硬约束 7：防 isalpha 汉字陷阱）

- `norm_title('稀疏混合路由：模块化神经检索（综述）')` = `'稀疏混合路由模块化神经检索综述'`
  （CJK 原样保留、标点剥除）——**不使用 isalpha/isalnum 类启发式**（汉字
  isalpha()==True，会把中文标题剥空或误判）。
- 中文标题节点 + 中文 quote 回证 → verify_check PASS、unbacked_titles=0（实跑验证）。

## 五、修复记录

1. `skip_check` 不支持 note 参数 → 签名补 `(item, template, reason, note=None)`。
2. `numbers_backed` 调用传 4 个位置参数与 note 撞名 → 收敛为 3 位置参数。
3. **标题回证口径 bug**：quote 用 `norm()`（只去空白）而标题用 `norm_title()`
   （去标点+小写），大小写不一致会全量误报 → 新增 `quotes_t`（quote 同走
   norm_title 口径）+ `backed_by_titles()`，首跑即 PASS。
4. Git Bash `/tmp` 与 Python `TEMP` 路径不一致导致首次复现脚本 FileNotFoundError
   → 测试脚本改用 `os.environ['TEMP']`（脚本本身全 argparse 参数化，无影响）。
5. verify_check 会把三元组回写进 --result 指向的文件，导致示例 fixture 被放大
   （17KB→50KB）→ 恢复干净版 fixture，自测一律在副本上跑；README 与
   SKILL.md 均注明该行为属预期。

## 六、约束自查（逐条过硬约束）

- SKILL.md **146 行** ≤150 ✓；frontmatter 合法（name/description 英文）✓
- 脚本 **4 个** ≤8 ✓；包 **8 文件 / 173KB** <2MB、≤50 文件 ✓
- 零外部依赖（json/os/re/sys/argparse/copy/time/math）✓；命令一律 python3 ✓
- 挂载路径 /skills/weekly-skill、输入 /input/case.json、产出 /app/output/result.json
  （含 case_id 与 output_contract 全字段，schema_guard 校验）✓
- **所有失败路径 exit 0**：负例/缺文件/脏 JSON 全部实测 exit 0，verdict 照实写报告 ✓
- 不预置正式答案：examples 全合成并标注"示意" ✓
- 多脚本禁写同一键：self_check 等四键归 verify_check 独写，gain_evidence/efficiency
  归 gain_probe 独写（README §14 维护约定明文）✓
- 防汉字陷阱：norm_title 显式字符类，CJK 保留 + 实测断言 ✓

## 七、诚实边界与剩余风险

- 增益对照是本校验层"正常 vs 退化"两模式，**不等于**平台"基础 Agent vs 参赛
  Skill"白板对照；平台对照由平台生成，gain_evidence.boundaries 已声明。
- 干净输入上 backed_edge_ratio/violations_missed 无区分度（两侧都满/都 0），
  区分度由污染自测提供——已在 mechanism_to_metric_map 注明，不掩饰。
- 追问轮次是折算估计量（每轮 3 条），非实测交互次数；原始计数一并落盘。
- 追踪质量最终取决于输入材料覆盖度：材料没给的引用边一律登记缺口，不联网补；
  正式案例的实际追踪覆盖率须等平台运行后由白板对照判定。
- model_requests 由 Agent 侧回填；本包交付时为 null，不臆造。
- 退化侧漏检数是下界（基础枚举检查仍开启），非最坏情形。
