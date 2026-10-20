# 100-review cost and runtime calculator

Offline replay of saved measurements; rates multiplier **x1.0**. Regenerate with `python cost/calculator.py` (no API key, no model calls).

## Measured pilot (cost_100.csv, unchanged)

- Input: `cost_100.csv` sha256 `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e`; 100 source IDs; 100 completed, 0 failed/quarantined; 100 distinct texts enriched.
- Settings: label_config `jev-1.13.0+gpt-6-luna/none+prompts-v1+schema-v1+labels-v1`; enrichment batch <= 50 reviews; workers: batch 1, Jev 1 (one worker, as specified).
- Models: enrich: `jev-1.13.0`; quote: `gpt-6-luna/none`; verify: `gpt-6-luna/none`; group: `gpt-6-luna/low`; memo: `gpt-6-luna/low`.
- Prompt versions: labels `prompts-v1`, group `group-v2`, memo `memo-v2`; schema `schema-v1`.

| | Cold (empty result cache) | Warm (saved result cache) |
|---|---|---|
| End-to-end wall clock | 69.06 s | 0.67 s |
| API cost | $0.009011 | $0.000000 |
| Requests / attempts / failed | 110 / 110 / 0 | 0 new calls (0 enrichment) |
| Result-cache hits | 0 | 100 of 100 |
| Cost per 1,000 inputs | $0.0901 | $0 |
| Cost per completed record | $0.000090 | $0 |
| Throughput | 1.45 records/s | 149.0 records/s |

Stage seconds (cold): ingest 0.07, enrich 14.82, verify 5.19, group 28.83, rank 0.01, memo 20.13. Stage seconds (warm): ingest 0.06, enrich 0.52, verify 0.02, group 0.03, rank 0.01, memo 0.02.

### Cold run by stage (actual usage x editable rates)

| Stage | Provider | Model (effort) | Prompt / schema | Batch limit | Workers | Requests | Attempts | Failed | Review IDs sent | Input tok | Cached tok | Output tok | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| enrich: Jev labels | TypeSafe | jev-1.13.0 | prompts-v1 (jev_questions_v1) / schema-v1 | 1 review per request; batches of 50 | Jev 1 | 100 | 100 | 0 | 100 | 127,787 | 0 | 21,275 | $0.005367 |
| enrich: gpt quotes | OpenAI | gpt-6-luna (effort none) | prompts-v1 (quote_v1) / schema-v1 | <= 50 reviews per request | batch 1 | 2 | 2 | 0 | 9 | 1,417 | 0 | 186 | $0.000235 |
| verify | OpenAI | gpt-6-luna (effort none) | prompts-v1 (verify_system) / schema-v1 | <= 50 reviews per request | 1 | 1 | 1 | 0 | 20 | 1,719 | 1,313 | 492 | $0.000300 |
| group: discover | OpenAI | gpt-6-luna (effort low) | group-v2 / schema-v1 | <= 120 examples per topic | 1 | 3 | 3 | 0 | 37 | 3,064 | 0 | 1,609 | $0.001111 |
| group: assign | OpenAI | gpt-6-luna (effort none) | group-v2 / schema-v1 | <= 50 reviews per request | 1 | 3 | 3 | 0 | 37 | 2,503 | 0 | 455 | $0.000478 |
| memo | OpenAI | gpt-6-luna (effort low) | memo-v2 / schema-v1 | 1 request (aggregates only) | 1 | 1 | 1 | 0 | 0 | 5,036 | 0 | 2,034 | $0.001521 |

Retries: 0 failed attempts in the pilot, so the base projection adds no retry allowance; the conservative case adds 10%. Verification: a declared seeded sample (3% of distinct texts, minimum 20; 20 in the pilot). Fallbacks: none configured (no stronger model); a quote failure falls back to an exact text prefix in code at zero API cost.

## Estimate refreshes (100 -> 500 -> 10,000)

| Checkpoint | Distinct texts | Enrich seconds | Texts/s | Jev cost/text | Workers |
|---|---|---|---|---|---|
| pilot 100 (cold, 1 worker) | 100 | 14.8 | 6.75 | $0.000054 | batch 1 / jev 1 |
| checkpoint_500 | 479 | 31.5 | 15.22 | $0.000054 | batch 2 / jev 8 |
| checkpoint_10000 part 1 (before cache-fill fix; process ended by a session restart) | 3,750 | 1243.2 | 3.02 | $0.000054 | batch 4 / jev 8 |
| checkpoint_10000 part 2 (after fix) | 4,741 | 136.2 | 34.81 | $0.000054 | batch 4 / jev 8 |

Projections use the latest refresh's enrichment throughput. Elapsed time is modeled from measured throughput, not from summed call durations (calls overlap when workers > 1).

## Full-run projections (budget $10.00)

| Scenario | Case | Distinct texts sent | Completed classifications | API cost | Enrich time | Budget |
|---|---|---|---|---|---|---|
| 100k scope, exact-text reuse (chosen) | base | 78,137 | 237,987 | $4.98 | 0.62 h | within |
| 100k scope, exact-text reuse (chosen) | conservative | 78,137 | 237,987 | $5.67 | 1.25 h | within |
| Full corpus, exact-text reuse | base | 484,189 | 660,609 | $30.68 | 3.86 h | **OVER BUDGET** |
| Full corpus, exact-text reuse | conservative | 484,189 | 660,609 | $34.98 | 7.73 h | **OVER BUDGET** |
| Full corpus, NO reuse (comparison) | base | 660,609 | 660,609 | $41.85 | 5.27 h | **OVER BUDGET** |
| Full corpus, NO reuse (comparison) | conservative | 660,609 | 660,609 | $47.71 | 10.54 h | **OVER BUDGET** |

All scenarios account for all 660,622 source rows and 13 empty-text quarantines. Stage detail (work units x unit cost):

- **100k scope, exact-text reuse (chosen) / base**: enrich: Jev labels 78,137 -> $4.19; enrich: gpt quotes 7,032 -> $0.1834; verify 2,345 -> $0.0351; group: assign 41,413 -> $0.5348; group: discover (fixed) 8 -> $0.0288; memo (fixed) 1 -> $0.001521. Assumptions: extra attempts 0%, long-text share 0.090, complaint share 0.530.
- **100k scope, exact-text reuse (chosen) / conservative**: enrich: Jev labels 78,137 -> $4.61; enrich: gpt quotes 8,790 -> $0.2522; verify 2,345 -> $0.0387; group: assign 51,766 -> $0.7353; group: discover (fixed) 8 -> $0.0288; memo (fixed) 2 -> $0.003041. Assumptions: extra attempts 10%, long-text share 0.112, complaint share 0.663.
- **Full corpus, exact-text reuse / base**: enrich: Jev labels 484,189 -> $25.99; enrich: gpt quotes 43,577 -> $1.14; verify 14,526 -> $0.2177; group: assign 256,620 -> $3.31; group: discover (fixed) 8 -> $0.0288; memo (fixed) 1 -> $0.001521. Assumptions: extra attempts 0%, long-text share 0.090, complaint share 0.530.
- **Full corpus, exact-text reuse / conservative**: enrich: Jev labels 484,189 -> $28.59; enrich: gpt quotes 54,471 -> $1.56; verify 14,526 -> $0.2395; group: assign 320,775 -> $4.56; group: discover (fixed) 8 -> $0.0288; memo (fixed) 2 -> $0.003041. Assumptions: extra attempts 10%, long-text share 0.112, complaint share 0.663.
- **Full corpus, NO reuse (comparison) / base**: enrich: Jev labels 660,609 -> $35.46; enrich: gpt quotes 59,455 -> $1.55; verify 19,819 -> $0.2970; group: assign 350,123 -> $4.52; group: discover (fixed) 8 -> $0.0288; memo (fixed) 1 -> $0.001521. Assumptions: extra attempts 0%, long-text share 0.090, complaint share 0.530.
- **Full corpus, NO reuse (comparison) / conservative**: enrich: Jev labels 660,609 -> $39.00; enrich: gpt quotes 74,319 -> $2.13; verify 19,819 -> $0.3267; group: assign 437,653 -> $6.22; group: discover (fixed) 8 -> $0.0288; memo (fixed) 2 -> $0.003041. Assumptions: extra attempts 10%, long-text share 0.112, complaint share 0.663.

## Controls

- Spending limit: $10.00 (`limits.spend_cap_usd` in config/run_config.json; the pipeline reserves an estimated worst case before every call and stops admitting work when spent + reserved + next > cap).
- Output-token cap per request: 6,000; max reviews per enrichment request: 50.
- Max workers: Jev 8, batch 4; shared rate limiter and one spend ledger.
- Max fallback fraction: 5%; fallback model: none (no stronger-model fallback is configured; a failed quote falls back to an exact text prefix in code at zero API cost).

## Not API spend

- Local compute: **unknown**. Pipeline code runs on a Windows laptop; electricity and hardware time are not metered, so they are reported as unknown rather than zero.
- Infrastructure: neon_postgres: free tier, $0 list price (checked 2026-10-14); vercel_hosting: Hobby tier, $0 list price (checked 2026-10-14).

## Rates used (editable: cost/rates.csv)

| Provider | Model | Item | Price per unit | Quoted as | Checked | Source |
|---|---|---|---|---|---|---|
| openai | gpt-6-luna | input_uncached | 0.000000100000 | $0.10 per 1M tokens (standard) | 2026-10-13 | https://developers.openai.com/api/docs/models/gpt-6-luna |
| openai | gpt-6-luna | input_cached | 0.000000010000 | $0.01 per 1M tokens (standard) | 2026-10-13 | https://developers.openai.com/api/docs/models/gpt-6-luna |
| openai | gpt-6-luna | cache_write | 0.000000125000 | $0.125 per 1M tokens (standard) | 2026-10-13 | https://developers.openai.com/api/docs/models/gpt-6-luna |
| openai | gpt-6-luna | output | 0.000000500000 | $0.50 per 1M tokens incl. reasoning (standard) | 2026-10-13 | https://developers.openai.com/api/docs/models/gpt-6-luna |
| typesafe | jev-1.13.0 | input | 0.000000042000 | $0.042 per 1M input tokens ($42 per 1B) | 2026-10-13 | https://docs.typesafe.ai/models |
| typesafe | jev-1.13.0 | output | 0.000000000000 | output tokens are free | 2026-10-13 | https://docs.typesafe.ai/models |

Every charged item per call is in `usage.csv` (request_id -> billing item -> billed units x price). Raw per-attempt usage and timing are in `pilot_calls.jsonl`.
