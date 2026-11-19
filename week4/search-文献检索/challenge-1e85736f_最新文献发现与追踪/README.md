# lit-track-incremental — 最新文献发现与追踪 Skill（v1）

> 面向「主题订阅 / 定期检索 / 增量识别 / 去重 / 更新判定 / 提醒」场景的可复用 Skill。
> 本 README 是使用与方法说明；Skill 行为契约见 `SKILL.md`；制作过程与实测数字见 `worklog.md`。

## 1. 用途与适用条件

解决"一次性主题检索改名叫追踪"的痛点：每个时间窗口内，相对上次快照**机械地**找出
真正新增的文献，并压住三类噪声——

| 噪声类型 | 本 Skill 的机制 |
|---------|----------------|
| 重复结果（同文多源转载、标题标点/大小写差异） | 稳定去重键：`doi > arxiv_id > title_norm`（casefold + 去标点空白，`\w` 含 CJK 汉字，**不用 isalpha 判字**） |
| 版本混淆（预印本→正式版→修订→撤稿，DOI 与 arXiv 编号并存） | 版本链归并：同 dedup_key **或同 title_norm** 按发表日升序成链，正式版判 version_update，撤稿判 retraction（只登记不推送） |
| 延迟与漂移（数据库入库滞后、窗口边界条目） | 时间窗判定区分 `backfill`（延迟入库补回，可推送）与 `out_of_window`（旧条目重复投喂，必须排除）；窗口起止 + 时区事前声明 |

适用条件：输入为组织方提供的固定记录集（真实署名文献 + 少量合成重复/撤稿/回补夹具），
含主题、窗口/快照线索与 output_contract。**不适用**：数据库实时抓取、全文精读、
自动写综述、未经授权的定时爬取。

## 2. 目标用户与典型场景

- 科研人员/Agent：按主题订阅领域新文献，要求每次增量可回放、可复核。
- 场景 A：本周窗口内哪些是**真正的新论文**（相对上次快照）？
- 场景 B：某篇预印本是否已出正式版？撤稿/勘误是否波及已推送条目？
- 场景 C：聚合源投喂的旧文献与转载条目如何静默压掉而不打扰用户？

## 3. 依赖与环境

- Python ≥ 3.8，**仅标准库**（json / re / os / argparse / copy / math / time），零 pip 依赖。
- 脚本共 5 个（≤8 上限内）：`build_skeleton.py` / `track_engine.py` / `verify_check.py` / `gain_probe.py` / `schema_guard.py`。
- 运行时路径约定：输入 `/input/case.json` + `task.md`；工作区 `/app/work`；产物 `/app/output/result.json`；Skill 挂载于 `/skills/weekly-skill`。
- 无外部网络请求；无随机数（`seed` 恒 null），同输入同输出，重跑幂等。

## 4. 安装与运行

```bash
# Step 0：自动落骨架 + 记录清单 + 追踪口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明窗口/水位/去重键/权重（写入 result.* 与 /app/work/track_policy.json），
#           然后逐条判定（见 SKILL.md 七步流程）

# Step 3：机械引擎——去重键/时间窗/版本链/时效排序（写 result.ranking 等）
python3 /skills/weekly-skill/scripts/track_engine.py --result /app/output/result.json \
  --case /input/case.json

# Step 4：Agent 登记待复核 + claims 证据链（数字逐字回证）

# Step 5：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

**所有校验脚本退出码恒为 0**（失败路径也 exit 0）；成功/失败以报告内 `verdict`
（PASS/FAIL）与 `problems[]` 为准——语义值返回，不用退出码传递失败。

## 5. 输入与输出

- 输入：`/input/case.json`（`records[]` 记录集、可选 `previous_snapshot[]` 上次快照、
  `output_contract` 字段名）+ `task.md`。以实际文件为准，不依据标签假设内容。
- 输出：`/app/output/result.json`，含 case_id、status 与 output_contract 全部字段。
- 核心业务键：`result.window` / `result.watermark` / `result.dedup_policy` / `result.rubric` /
  `result.items[]`（event ∈ new|version_update|duplicate|backfill|retraction|out_of_window，
  label ∈ push|hold|exclude）/ `result.ranking` / `result.version_chains` /
  `result.source_registry` / `result.conflicts` / `result.pending_review` / `result.coverage` /
  `result.gain_evidence` / `result.efficiency` / `claims[]` / `uncertainties` / `changelog`。
- 键归属（多脚本禁写同一键）：骨架+Agent 写业务内容；`track_engine.py` 只写
  dedup_key/in_window/event/related_to/track_score/rank/ranking/version_chains；
  `verify_check.py` 只写 self_check/gates/unbacked_numbers/validator_verdict；
  `gain_probe.py` 只写 gain_evidence/efficiency。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/example-case.json`（8 条合成记录：2 新增、1 预印本→正式版跨键版本链、
1 同 DOI 转载、1 撤稿、1 窗外旧条目、1 延迟入库、1 缺日期）+ `examples/example-result.json`
（全链路实跑产出，文件头 `_note` 已标注示意）。本地自测：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples \
  --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/track_engine.py --result examples/example-result.json --case examples/example-case.json --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --policy /tmp/wk/track_policy.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

最小自检清单（每项都实测过，见 worklog.md 对照数字）：

```bash
# 1. 结构：schema_guard PASS（退出码 0，verdict=PASS）
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
# 2. 业务：verify_check PASS（31 项机械检查全 applied，含 dedup_key 复算、track_score 复算、数字回证）
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json
# 3. 增益：gain_probe 两遍跑完，污染反例 caught_by_normal_mode=true
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
# 4. 失败路径：故意喂坏文件，退出码仍为 0
python3 scripts/verify_check.py --result /nonexistent.json; echo "exit=$?"
```

## 8. 增益对照机制（增益可验证性）

- **同输入双跑**：`gain_probe.py` 对同一份 result.json 依次跑正常模式（四组校验全开）与
  退化模式（`--ablate all`），逐项对照漏检数，delta 写入 `result.gain_evidence.delta_normal_minus_degraded`。
- 五项指标：事件-标签违规漏检 / 排序失据漏检 / 证据缺失漏检 / 登记漏项 / 需人工核对条目数。
- **污染反例注入**（`--inject-pollution`）：在副本上注入 5 类污染（push 无证据、篡改
  track_score、清空 pending_review、清空 claims、抹掉 related_to），正常模式必须全部抓到
  （caught_by_normal_mode=true），且原 result.json 不被改动。
- 实测对照（合成示例，详见 worklog.md）：干净结果上正常模式比退化模式多执行 29 项检查
  （steps_count 38 vs 9）；污染副本上正常模式 FAIL 抓出 16 处问题、退化模式 PASS 0 处
  （漏检 delta：consistency +1 / order +1 / evidence +6 / registry +4）。
- 边界（诚实声明）：该对照是本校验层 normal vs degraded，**不等于**平台基础 Agent 与
  参赛 Agent 的白板对照；平台对照由平台生成。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 来源无响应 / 记录集为空 | items 空、coverage.total=0、verdict=cannot_verify，source_registry 记 failed，不补造文献 |
| published_date / DOI 缺失 | missing_metadata 登记 + 置信度降级，hold 进待复核 |
| 时区错位 / 边界条目 | window.timezone 显式声明；边界按 start<=date<=end 判入并注明 |
| 预印本→正式版跨键 | title_norm 归并成链；无法确认同一性则 escalated 进待复核 |
| 撤稿 / 勘误 | event=retraction 登记链，绝不 push，走人工更正通道 |
| 校验 FAIL | 按 problems 逐条修复后覆盖重跑；修不了如实登记 uncertainties，不中断交付 |
| 运行中断 | 仍写 result.json（status=partial），注明中断点与已完成部分 |

## 10. 常见问题 FAQ

- **Q: 为什么推送条目 push 要求 relevance=direct？** 误报直接消耗信任；间接相关一律 hold 待人工确认，宁可漏推不误推。
- **Q: 撤稿算新发现吗？** 算重要事件但不算新文献：event=retraction 登记进版本链，提醒走人工更正通道，绝不做 push 动作。
- **Q: 为什么还有 hold？** 延迟入库的预印本（已被正式版取代）、综述类间接结果、缺日期条目都进待复核——机器判定面不越界。
- **Q: 校验脚本 exit 0 但 verdict=FAIL 是什么意思？** 语义在 verdict 不在退出码：交付流永不因校验失败中断，但 FAIL 必须修复或如实登记后才能宣称"已核对"。
- **Q: dedup_key 会不会误伤中文标题？** 归一化用 `\w`（Unicode 词字符，含 CJK），显式不用 `isalpha()`（汉字 `isalpha()=True` 会破坏 ASCII/汉字区分），校验器逐条复算 dedup_key 保证可复算。

## 11. 适用范围与限制

- 仅处理输入记录集内文献；不做实时检索、不全文精读、不做授权外定时抓取。
- 改题换封面（同一论文换标题再投）无法机械归并，只能 escalated 待复核兜底（已在
  gain_evidence.failure_conditions 声明）。
- recency/confidence 归一化口径是本技能设定（窗口天数线性、置信三档），非外部标准，随 rubric 落盘可复算。
- 增益对照不代替平台白板对照；追问轮次按每轮 3 条折算，非实测交互次数。

## 12. 复用建议（给其他作者/其他赛道）

- 换主题只需换 case.json；换时间粒度（周/月）只改 `result.window` 声明，引擎与校验零改动。
- 追踪口径模板 `/app/work/track_policy.json` 可直接作为订阅配置模板复用。
- 新增校验维度时在 `verify_check.analyze` 加一组并以 `--ablate` 组名接入 gain_probe，
  保持"客观违规由 gain_probe 独立复算、校验器只负责捕获"的双实现结构。

## 13. 资源清单

```
submission/
├── SKILL.md              # 行为契约（150 行内）：协议 / 七步流程 / schema / 机检点 / 异常
├── README.md             # 本文件：使用说明 + 生态十项 + 最小自检清单
├── worklog.md            # 制作过程与实测对照数字（真实数据，含诚实边界）
├── scripts/
│   ├── build_skeleton.py # Step 0：骨架 + 记录清单 + 口径模板（三级容错）
│   ├── track_engine.py   # Step 3：去重键/时间窗/版本链/时效排序机械引擎
│   ├── verify_check.py   # Step 6：四组业务校验（--ablate 可消融）
│   ├── gain_probe.py     # Step 5：增益双跑 + 污染注入 + 效率计数
│   └── schema_guard.py   # Step 6：output_contract 结构守卫
└── examples/
    ├── example-case.json    # 合成案例（8 条记录，非正式答案）
    └── example-result.json  # 全链路实跑的示意输出（_note 已标注）
```

## 14. 版本与维护

- v1（2026-11-19）：首版。5 脚本 / 8 文本资源文件 / 全部标准库 / UTF-8。
- 维护入口：改 `track_engine.py` 的归一化或分类规则时，必须同步 `verify_check.py` 的
  复算逻辑并重跑 examples 自测（第 7 节四条命令）。
