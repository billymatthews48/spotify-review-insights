# Golden-set error analysis

**Inputs:** [`golden_50_labeled.csv`](golden_50_labeled.csv) (50 human labels by the student) vs the final pipeline's saved predictions ([`golden_eval_cases.jsonl`](golden_eval_cases.jsonl), [`golden_eval_report.json`](golden_eval_report.json)). Regenerate with `python evals/golden_eval.py` (no enrichment calls; `--compare-luna` adds one paid call).

**Human labels were not changed after seeing predictions.** One revision happened *before* any comparison: the first pass used severity as "strength of feeling" (praise got 3-5). After re-reading the shared definition the student relabelled severity only (45 values) and nothing else; the superseded file is kept as [`golden_50_labeled_v1_superseded.csv`](golden_50_labeled_v1_superseded.csv). Golden labels were never model inputs, examples or thresholds.

## Headline numbers (n = 50; small diagnostic sample, not a population estimate)

| Field | Final pipeline (Jev + quotes) | Alternative: gpt-6-luna only (blind) |
|---|---|---|
| Topic agreement | 60% (30/50) | 66% (33/50) |
| Intent agreement | 82% | 82% |
| Severity exact / MAE | 80% / 0.32 | 80% / 0.32 |
| Sentiment within ±0.5 (pre-declared) / MAE | 86% / 0.21 | 86% / 0.27 |
| Evidence quote is an exact substring | 50 / 50 | n/a |
| Ambiguous cases flagged by labeller | 1 | 1 |

`needs_review` as a predictor of a material error (topic or intent wrong, or severity off by 2+): flagged 6 reviews, 4 of them materially wrong (precision 4/6). It caught only 4 of the 24 human-scored misses, so it is a weak recall signal. Many of those misses are rubric-application differences (category B below), not model uncertainty.

## Each disagreement (topic, intent or severity), categorized against the written rubric

Categories were drafted by the AI assistant (Claude) by applying the GRADING_CONTRACT.md rules to the text. They are a reading aid, not a re-score: the official agreement above uses the human labels as given.

- **A. Pipeline error:** the human label fits the rubric and the prediction does not.
- **B. Rule application:** the prediction follows a specific written rule that the human label does not (e.g. "ads → usability", "mixed praise + problem → complaint", "tie → first mentioned").
- **C. Language:** non-English text the labeller could not read.
- **D. Ambiguous:** both labels are defensible.

| # | Review (abridged) | Human | Pipeline | Cat. | Note |
|---|---|---|---|---|---|
| 1 | "…Banning conservative music… banning Christian songs…" | access/complaint/2 | catalog/complaint/2 (NR) | B | Removed content is catalog |
| 2 | "Ads were okay, but limited functionality.. too much" | usability/complaint/2 | usability/complaint/3 | D | Severity only: annoyance (2) vs restricted function (3) |
| 3 | "Hate this application 🤮" | usability/complaint/2 | other/complaint/2 | B | Generic criticism names no feature: other |
| 4 | "Spotify is awesome and very diverse :)" | catalog/praise/1 | other/praise/1 | D | "Diverse" may mean catalog breadth |
| 5 | "Duo Premium .... No ads at all!" | other/unclear/1 | usability/praise/1 | B | First specific praised feature: no ads, which is usability |
| 6 | "Very good but… it only plays a little bit then it stops… need to fix this" | playback/unclear/1 | playback/complaint/3 | B | Mixed praise + failure is complaint |
| 7 | "Update: …Support… got the app working again. Old post: …keeps crashing…" | support/praise/1 | playback/complaint/4 | A | Pipeline weighted the resolved old post |
| 8 | "Great..." | other/praise/1 | other/unclear/1 (NR) | A | Trailing dots made Jev uncertain; flagged |
| 9 | "Lhat ng song nasa spotify" (Tagalog: "all songs are on Spotify") | other/unclear/1 | catalog/unclear/1 | C | Likely catalog praise; neither label is fully right |
| 10 | "asem, lirik nya kdang gaada…" (Indonesian: lyrics are sometimes missing) | other/unclear/1 | catalog/complaint/3 | C | Pipeline matches the meaning |
| 11 | "We are boycotting Swedish app in our protest…" | other/cancellation/2 | other/unclear/1 | D | Collective boycott vs personal departure |
| 12 | "…Spotify gave me recommendations for an AWESOME Playlist" | usability/praise/1 | catalog/praise/1 | B | Recommendations are catalog |
| 13 | "Please ye ads ko thoda kumm Karo…" (Hindi: please reduce ads, one after every song) | other/unclear/1 | usability/request/3 | C | Ads are usability; request vs complaint is debatable |
| 14 | "my best music app but now… everything basic features is premium" | usability/praise/1 | billing/complaint/3 | B | Premium-only features are billing; mixed is complaint |
| 15 | "…trying to play a song but it doesn't work… can't even open the app" | usability/complaint/3 | playback/complaint/4 | B | Playback failure, core task blocked |
| 16 | "Beth, we all got to give me a free dollar…" | other/unclear/1 | billing/unclear/1 (NR) | A | No supported topic should be other; flagged |
| 17 | "Nice app, very less advertising" | other/praise/1 | usability/praise/1 | B | First specific praised feature: ads |
| 18 | "1-Lyrics not getting loaded, 2-can't go back… Pathetic update" | usability/complaint/3 | catalog/complaint/3 (NR) | B | Tie at severity 3: first mentioned problem (lyrics) is catalog |
| 19 | "The only thing Spotify lacks is… collections" | usability/praise/1 | usability/request/1 | B | Desired change with no failure is request |
| 20 | "…new update… can't even play the songs that I like and can't rewind" | usability/complaint/3 | playback/complaint/4 | D | Could be free-tier restriction (billing) or playback |
| 21 | "…it finds and plays whatever music you want and also adds songs you might like" | other/praise/1 | catalog/praise/1 | B | First specific praised feature: search/recommendations |
| 22 | "paying for subscribing but unable to play in offline mode" | usability/complaint/3 | downloads/complaint/4 | B | Offline listening is downloads |
| 23 | "Worst app ever too much ad" | other/complaint/3 | usability/complaint/3 | B | Ads are usability |
| 24 | "Too expensive and the free version is… unusable with constant ads" | other/complaint/3 | billing/complaint/3 | B | Tie: first mentioned (price) is billing |
| 25 | "I'm loving the experience with the app" | usability/praise/1 | other/praise/1 | B | General praise is other |

**Tally:** A pipeline error 3 · B rule application 15 · C language 3 · D ambiguous 4.

## Evidence quotes: does the quote support the label?

Code confirms all 50 quotes are exact substrings. Support was inspected by hand:

- **46 of 50** reviews are ≤ 200 characters, so the quote is the **whole review** by design. It contains all the evidence by construction but is not a minimal span.
- **4 long reviews** got a gpt-6-luna span:

| Review | Pipeline label | Quote | Supports the label? |
|---|---|---|---|
| 215463ae | playback / complaint / 4 | "I'm trying to play a song but it doesn't working." | **Yes** (the stronger severity-4 evidence, "can't even open the app", sits elsewhere in the text) |
| 292ce26a | catalog / complaint / 2 | "Banning conservative music that speaks truth." | **Yes** (removed content is catalog) |
| 3ddb3f4e | usability / cancellation / 3 | "we can't CHOOSE song after a song played" | **Partly:** supports the topic, but the cancellation evidence ("Deleting this App") is not in the span |
| 723f07de | playback / complaint / 4 | "it keeps crashing every time." | **Supports a wrong label:** the quote is faithful, but the review's update says the problem was resolved (model error #7) |

**Result:** 4/4 long-review quotes support the topic, 1 misses the intent evidence, and 1 faithfully supports a mislabel. A single span cannot always carry both topic and intent evidence; the contract requires one exact substring.

## Entities: inspection of unsupported additions

The human labeller left the optional `entities` field blank on all 50 rows, so there is no human-vs-model entity agreement score (the report's `cases_with_entities_not_in_human_list: 19` only means "the pipeline listed something and the human listed nothing"). Instead, each predicted entity was inspected against the text:

- **19 reviews, 29 entity mentions.** Entities come from a fixed term lexicon matched in code ([`ENTITY_TERMS`](../../pipeline/enrich.py)), so **every entity literally occurs in the review**; none can be invented.
- **Wrong-sense matches: 2 of 29.** `update` for a post that starts "Update:" as an edit marker (#7, 723f07de), and `update` for "I updated my phone" (#6, 947821dc), which is not an app update.
- **Misses (recall):** features outside the lexicon are not listed, e.g. "can't rewind songs" (dceb14e7) gets no `rewind` entity. Entities are descriptive metadata only; they feed no label, issue or ranking.

## What this means

- **The pipeline applies the written precedence rules more literally than a first-time human labeller.** Most topic disagreements (15 of 25 rows) are ads/recommendations/price rules or "generic → other". This is why topic agreement (60%) is lower than intent (82%) and severity (80%).
- **Real model errors cluster in edge cases:** a resolved problem reported as an "Update:" (7), very short ambiguous praise (8), and unintelligible text given a topic (16). Two of these three were flagged `needs_review`.
- **Non-English reviews:** the model labelled Indonesian and Hindi text by meaning, where the human could not read it. Language is not translated or filtered; `non_latin_script` is added to review reasons for non-Latin scripts.
- **Setup choice:** the Jev + quote pipeline and a gpt-6-luna-only labeller performed about the same on these 50 (topic 60% vs 66% is a 3-review difference). Jev was kept because the instructor recommended it, its per-option probabilities drive `needs_review`, and it costs $0.000054 per text with free output. Disclosure: the human labels arrived after the 10k checkpoint had been classified, so this comparison was made after the setup was chosen, not before. When Jev credit ran out, phase 2 labelled the remaining reviews with gpt-6-luna; this table is the evidence that the switch does not lower quality on these 50 (and the two-way verifier in [`../verify/README.md`](../verify/README.md) shows the same at scale). All 50 golden reviews are in phase 1, so their saved pipeline labels are Jev labels.
- **Limitations:** 50 reviews is a small sample (32 are "other"), there is a single labeller, and the categorization above is assistant-drafted.
