# Reproducibility evidence

| Check | How | Result |
|---|---|---|
| Ranking regenerates from saved outputs, no model | `python -m pipeline rerank --records grading/records.jsonl.gz --membership grading/membership.csv --out ranking_check.csv` (standard library only) | **byte-identical** to [`grading/ranking.csv`](../grading/ranking.csv) (44 issues), also from a fresh clone with system Python and nothing installed |
| Course checker recomputes ranking and claims | `python tools/check_submission.py check …` | 0 ranking or claim mismatches; only `unfinished_classification: 83379` (83,227 not reached before the credit limit + 152 invalid-output quarantines, all disclosed); coverage-point candidate 0.9243 ([`self-check.json`](../out/full/self-check.json)) |
| Identical inputs give identical outputs (pilot) | warm rerun of the 100-review pilot with the saved result cache, fresh run state | **0 new calls** (0 enrichment, verify, group and memo all cache hits), 100/100 records completed, 0.67 s ([`cost/report.md`](../cost/report.md)) |
| Identical memo inputs reuse the checked memo | memo cached by SHA-256 of its exact input + memo config | warm pilot memo `cache_hit: true` |
| Offline calculator replay | `python cost/calculator.py` (no key, no network) | same cold cost $0.009011. With `--rates-multiplier 2`: API spend exactly doubles, measured time unchanged |
| Published files match the recorded run | [`run_manifest.json`](../out/full/run_manifest.json) records SHA-256 for 61 published outputs | all 61 hashes verified against the git index before pushing |
| Resume does not relabel completed work | checkpoints [`before`](../grading/checkpoint_before.json) (131,915) ⊂ [`after`](../grading/checkpoint_after.json) (237,987); no `resume` call contains a before-ID | checker `resume_call_evidence` and `reprocessed_checkpoint`: no issues. See [recovery](recovery/README.md) |
