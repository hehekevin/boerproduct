# DOMAIN RULES — Academic talk content organization
(kind = `content_organization`)

From existing material to a *speakable* deck: goal, audience, narrative order,
per-page key message, and Q&A prep form a closed loop. Not a section-by-section
compression of the paper.

## 1. Report goal (checkable)
- Convert "what this talk must achieve" into a checkable goal (e.g. committee
  accepts method novelty; collaborators understand progress risk). The goal sets
  page count, duration and conclusion strength. Record `goal`.

## 2. Audience
- Identify prior knowledge, concerns, likely challenges. Set background proportion,
  terminology explanation depth, evidence depth. `audience` drives layout: e.g.
  reviewers → conclusion+evidence strength first; peers → method detail; committee
  → innovation+boundary.

## 3. Narrative order
- On the question→method→result→conclusion backbone, arrange selection and
 铺垫 with a tellable arc (起承转合), not paper TOC order. Each page has ONE claim
  (`claim`) + supporting evidence + figure; compress a paragraph to one speakable
  sentence; tag `evidence_strength` (established/supported/hypothesized/uncertain).

## 4. Key information & notes
- Per page: single claim, evidence, visual; speaker notes say what to SAY and match
  the claim (not repeat bullets). Conclusion strength must match evidence.

## 5. Q&A prep
- Anticipate challenges on mechanism/data/control/limitation; prepare `qa[]` with
  answer_points, a citable `backup_page`, and consistent口径. Backup pages hold
  extra evidence without cluttering the main line.

## 6. Correctness & template & export
- All claims/numbers/figure refs source-bound (`source`+`source_locator`); no
  fabricated facts. Respect audience/time/slide_count_target. Use provided template;
  notes+footer+page numbers; export via office-renderer; verify render matches pptx.

## 7. Self-check
- [ ] goal+audience+narrative+per-page key message+Q&A form a closed loop
- [ ] order serves audience & duration; one claim/page; evidence strength tagged
- [ ] notes correspond to claims; Q&A backup pages citable & consistent
- [ ] numbers/refs match source; template inherited; export clean; change log kept