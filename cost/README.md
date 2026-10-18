# Cost and runtime calculator

**Offline replay (default; no API key, no network, no model calls, Python standard library only):**

```bash
python cost/calculator.py                                    # recompute report.md / report.html / report.json / usage.csv
python cost/calculator.py --rates-multiplier 2 --out /tmp/x  # what-if: every API rate x2 with usage fixed
```

Edit [`rates.csv`](rates.csv) (dated, with source links) or [`assumptions.json`](assumptions.json) (budget, output-token cap, workers, fallback fraction, retry and volume assumptions), then rerun. Measured pilot numbers never change when you edit projections.

**Paid pilot execution (explicit, separate command; about $0.01):**

```bash
python -m pipeline pilot --confirm-paid
```

This runs the real pipeline on the unchanged `cost_100.csv` (checksum verified against the course manifest) with an empty result cache and one worker: enrichment, a declared verification sample, grouping, ranking and memo. It then reruns warm with the saved cache, and writes the files below.

| File | Contents |
|---|---|
| `pilot_records.jsonl` | one record per pilot ID (cold run), contract format with `source_sha256` |
| `pilot_records_warm.jsonl` | the warm rerun's records (all result-cache hits) |
| `pilot_calls.jsonl` | every attempt (cold + warm): role, step, model, effort, usage, cost, timing, request IDs |
| `pilot_runs.json` | settings, wall-clock and stage seconds for cold and warm runs |
| `checkpoint_500_*`, `checkpoint_10000_*` | estimate refreshes at 500 and 10,000 (two segments: before/after a query fix) |
| `rates.csv`, `usage.csv` | billing items: every charged item per call = billed units x price per unit |
| `report.md`, `report.html`, `report.json` | measured-100 tables, refreshes, base/conservative projections, controls, budget warnings |

The full run's actual charges ($4.95) are in [`../out/full/run_summary.json`](../out/full/run_summary.json), against the calculator's $4.98 base projection for the 100k scope.

Note: the pilot ran with memo prompt `memo-v2` and a 3% verify fraction with a minimum of 20. The final run used `memo-v3` (stricter evidence and claim rules); everything else was unchanged.
