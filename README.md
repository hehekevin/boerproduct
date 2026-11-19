# boerproduct — Bohrium Product Arena 参赛答案仓库

按 **week（周）/ 赛道 / 题目** 三级分组，存放每周每题的最终提交包与提交证据。

## 目录结构

```
week{N}/
  reading-文献阅读/          # AI 文献阅读赛道
  writing-学术写作/          # 学术写作赛道
  illustration-科研绘图/     # 科研绘图赛道
  slides-学术幻灯片/         # 学术幻灯片赛道
    {challenge-id}_{题目中文名}/
      submission/            # 最终提交包（SKILL.md + scripts/ + README + worklog）
      trace.jsonl            # 平台提交时的执行 trace（提交证据）
```

## 每周提交流程

1. 平台提交完成后，把 `{包目录}/submission/` 复制到对应 `week{N}/{赛道}/{challenge-id}_{题名}/`；
2. 同目录放入当次 `trace.jsonl`；
3. `git add . && git commit -m "week{N}: {题目} 分数" && git push`。

## 命名约定

- 目录名：`{challenge-id}_{题目中文名}`，challenge-id 与平台一致，便于对照榜单。
- 赛道目录名与平台 track 字段对应：`reading / writing / illustration / slides`。
- commit message：`week{N}: {题名} {出分或变更说明}`。

## 第 3 周（week3）概览

25 题全部参赛：文献阅读 9 题、学术写作 11 题、科研绘图 4 题、学术幻灯片 1 题。
本期收官：总榜 24/760，窗口合计 1741.98 分，前三 3 题、前五 12 题。
每题包内含 worklog.md（迭代记录、对照实测数字、硬约束自检），SKILL.md 为平台加载入口。
