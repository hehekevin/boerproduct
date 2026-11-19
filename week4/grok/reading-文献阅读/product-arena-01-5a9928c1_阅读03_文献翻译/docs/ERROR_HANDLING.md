# ERROR_HANDLING — translation

| failure | detection | handling | status |
|---|---|---|---|
| requested passage absent from material | search all sources | segment status=not_reported, target_text=null, human_confirm | partial |
| no text layer / image-only formula / garbled source | extraction fails or quote unreadable | status=extraction_failed + reason; never guess translation | partial |
| ambiguous term / multiple plausible renderings | translator judgment | keep best rendering + uncertainty entry (term, alternatives) + human_confirm | success/partial |
| source versions conflict | differing source_text | status=source_conflict, both evidence locators + conflict note | partial |
| glossary violation | translation_check term_inconsistent | fix target_text to locked term; re-run | must_fix |
| number/citation lost | translation_check number_missing / citation_missing | restore exact number/marker in target; re-run | must_fix |
| mixed-language source | task.md + material | translate the requested direction; keep proper nouns/abbreviations as printed; note in uncertainty | success/partial |
| IR validation errors | exit 2 + validation.json | fix sources/locators/status vocabulary; re-run | partial until fixed |
| build exception | uncertainty entry | IR+validation saved; result.json partial with limits | partial |

Never omit or add content; never smooth over an untranslatable part; every gap has a
human-takeover point (human_confirm).