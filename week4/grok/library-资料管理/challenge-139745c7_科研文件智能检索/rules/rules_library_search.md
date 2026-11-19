## Domain rules — library_search
Goal: find the right files/passages across the library, verifiably.
1. Build the index from actual documents (sources[] + documents[] with source_id). Register every searched file.
2. searches[]: each {search_id, query, scope[] (document_ids), filters{}}. query required; scope must reference registered documents.
3. The engine tokenizes query (CN+EN stopwords removed), matches against document content + metadata, ranks hits, and returns paragraph_id + quote locators. A query with no matching passage is status=no_hits, NOT an invented hit.
4. filters narrow by metadata field (year/type/project/author); a filter that excludes everything is reported honestly.
5. Output search_results.json (per-search hits + locators + status), library_index.json, provenance.json, report.md, result.json. Every hit traces to a real paragraph; quote text is verified against the actual document where readable.
