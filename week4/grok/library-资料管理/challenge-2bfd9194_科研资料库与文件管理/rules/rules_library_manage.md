## Domain rules — library_manage
Goal: turn a messy real file batch into a trustworthy, hand-over-able library.
1. Inventory EVERY actual input file (w4kit.list_materials); register each used file in sources[] with its real path. Never infer content from a filename alone.
2. documents[]: one entry per logical document with document_id + source_id. Compute content hash; group duplicates BY CONTENT HASH, not by filename. Record alias conflicts (same alias claimed by two docs) instead of silently overwriting.
3. metadata{field:{value,status,evidence}}: fill title/authors/year/type/project/doi from filename, content, companion tables or manual entry. status in {reported,inferred,not_reported,source_conflict,extraction_failed}. reported/inferred/source_conflict REQUIRE an evidence locator; inferred requires an uncertainty note. A missing field is not_reported, NEVER a guessed value.
4. versions[]: rebuild the version chain by content hash + mtime; supersedes must reference a known version_id; note who replaced whom and the difference, with evidence.
5. operations[]: log every organize/dedup/rename/archive action with op_id + status {done,skipped,failed,conflict,pending}. skipped/failed/conflict REQUIRE a reason — no silent skips of huge/deep/no-permission/special-char files.
6. Output library_index.json (tree + metadata coverage + hash duplicate groups + alias conflicts + operations + unreadable list), provenance.json, report.md, result.json. Another person must be able to replay and check.
