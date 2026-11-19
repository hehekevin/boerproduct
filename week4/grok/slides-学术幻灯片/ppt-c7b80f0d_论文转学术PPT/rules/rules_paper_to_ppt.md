# Domain rules — paper_to_ppt (论文转学术PPT)

## 1. Extract the main line (not paragraph order)
- Identify the paper's problem, core approach, key evidence, conclusion. Build a
  tellable narrative backbone: question -> method -> result -> limitation -> conclusion.
- Distinguish main conclusions from supporting detail; put detail in backup/qa.
- One `claim` per page; the claim is the page title. Do not paste abstract/body
  paragraphs verbatim into pages.

## 2. Page structure & information layering
- Decide each page's claim, bullet count and hierarchy; rewrite long paragraphs into
  tellable phrases. Respect template max_bullets / max_words_per_bullet / min_pt.
- role ∈ title/outline/background/question/method/result/discussion/limitation/
  conclusion/qa/backup/section. First page role=title.

## 3. Evidence preservation (engine-checked source binding)
- Every bullet and figure binds `source` + `source_locator` (paper section/paragraph/
  figure/table/page). deckkit errors on unregistered sources; provenance.page_map maps
  each page -> claim/bullets/figures locators.
- Preserve numbers, units, method names, conclusion wording, figure numbering + captions
  + necessary conditions. Never misattribute (张冠李戴), never present a schematic as
  experimental data, never present others' results as this paper's.
- Figures: data-bound `chart` from real data (data_path/x/y/series/error/n) OR cited
  `image_path`. No placeholder, no invented curve. Missing bitmap → cite original or
  state limit.

## 4. Speaker notes & Q&A
- `notes` correspond to the page but do NOT repeat page text: transitions, emphasis,
  supplementary evidence for likely questions.
- `qa[]`: anticipated questions + answer_points + source + backup_page.

## 5. Template & layout
- Inherit provided template layouts/placeholders/theme fonts/colors; keep footer + page
  number consistent. Handle long titles, multi-figure rows, big tables. Overflow →
  cut/split, never shrink below min_pt. CJK font fallback when needed.

## 6. Export & editability
- Editable PPTX (real text runs, not images) + source-bound outline.md. Export PDF/PNG
  via office-renderer (true render); honest labelled fallback if absent (status partial).
- Record provenance.changes[] for version-safe local edits; never break the master.
- Honest status/sources/uncertainty/change_log; gaps human_confirm; never fabricate.