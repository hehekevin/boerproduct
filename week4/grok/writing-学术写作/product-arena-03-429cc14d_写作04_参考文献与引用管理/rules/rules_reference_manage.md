# Domain rules — reference_manage (参考文献与引用管理)

## 1. Register the real library
- Read the ACTUAL library file(s); register each record in `references[]` with its raw
  fields (authors, year, title, journal, doi, volume, issue, pages) + `source`/`locator`.
- Register the manuscript; record each in-text citation point in `in_text_citations[]`
  {marker, ref_id, claim_text, source, locator}. Bind the marker to the claim it supports.

## 2. Normalize then dedup (收得净) — engine-computed
- `w4kit.normalize_doi`: strip `https://doi.org/`, `http://dx.doi.org/`, `doi:`,
  lowercase, trim trailing dot. `w4kit.normalize_title`: lowercase, collapse punctuation.
- `w4kit.dedup_records`: DOI exact match first, then fuzzy title (Jaccard ≥0.85) + year.
  Every input id lands in exactly one cluster; nothing silently dropped.
- Merge basis (`match`: doi / fuzzy_title_year / singleton) + field `conflicts`
  (title/year/journal/authors) are recorded in dedup_report.json. Representative =
  first record (prefer published over preprint when ordering the library).
- Ambiguous merges (same author, different work) → keep separate; flag human_confirm.

## 3. Format to target style (编得顺)
- GB/T 7714: `[n] AUTHORS. Title[J]. Journal, Year, Vol(Issue): Pages. DOI: ...`
- APA: `Authors (Year). Title. Journal, Vol(Issue), Pages. https://doi.org/...`
- IEEE: `[n] Authors, "Title," Journal, vol. X, no. Y, pp. Z, Year, doi: ...`
- Preserve DOI/volume/issue/pages/type identifier; omit absent fields gracefully and
  flag incomplete metadata. Numbering continuous [1..n] over unique clusters.
- Also emit BibTeX (references.bib) for editable reuse.

## 4. Consistency (对得上) — engine-computed
- missing_in_text: marker whose ref_id has no reference → flag + partial.
- uncited_references: cluster never cited → flag (human_confirm: cite or remove).
- duplicates: n_duplicates_merged + cluster members.
- conflicts: field disagreements within a cluster.
- Claim<->reference topic match is the Agent's judgment (record in claim_text +
  evidence); the engine checks structural linkage, not scientific truth.

## 5. Honesty
- Verification is against PROVIDED material (no live DOI lookup / no fabricated
  metadata). Unverifiable entry → mark uncertain + human_confirm. Missing fields →
  not_reported. Never invent authors/year/DOI to fill a gap.