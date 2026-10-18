# Decision memo: Prioritize playback reliability

## Recommendation
Prioritize playback reliability next quarter, including offline downloads. The severity-weighted issue ranking highlights crashes or loading failures (PLB-03, [C1]), false connection failures (PLB-04, [C2]), and download complaints (DWN-99, [C3]); wrong-song or control failures also rank strongly (PLB-05, [C4]). Treat this as a directional signal, not a population-wide estimate.

## Why
These issues describe failures at the point of listening: the app will not open or play, reports a connection problem despite working internet, or fails to make downloaded content available. For example, one reviewer described a black screen and repeated reinstalling (065c418e-7f18-42a3-b241-fe693b7a2b0c); another said downloaded content was gone (5be3399d-dcd2-405b-a931-29b02ffc966e). Together, they support focusing on reliability and offline listening rather than a broader, less specific complaint category.

## Alternatives considered
**Usability:** Excessive ad interruptions are the highest-ranked specific issue in the supplied list, with priority score 77 (USB-01, [C5]). This merits attention, but playback failures more directly prevent the core listening task.

**Billing/support:** Free-tier song choice and ordering has priority score 36 (BIL-01, [C6]), and reviews describe frustration with shuffle and controls behind a paywall (88439ec2-7c49-4c57-bedb-c5e098692aff; 66c56c76-ca94-46ef-b0a1-931654ead16d). It ranks below playback reliability for this quarter because it concerns access to controls or plan boundaries rather than service reliability itself.

## Evidence
The supplied evidence includes reports of crashes (065c418e-7f18-42a3-b241-fe693b7a2b0c), network failures (bcdf315e-c82d-41f0-9fcd-ba5933dfe77e), and offline mode not working (b03d6dc9-449a-4647-b112-559186656759). The aggregate ranking places PLB-03, PLB-04, and DWN-99 among the leading playback-related issues.

## Limitations
The classification covers only the supplied records and taxonomy, not all user problems. The reviews are self-selected and historical, from 2022-05-19 to 2023-11-15. The facts report no quarantined or pending-unclassified records, but that does not rule out omissions or classification error. Cancellation language is expressed intent, not observed churn; these data establish no causal effects.
