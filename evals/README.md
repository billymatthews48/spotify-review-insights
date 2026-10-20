# evals/: evaluation and system evidence

| Folder / file | What it holds |
|---|---|
| [`golden/`](golden/) | **50 human labels** ([`golden_50_labeled.csv`](golden/golden_50_labeled.csv); superseded first pass kept), labeling tool, per-case results ([`golden_eval_cases.jsonl`](golden/golden_eval_cases.jsonl)), per-field report ([`golden_eval_report.json`](golden/golden_eval_report.json)), gpt-only setup comparison, and the [error analysis](golden/error_analysis.md) (all 25 disagreements, quote support, entities) |
| [`verify/`](verify/) | **independent verifier**: procedure and disagreement analysis ([README](verify/README.md)), predictions, disagreements, **planted-error cases** (synthetic, 20/20 detected) |
| [`system_tests/`](system_tests/) | **synthetic** tests: 4 prompt injections, empty text, non-English, injected HTTP 503 (retry), injected invalid label (retry), spend-cap stop. [`results.json`](system_tests/results.json): 8/8 + spend cap passed; inputs in [`synthetic_reviews.csv`](system_tests/synthetic_reviews.csv); calls logged |
| [`recovery/`](recovery/) | **interruption/resume** recording (4-minute clip + full take) and [what it shows](recovery/README.md), with checkpoint counts before and after |
| [`fresh_input_demo/`](fresh_input_demo/README.md) | the full six-stage program run on a **new CSV** of 40 never-classified reviews (40/40 completed, $0.0039, 36.8 s), with all handoffs |
| [`reproducibility.md`](reproducibility.md) | deterministic rerank, warm pilot with 0 calls, offline calculator, manifest hash verification |

Synthetic rows (`synthetic-*` IDs, planted-error copies) live only in their own state DBs and files and never enter `grading/`, aggregates, the memo or the dashboard. Golden labels were never model inputs, examples or thresholds, and **golden results did not drive any prompt or configuration change**: every change after the pilot came from development data, run failures or the memo's code checks.
