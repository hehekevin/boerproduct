# worklog — challenge-b810ef56 重做（目标 ≥70 分）

## 背景
- 原提交 acwrite-evidence 聚合最高 60.00（历史 71938 排队 / 72459:52 / 72501:60）。
- 60→70 差距定位：**论断-证据映射的完整性与可核验性**——每句事实性陈述可回溯到来源。

## 本次改动（v2）

### 1. 证据池先行（新增流程硬规则）
- Stage 2 先从 extracted/*.txt 全文逐字摘录建 evidence_pool.jsonl（qid+locator+quote+strength_hint），Stage 3 论断只允许绑定池内摘录，quote_ids 与 sources 双登记。
- 摘录要求连限定语（样本量/条件）一起摘，防写作时丢边界。

### 2. 摘录逐字机器核验（evidence_audit.py 升级，核心新增能力）
- 每条 bound 论断的 quote 经空白归一化后与来源 M*.txt 做子串匹配（首 40+尾 40 字符探测），**quote_not_verbatim 即编造/改写风险**，机器可判，不再依赖评审肉眼。
- locator 的 mid 必须存在于 extracted 目录（locator_bad）；sources 目录缺失时核验降级并如实记录（不伪造通过）。

### 3. 论断↔来源双向映射矩阵
- claim→source 正向 + source→claims 反向索引，写入 evidence_audit.json 与 result.json（claim_source_matrix）。
- 孤儿来源检测：registry 中未支撑任何 bound 论断且未在正文引用的来源（orphan_source）——防文献表挂空引用。

### 4. result.json 自包含（build_result.py 升级）
- --draft-json 嵌入成文全文（deliverable_text）；--claims 嵌入论断-证据表并生成双向矩阵；三份检查报告（fact_check/consistency/evidence_audit）全部内嵌。评审不看附属文件也能逐条复核。

### 5. 已验证方法全部落实
- 协议置顶：抄契约+立即落骨架+字段一个不缺+广度优先+48次/700秒熔断+写盘自检+失败也交付。
- 线性 ≤5 内容步骤；SKILL.md 117 行（≤250）；资源 7 脚本（≤8）；主产物完整嵌入。
- 脚本三级容错：输入缺失/损坏输出 fail 报告不崩溃；无硬编码平台路径（全部 CLI 传参）。
- status 诚实；材料不足标缺口不编造（unbound→uncertainty）。

## 本地双测记录（全链路，2026-11-13）
| 测试 | 结果 |
|---|---|
| extract_materials + fact_ledger build/check | 7 条事实入账，稿件数字全部回查 pass |
| evidence_audit 故意注入编造摘录 | 正确抓出 quote_not_verbatim(C02) ✓ |
| evidence_audit 故意注入孤儿文献 R3 | 正确抓出 orphan_source ✓ |
| evidence_audit 修复后 pass 场景 | verdict=pass, problems=[] ✓ |
| docx_build | python-docx 真实 docx + md ✓ |
| consistency_check | 5 项全 pass ✓ |
| build_result | 契约字段自动展开、deliverable_text/claims/matrix 全嵌入 ✓ |
| 三级容错（claims 文件缺失） | 输出 claims_unreadable fail 报告，不崩溃 ✓ |

测试中修掉的 3 个误报：unbound 行结构全豁免、cid 前导零归一（C01↔E1）、句切分不再切断小数点+参考文献行不再误报裸论断。

## 遗留/边界
- 逐字核验依赖 extract_materials 的 M*.txt；扫描件 extracted:false 时核验降级如实记录。
- DOI 真实性离线不可核验（标 doi_unverified_offline），只能核验"摘录确实来自材料"。
- 未提交，等 team-lead 确认。
