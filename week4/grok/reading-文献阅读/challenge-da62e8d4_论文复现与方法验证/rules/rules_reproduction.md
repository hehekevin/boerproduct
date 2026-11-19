# DOMAIN RULES — 论文复现与方法验证 (kind=reproduction)

## Focus
- 找得齐: code/data/params/deps/license located to concrete versions; missing explicitly registered.
- 跑得对: env & key params restored per paper, not repo defaults.
- 对得上: repro results comparable to paper within pre-declared tolerance.
- 讲得清: differences attributed to env/data/params/seed/etc.

## Rules
1. Build executable parameter table (paper vs repo vs used) with sources; register missing items.
2. Record env/dependencies/versions; run with paper params; log steps.
3. Compare key metrics to paper with declared tolerance; compute within-tolerance.
4. Attribute each deviation (env/data/param/seed/eval); state reproduction conclusion honestly.

## Self-check
- [ ] materials/params located to versions; missing registered
- [ ] env/params per paper
- [ ] results within declared tolerance
- [ ] differences attributed; conclusion honest
- [ ] can't-judge not written as fact; gaps flagged; result.json honest
