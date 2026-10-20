# Fresh-input demonstration (arbitrary CSV)

The brief requires the saved pipeline to run on an arbitrary supplied CSV, and says a small fresh-input demonstration may be requested. This was run on 2026-10-19 after all code changes, on 40 real reviews the main run had **never classified** (out of scope, so no cached labels exist for them):

```bash
python -m pipeline run --input evals/fresh_input_demo/fresh_40.csv --state state/demo/fresh.sqlite --out evals/fresh_input_demo/out --batch-workers 1
```

| | |
|---|---|
| Input | [`fresh_40.csv`](fresh_40.csv) (six course columns, 40 rows) |
| Result | 40/40 completed, 0 quarantined |
| Stages (seconds) | ingest 0.11, enrich 10.05, verify 5.88, group 0.15, rank 0.01, memo 20.62; **wall clock 36.8 s** ([`run_summary.json`](out/run_summary.json)) |
| Calls / cost | 40 Jev label calls + 1 gpt quote call (enrich 41), 1 verify, 1 memo = 43 attempts, **$0.0039**, 0 failures |
| Handoffs | every stage's output is in [`out/`](out/): ingestion report, verifier predictions and disagreements, issue catalog, membership, aggregates, ranking, claims, memo |
| Memo | passed every code check on the first attempt ([`memo.md`](out/memo.md)) |

**Behaviour on tiny inputs:** issue discovery needs at least 8 complaint examples in a topic, so with 40 reviews every complaint went to its topic's catch-all (`-99`) and no grouping calls were made. The ranking is still computed and checked, but issue names are generic. On the full run every topic had enough examples (44 issues).
