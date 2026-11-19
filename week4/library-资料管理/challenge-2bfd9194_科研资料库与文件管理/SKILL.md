---
name: lib-file-organizer
description: Scientific research library and file management skill (inventory manifest / rule-based classification / content-hash dedup / version chains / audit trail). Builds a hashed file manifest with provenance-tracked metadata, declares classification rules and naming conventions BEFORE any filing (declared_at gate), mechanically assigns categories with per-file rule citations and rename suggestions, detects duplicates by sha256 content equality (never by filename), rebuilds version chains from normalized name stems ordered by mtime, and emits a hash-linked operation audit trail where every op is replayable. Verify_check replays rules, recomputes hash groups and chain hashes, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to organize a batch of research files into a reviewable library with metadata, duplicates, versions and a replayable audit log.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架（含文件清单与 sha256）；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 files / classification_rules / duplicates / versions / ops / coverage / skipped_conflicts / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：清单**每一个**文件都必须处理（judged=true 或写明 skip_reason），禁止只处理前几个就收尾；文件缺失、无权限、哈希算不出的一律登记 skipped_conflicts 并给恢复方式，不静默跳过、不脑补元数据。
4. **不编造**：元数据逐字段记录出处（metadata_source）；哈希必须来自实际计算；重复/版本判断必须基于内容哈希而非文件名相似；对不上就登记，不改证据凑结论。
5. **规则事前声明**：分类规则与命名规范必须在**任何归类之前**写定（declared_at），之后禁止调整；每条规则给 rule_id，逐文件归类必须引用命中的 rule_id，不得事后改规则凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定一批科研文件（真实文件或 case.json 内联清单），完成**清单化盘点（哈希+类型+元数据出处）、规则驱动的归类与重命名建议、内容级去重、版本链重建、操作审计链**。不做网盘上传、不解析 PDF 全文、不迁移存储；文件缺失、无权限、内容损坏照实登记，不补造数据。
关键词：盘得清（每文件有哈希有出处）· 归得稳（规则事前声明、逐条可引用）· 重复按内容（sha256 判重，不按文件名）· 版本可重建（归一化主干 + mtime 排序）· 操作可回放（审计链逐条哈希链接）。
- 输入：`/input/case.json`（文件清单/内联内容 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- **脚本分工（多脚本禁写同一键）**：build_skeleton=骨架+清单+哈希；classify_files=category/rule_hit/rename_suggestion/action/directory_plan；duplicate_check=duplicates/versions/duplicate_of/version_*；audit_ops=ops；verify_check=coverage/verdict/self_check/gates/unbacked_numbers/validator_verdict；gain_probe=gain_evidence/efficiency。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与文件清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（files/documents 等）与 /input 目录合并提取文件清单；逐文件计算 sha256、识别类型、从文件名保守抽取 year/version_hint（出处记入 metadata_source）；生成 /app/work/classification_rules.json 声明模板。
- 脚本失败时手工兜底：读 case.json 抄文件清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 事前声明分类规则与命名规范（1 次响应，归类前完成）
- 填 `result.classification_rules`：规则逐条编号（R-01…），每条给 priority/match（ext/path_contains/name_contains 三类条件，中文一律子串匹配，**禁用 isalpha 判断**）/category/basis；fallback_category 兜底；naming_convention 给 pattern/regex/example。**declared_at 在任何归类之前填写，之后禁止调整**，同步写 /app/work/classification_rules.json。
- 环境与范围登记：`result.environment`（照实）、`result.library_profile.scope`（这批资料是什么、来自哪）。

### Step 2 — 逐文件登记（1 次响应，广度优先）
对 `result.files[]` 中**每一个**文件：补全 metadata（author/project/instrument 只在文件名/路径/伴随信息有据时填写并记出处）；无法核实的（文件缺失、无权限、损坏）写 skip_reason + `skipped_conflicts[]`（含 kind 与 recovery），置 action=skip；其余保持待归类。

### Step 3 — 机械归类与重命名（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/classify_files.py --result /app/output/result.json \
  --rules /app/work/classification_rules.json
```
- 按 priority 升序重放规则匹配（首个命中生效，全不中归 fallback），机械写出 category/rule_hit/rename_suggestion/action 与 directory_plan 目标目录树；规则未声明时归类整体暂停（不落无据结果）。
- 脚本失败时手工兜底：按同一规则手填并注明「手填」，事后仍须重跑脚本核对。

### Step 4 — 内容级去重与版本链（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/duplicate_check.py --result /app/output/result.json
```
- sha256 相同 → duplicates 组（保留最早 mtime 为正本，其余 duplicate_of + action=merge）；归一化主干相同且哈希互异 → versions 链（按 mtime 升序 version_rank，最新为 current）。哈希相同的一律进重复组，不进版本链。

### Step 5 — 审计链与增益对照（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/audit_ops.py --result /app/output/result.json --work-dir /app/work
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- audit_ops 为每个非 keep 操作生成 op_id + prev_op_id + chain_hash（sha256 链式）+ replay 复放命令；**实际执行整理动作后把对应 op.status 改为 done 并附证据路径**，未执行保持 planned，不冒充已完成。
- gain_probe 同一输入跑五遍：normal（五组检查全开）+ 四组消融（rules/duplicates/audit/all），真实漏检差写入 `result.gain_evidence`；`--inject-pollution` 在**副本**注入 4 类污染（改错归类/篡改哈希/断审计链/清空跳过理由），正常模式必须抓到，原 result.json 不被改动。退化模式结果仅用于增益对照，不得当作交付自检结论。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}`，不得编数字。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence/efficiency 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：清单每个文件都有归类或 skip_reason 吗？重复与版本都能回溯到内容哈希吗？每个非 keep 操作都在审计链里且有 replay 吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "library_profile": {"root": "/input", "scope": "…", "file_count": 8, "total_bytes": 0, "type_summary": {"csv": 2}},
    "classification_rules": {"declared_at": "step1", "declared_by": "agent", "rules": [{"rule_id": "R-01", "priority": 1, "match": {"ext": ["csv"], "path_contains": [], "name_contains": []}, "category": "raw_data", "basis": "…"}], "fallback_category": "unsorted", "naming_convention": {"pattern": "{category}_{stem}{ext}", "regex": "…", "example": "…"}},
    "files": [{"file_id": "F01", "path": "raw/a.csv", "file_type": "csv", "size_bytes": 42, "mtime": null, "sha256": "…", "sha256_status": "ok|ok_inline|no_content|unreadable", "metadata": {"author": null, "year": 2025, "project": null, "instrument": null, "version_hint": null}, "metadata_source": {"year": "filename"}, "category": "raw_data", "rule_hit": "R-01", "rename_suggestion": null, "action": "keep|move|rename|move_rename|merge|skip", "duplicate_of": null, "version_group": null, "version_rank": null, "skip_reason": null, "judged": true}],
    "directory_plan": {"target_root": "organized", "tree": "{\"raw_data\": 2}", "note": "…"},
    "duplicates": [{"group_id": "D01", "hash": "…", "member_ids": ["F01", "F02"], "keep_id": "F01", "action": "merge", "evidence": "sha256 完全相同"}],
    "versions": [{"group_id": "V01", "logical_name": "…", "member_ids": ["F03", "F04"], "order_by_mtime": ["F03", "F04"], "current_id": "F04", "evidence": "…"}],
    "ops": [{"op_id": "OP-0001", "prev_op_id": null, "chain_hash": "…", "op_type": "move|rename|merge|register|skip", "target_id": "F01", "detail": {"from": "…", "to": "…", "rule_id": "R-01", "basis": "…"}, "replay": "python3 audit_ops.py --replay OP-0001 …", "status": "planned|done|failed|skipped"}],
    "coverage": {"total_files": 8, "judged_files": 8, "classified": 7, "duplicates_groups": 1, "version_groups": 1, "skipped": 1, "ops_count": 8, "ratio": 1.0},
    "skipped_conflicts": [{"file_id": "F08", "kind": "no_permission|unreadable|name_conflict|hash_mismatch", "detail": "…", "recovery": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success|partial|unable_to_determine|refused", "reason": null, "manual_takeover": []},
    "verdict": "organized | partially_organized | not_organized | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"available": true, "runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"available": true, "wall_clock_seconds_total": 0.0, "checker_runs": 7, "files_processed": 8, "manual_items": 0, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "归类/去重/版本结论+哈希证据", "kind": "reported | inferred", "source_id": "F01", "location": "result.files[F01]", "evidence": [{"paragraph_id": "files[F01].path", "quote": "路径或哈希逐字引用"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. rules：declared_at 为空 / 规则空 / rule_id 重复 / 规则永不命中 / 命名 regex 编译失败；逐文件重放规则与 category/rule_hit 不一致。
2. judged：文件标 judged 但缺 category/rule_hit/skip_reason；action、sha256_status、verdict、run_status.state、op 枚举非法；merge 无 duplicate_of；version_group/rank 不成对。
3. duplicates：重算哈希分组与登记不符（漏组/成员错/正本错）；版本链顺序与 mtime 重算不符；版本链哈希不互异。
4. audit：chain_hash 重算不符（断链）；prev_op_id 断链；缺 replay；target 不在清单；非 keep 文件无操作记录；op_id 重复。
5. evidence：duplicates/versions 引用的哈希在清单中无回证；claims quote 不能逐字回证到所指文件的 path/sha256/category → unbacked_numbers 判 FAIL。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，文件内容均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root <空目录> --out /tmp/r.json --work-dir /tmp/wk
python3 scripts/classify_files.py --result /tmp/r.json --rules examples/example-rules.json
python3 scripts/duplicate_check.py --result /tmp/r.json
python3 scripts/audit_ops.py --result /tmp/r.json --work-dir /tmp/wk
python3 scripts/gain_probe.py --result /tmp/r.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result /tmp/r.json --case examples/example-case.json --out /tmp/wk/vc.json --emit-into
python3 scripts/schema_guard.py --result /tmp/r.json --case examples/example-case.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 清单为空 / 无文件 | files 空、coverage.total=0、verdict=cannot_verify，绝不补造文件 |
| 文件缺失 / 无权限 / 哈希失败 | sha256_status=unreadable 或 skip_reason + skipped_conflicts（含 kind 与 recovery），不静默跳过 |
| 元数据字段无据 | metadata 留空 + metadata_source=not_extracted，不按文件名猜作者/仪器 |
| 规则覆盖不了某文件 | 落 fallback_category 并登记 uncertainties，不临时加规则（要加先改 declared_at 前置声明并说明） |
| 大量同哈希重复 | 全部进 duplicates 组，保留最早正本，其余 merge，不逐个删 |
| 中文/特殊字符文件名 | 匹配一律子串/正则，禁用 isalpha（汉字返回 True 会误判） |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 已知限制
- 只整理输入清单内的文件：不上传网盘、不解析文档全文、不做存储迁移；真实移动文件由调用方按 directory_plan/ops 执行后回填 op.status。
- 版本链按「归一化文件名主干 + mtime」重建，主干相同但实为不同文档的极端情况会误并入链——已用哈希互异约束缓解，残余风险登记在 uncertainties。
- 增益对照是本校验层正常 vs 退化两模式对照，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
