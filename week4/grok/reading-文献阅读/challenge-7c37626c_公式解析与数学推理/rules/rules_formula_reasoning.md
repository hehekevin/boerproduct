# DOMAIN RULES — 公式解析与数学推理 (kind=formula_reasoning)

## Focus
- 认得准: structure/symbols fully restored (sub/superscript, brackets, greek, units; no lost terms).
- 讲得清: each variable has source-backed definition/range/unit; not guessed silently.
- 推得顺: derivation split into checkable steps with assumptions/approximations/boundaries.
- 核验: numeric substitution check.

## Rules
1. Emit structure-checkable LaTeX; run formula.py structure check (balanced braces/left-right).
2. Build variable table (definition/unit/range/first-definition locator; defined-in-paper vs inferred).
3. Split derivation into steps with assumptions; mark cross-formula dependencies.
4. Run safe numeric-substitution check (AST, no arbitrary eval); report match/tolerance.

## Self-check
- [ ] LaTeX structure valid; symbols complete
- [ ] variable table source-backed
- [ ] derivation steps with assumptions
- [ ] numeric check passed/flagged
- [ ] can't-judge not written as fact; gaps flagged; result.json honest
