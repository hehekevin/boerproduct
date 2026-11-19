# DOMAIN RULES — 文献证据溯源与事实核验 (kind=evidence_verification)

## Focus
- 拆得开: split complex claims into fact/comparison/causal/scope sub-claims, no miss/dup.
- 找得到: minimal sufficient evidence per sub-claim, precise to sentence.
- 判得准: support degree matches original wording; partial/insufficient ≠ topic-related.
- 说得清: sources & uncertainty explicit.

## Rules
1. Decompose claims into typed sub-claims; note required evidence type.
2. Match minimal sufficient evidence with locator; assign supports/partial/insufficient/unrelated/contradicts.
3. Never judge 'supports' from topic relevance alone; handle secondary/cross-page/abstract-vs-body mismatch.
4. Output verification report with per-sub-claim evidence + degree + uncertainty.

## Self-check
- [ ] sub-claims typed & complete
- [ ] minimal evidence located
- [ ] support degree valid (unrelated≠supports)
- [ ] uncertainty explicit; report traceable
- [ ] can't-judge not written as fact; gaps flagged; result.json honest
