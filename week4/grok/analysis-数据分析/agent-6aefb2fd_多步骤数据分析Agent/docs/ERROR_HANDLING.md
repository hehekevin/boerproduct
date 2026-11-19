# Error handling — analysis-multi-step

Principle: honest cascade — a failed upstream step never produces a fabricated downstream result.

| Situation | Engine behavior | Agent action |
|---|---|---|
| Dependency failed / absent | dependent step SKIPPED with reason; overall partial | fix upstream step payload; rerun |
| Unreadable / empty dataset | load step partial; dataset status recorded | register what exists; partial early |
| Cleaning op failed / consistency mismatch | clean step partial | fix rule/data; rerun |
| Stats insufficient n / failed | stats step partial; metrics absent | report gap; do not invent numbers |
| Viz skipped missing rows / failed | viz step partial | state caliber; clean upstream |
| Query failed / empty | query step partial | fix SQL/keys; read-only only |
| Interpret back-fill mismatch | claim fail; interpret step partial | fix text or analysis to be same-source |
| Interpret text missing | interpret step partial | write the narrative |
| Forward depends_on reference | validation error | reorder steps |
| IR validation errors | validation.json; result still written (partial) | fix IR; rerun |
| Build exception | honest partial/failed + build_error | read traceback; fix; rerun |

Step status: done|partial|failed|skipped. Result: success|partial|failed|stuck.
Per-step provenance records inputs (dataset sha) → outputs → status, so failure is locatable
and recovery is per-step (rerun recomputes downstream from the shared context).
Every gap: {item, reason, impact?, handling: human_confirm} in uncertainty[].