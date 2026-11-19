# DOMAIN RULES — 文献阅读 Benchmark 与评测工具 (kind=reading_benchmark)

## Focus
- 判得动: task/input/reference/rubric complete so two graders agree.
- 跑得一致: repeat runs under fixed tools/budget stable; fluctuation recorded.
- 查得回: each score traceable via task ID to output/config/scoring record.
- 改得动: failure attributed to task type, feeds next revision.

## Rules
1. Define task cards (task/input material/reference answer/rubric/difficulty/license); version snapshots.
2. Unified runner fixes tools/prompt/budget/output format; normalize outputs to a scorable dir.
3. Score 0/1/2 per task with rule + human review; keep raw output + config + scoring record.
4. Run eval reproducibly; produce per-task scores + failure analysis; record stability.

## Self-check
- [ ] task cards decidable & complete
- [ ] runner fixed & reproducible
- [ ] 0/1/2 scores traceable
- [ ] failure analysis + versioning
- [ ] can't-judge not written as fact; gaps flagged; result.json honest
