# SYNTHETIC TASK (deep_research)

Labelled EXAMPLE; NOT an official case.

Decompose the research question into subquestions, plan retrieval over the provided corpus, bind every conclusion to exact source paragraphs, surface conflicting evidence and research gaps, and deliver a bounded synthesis. Do not claim field-wide completeness or completed experiments.

Inputs: case.json + this task.md + docs/s1.md..s8.md (fictional corpus).
Output: /app/output/result.json preserving output_contract + case_id, plus editable artifacts.
