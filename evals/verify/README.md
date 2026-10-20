# Independent verification: procedure and disagreement analysis

There are two labelling phases, and each is verified by the **other** model family: phase 1 (Jev labels) is checked by gpt-6-luna, and phase 2 (gpt-6-luna labels) is checked by Jev. Phase 1 is described first; [phase 2](#phase-2-jev-verifies-gpt-6-luna-labels) is at the end.

## Procedure

- **Sample:** a declared, seeded 3% of origin records (`SHA-256("verify-v1:" + review_id)` order; n = 2,345 of 78,137 distinct texts). The sample is fixed before verification, so the verifier cannot choose its cases.
- **Verifier:** `gpt-6-luna` (reasoning `none`). It is a different model family from the enricher (Jev) and receives **only the review text and the shared rubric** ([prompt](../../prompts/verify_system_prompts-v1.txt)), never Jev's answer. Requests carry <= 50 reviews and use structured output with enum-constrained labels.
- **Comparison in code** ([`pipeline/verify.py`](../../pipeline/verify.py)): field by field, with the results in [`verify_summary.json`](verify_summary.json), every pair in [`verifier_predictions.jsonl`](verifier_predictions.jsonl), and every disagreement with its text in [`disagreements.jsonl`](disagreements.jsonl).
- **Planted-error test** ([`planted_error_cases.jsonl`](planted_error_cases.jsonl)): a separate synthetic copy of 20 verified records with a deliberately wrong topic (rotated 3 places) and severity (1 <-> 5). It is detected when the blind verifier disagrees with the planted label. **20/20 detected.** These rows are marked `synthetic: true` and never enter business data.
- **Failures:** one batch of 50 failed validation twice in the first pass and succeeded when the stage was rerun; final verifier failures: 0. GPT failures in the call log: 5 attempts (invalid JSON, `max_output_tokens`), all retried.

## Results (n = 2,345)

| Field | Agreement | Disagreements |
|---|---|---|
| Topic | 87.1% | 303 |
| Intent | 93.3% | 158 |
| Severity | 87.4% (MAE 0.14) | 295: **261 differ by 1**, 26 by 2, 8 by 3 |
| All three | 73.0% | 632 records with at least one difference |

`needs_review` is a useful but imperfect signal: topic disagreement is **25.1%** among flagged records (98/390) vs **10.5%** among unflagged (205/1,955), about 2.4x.

## Where they disagree

- **Topic: specific vs generic.** The most common pairs are Jev `other` vs verifier `usability` (30), `catalog` (24), `billing` (21) and `playback` (21). Jev more often treats short, slangy reviews as generic (e.g. "It's adify not spotify", which the verifier reads as ads, i.e. usability).
- **Topic: adjacent areas.** `usability` <-> `catalog` (22, e.g. playlists and recommendations) and `playback` <-> `billing` (18, premium-restricted playback controls, which the rubric files under billing).
- **Intent:** `unclear` <-> `praise` for emoji-only or one-word reviews (25), `complaint` <-> `unclear` (23, often boycott/political text), `complaint` <-> `cancellation` (18 + 17), `request` <-> `complaint` (16).
- **Severity:** almost entirely adjacent levels (2 vs 3, 3 vs 4).

## Inspection of 16 random topic/intent disagreements (seed 7)

| Review | Jev | Verifier | Text (abridged) | Reading against the rubric |
|---|---|---|---|---|
| 632b4cf9 | other/complaint/2 | billing/complaint/2 | "This premium membership update was 🐂💩" | ambiguous (a paid-plan mention alone is not billing) |
| 2d1bac36 | playback/complaint/3 | catalog/request/3 | "…took away the ability to hear part of the song :(" | ambiguous topic; complaint fits |
| 73acafb8 | catalog/praise/1 | other/praise/1 | "…all music in one, Amen" | **Jev** (first praised feature: catalog breadth) |
| ccfea689 | usability/complaint/2 | usability/request/1 | "…why is there no landscape view…" | **verifier** (wish without failure is request) |
| 0bacf7ba | billing/complaint/3 | usability/complaint/3 | "Way too many recommendations for premium…" | ambiguous |
| 17034860 | usability/complaint/3 | playback/complaint/3 | "…volume is low while listening via earbuds…" | **verifier** (audio quality is playback) |
| fa1b0051 | other/unclear/1 | other/praise/1 | "💪" | ambiguous |
| a50ed84f | other/complaint/2 | other/unclear/1 | "This country make fun off quran…" | **verifier** (political/boycott text is unclear) |
| 1c600d54 | downloads/praise/1 | other/praise/1 | "At least I dont have to download songs anymore…" | **Jev** (specific feature) |
| 6e636e00 | other/praise/1 | usability/praise/1 | "I love this app it makes everything so much easier." | **Jev** (general praise is other) |
| b5fac5f8 | other/praise/1 | other/request/1 | "a better music application" | **Jev** |
| 0ee68d6f | billing/complaint/3 | catalog/complaint/3 | "Spotify has made its lyrics premium and has advertisements every 2 seconds" | ambiguous (paywall vs lyrics availability) |
| 9cf9ac16 | other/complaint/4 | playback/complaint/4 | "App does not working now" | **verifier** (app not working is playback) |
| 41883bf4 | other/complaint/2 | usability/complaint/3 | "It's adify not spotify" | **verifier** (ads) |
| 0a98a359 | usability/praise/1 | catalog/praise/1 | "Easy to use… Best playlist…" | **Jev** (first praised feature: ease of use) |
| 1a2b2c39 | other/complaint/1 | other/unclear/1 | "Ye swedn ki app he…" (anti-Sweden slogan) | **verifier** (boycott slogan is unclear) |

**Tally:** Jev 5 · verifier 6 · ambiguous 5. Neither model is systematically better; the disagreements sit on genuine rubric boundaries.

## What this means for the result

- Some boycott/political slogans that the rubric calls `unclear` were labelled `complaint` by Jev (a50ed84f, 1a2b2c39). Those flow into **`OTH-99` (general dissatisfaction)**, inflating the catch-all, especially in the July 2023 spike. They do **not** inflate the actionable issues, so the recommendation (usability / `USB-01`) is unaffected.
- Topic is the least stable field (87% agreement here, 60% on the golden set), mostly at the `other`/specific boundary. Area totals and issue counts should be read as approximate shares, not exact counts. This is stated in the memo's and README's limitations.

## Phase 2: Jev verifies gpt-6-luna labels

- **Sample:** a declared, seeded 3% of the phase-2 origin records (seed `verify-v1_phase2`; n = 9,689 of 322,950 gpt-labelled distinct texts).
- **Verifier:** Jev `jev-1.13.0`, asked exactly the same fixed-option questions as the phase-1 enricher ([questions](../../prompts/jev_questions_v1.json)). It sees only the review text. Code compares the answers ([`pipeline/verify.py`](../../pipeline/verify.py) `run_jev`).
- **Cost and failures:** 9,689 Jev calls, $0.52. Three attempts failed with Jev HTTP 529 (overloaded) and were retried on the next analysis run ($0.00016); final verifier failures: 0.
- **Files:** [`verify_summary_phase2.json`](verify_summary_phase2.json), [`verifier_predictions_phase2.jsonl`](verifier_predictions_phase2.jsonl), [`disagreements_phase2.jsonl`](disagreements_phase2.jsonl), [`planted_error_cases_phase2.jsonl`](planted_error_cases_phase2.jsonl) (synthetic, 20/20 detected).

| Field | Agreement (n = 9,689) | Disagreements |
|---|---|---|
| Topic | 86.3% | 1,324 |
| Intent | 92.9% | 687 |
| Severity | 87.4% (MAE 0.14) | 1,218: **1,063 differ by 1**, 139 by 2, 16 by 3 |
| All three | 71.6% | 2,750 records with at least one difference |

**Patterns** (gpt-6-luna label -> Jev re-label). They are the same rubric boundaries as in phase 1, seen from the other side:

- **Topic:** `billing` -> `usability` (131; premium-restricted controls, which the rubric files under billing), `usability`/`playback`/`catalog` -> `other` (129 / 119 / 109; gpt tends to name a specific area where Jev says generic), `catalog` -> `usability` (115; playlists and recommendations).
- **Intent:** `praise` -> `unclear` (103; very short or emoji texts), `unclear` -> `complaint` (95), `cancellation` -> `complaint` (92), `request` -> `complaint` (65).

**What this means:** agreement in both directions is almost identical (topic 87.1% / 86.3%, intent 93.3% / 92.9%, severity 87.4% / 87.4%). Neither labeller is clearly more reliable, and mixing them does not change the picture at the area level. The phase-1-only and full-data analyses reach the same recommendation.
