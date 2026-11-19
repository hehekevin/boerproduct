# ERROR HANDLING & FAILURE MODES

Identify,处置 and **record** problems; never silently fabricate. Every handled
issue goes to `IR.uncertainty[]` (item/reason/impact/handling) and, if it changes
the figure, to `IR.provenance.changes[]`. Set `result.status` honestly.

| Failure | Detect | 处置 | status |
|-|-|-|-|
| Missing material / unreadable PDF | file absent, pdf-text returns empty | state which source is missing; draw only what is supported; list gap | partial |
| Domain label conflicts with file | tag says one field, content another | trust the actual file; note the conflict | success/partial |
| Entity name ambiguous (gene vs protein, synonym) | same symbol, different kind | keep source spelling; set category from context; add uncertainty; do not merge distinct entities | success |
| Relation direction missing | text gives no direction | use `direction:none` + `confidence:low`; do NOT guess a direction; flag | partial |
| Inhibition vs activation unclear | vague verb | choose the conservative type; record ambiguity; never default to activates | partial |
| Data column missing / empty / non-numeric | read_table yields None | skip that glyph, keep others; record; do not impute | partial |
| Magnitude/unit anomaly | value orders of magnitude off, unit mismatch | keep source value; flag for human check; do not "fix" silently | partial |
| Legend/series mismatch | legend count != series categories | renderer auto-generates legend from data so they match; if manual legend conflicts, rebuild from data | success |
| Label too long / overflow | node text wider than box | renderer sizes node to label; if still overflowing, wrap or abbreviate with source note | success |
| CJK font missing (boxes) | font not in font_manager | fall back to an available CJK font (Noto/WenQuanYi/YaHei); record font_used | success |
| Export format unavailable | savefig raises (e.g. eps/tiff backend) | skip that format, keep others; record in uncertainty | partial |
| Canvas overflow / too many elements | layout exceeds canvas | increase canvas or split into panels; record | success |
| Validation errors | assemble exit 2 | fix IR errors; re-run; if unfixable, save partial with limits | partial |

## Principles
- **Fail loud, not silent.** A wrong-but-pretty figure is worse than an honest
  partial one. Reviewers score verifiability, not gloss.
- **Partial is valuable.** Save `result.json` with `status:partial` and explicit
  `limits` early; improve incrementally within budget.
- **Never fabricate** missing software state, scientific data, or benchmark scores.
- **Reproducibility:** keep `figure_ir.json` + `provenance.json` + the exact
  command so a reviewer can re-run and get the same figure.