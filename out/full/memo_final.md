# Next-quarter product effort: make ads less disruptive, not fewer

Recommend prioritizing usability, starting with excessive ad interruptions (USB-01): complaint_count 28764 [C1], mean_severity 2.894938 [C2], priority_score 83270 [C3]. Ads pay for the free tier, so the goal is not fewer ads but less disruptive ones: control how often, when and how loudly they play, and keep promised ad-free periods free of ads.

## Why

Usability has the largest complaint total of the named product areas: complaint_count 59647, severity_sum 169075, mean_severity 2.834594, cancellation_count 6148. USB-01 is its leading issue and the highest-ranked specific issue overall.

The #1 baseline issue is OTH-99, general dissatisfaction that names no feature: complaint_count 61635 [C4], priority_score 116400 [C5]. Because it is a catch-all, I treat it as a signal to investigate, not as a feature workstream.

The ad complaints are mostly about how ads are delivered, not that ads exist. The issue is defined as ads that are too frequent, mistimed or loud. Reviewers say "wayyy to many ads" from someone who would otherwise give the app top marks (e57b7127-13d5-41bc-ad83-1595256f5478), and "Just got 4 minutes of ads straight" (cd8bf064-c32e-400e-906e-a4d900819bbd).

## Revenue trade-off

Ads and Premium-only features are how the free tier earns money and encourages upgrades. Under the declared business lens, 37075 of usability's 59647 complaints and 23245 of billing/support's 46820 are about these monetization levers, 61170 in total. Removing ads or paywalls would cost revenue, so this recommendation keeps them and changes how they are experienced:

- cap how many ads play in a row and how long one ad break lasts;
- play ads between songs, never in the middle of one;
- match ad loudness to the music;
- honor promised ad-free periods.

These changes reduce interruption while keeping ads in the product. This memo uses no revenue data, so each change should be tested against ad revenue and Premium upgrades before a full rollout.

## Alternatives considered

**Playback (incl. downloads)** is the strongest area with no revenue trade-off: complaint_count 42261, severity_sum 146374, mean_severity 3.463572, cancellation_count 3665, and none of its complaints are monetization levers. Its leading issue, PLB-01 (unexpected playback stops), has complaint_count 7860 [C6] and priority_score 26948 [C7]. These are defects, so fixing them costs no revenue, and the area's mean severity is higher than usability's. It comes second because USB-01's priority score is far above any playback issue and usability has more complaints. If leadership wants no revenue risk this quarter, playback reliability is the choice.

**Billing/support** totals are complaint_count 46820, severity_sum 136100, mean_severity 2.906877, cancellation_count 8247. BIL-02 (Premium-locked playback controls) has complaint_count 9937 [C8] and priority_score 29827 [C9]. 23245 of its complaints are about Premium-only limits, which are the reason to upgrade; loosening them trades directly against subscription revenue, so it is not first.

**Access** has the highest mean severity of any area (3.964362) but the smallest volume (complaint_count 7997), so it suits a targeted fix rather than a quarter's focus.

## Evidence

The excerpts illustrate the themes; they are examples, not estimates. Ad complaints focus on frequency and length (e57b7127-13d5-41bc-ad83-1595256f5478, cd8bf064-c32e-400e-906e-a4d900819bbd). A paying subscriber has to reinstall the app because the music player stops working (811a3af2-8624-4e83-93fc-d17cfd216bb6). A free user cannot loop, play the previous track or play songs in order without Premium (b2d1098c-85a0-4acc-b481-9bdfbe844940).

## Limitations

- 577230 records are classified; 83227 are pending unclassified and 165 are quarantined.
- Reviews are self-selected and historical (2022-05-17 to 2023-11-15). Cancellation language is expressed intent, not observed churn.
- The monetization-lever tags are a product judgment, declared after the first draft and applied to whole issues. BIL-99, a catch-all that mixes price complaints with billing errors, is left untagged. No revenue data was used.
- OTH-99 is the #1 baseline issue but names no feature, so it should guide investigation rather than be treated as a feature.
- This memo is the student's revision of the memo agent's draft (memo.md). Code re-checked every number, claim and review ID in it.
