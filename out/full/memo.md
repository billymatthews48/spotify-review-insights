# Next-quarter product effort: reduce ad interruptions

Recommend prioritizing usability work to reduce excessive ad interruptions. Usability has the largest complaint total among the named product areas, while its leading ranked issue, USB-01, is a specific and actionable target: complaint_count 28764 [C1], mean_severity 2.894938 [C2], and priority_score 83270 [C3].

## Why

The #1 baseline issue is OTH-99, general dissatisfaction with no specific feature: complaint_count 61635 [C4] and priority_score 116400 [C5]. Because it is a catch-all, I treat it as a broad signal for investigation, not as a feature workstream. Usability totals are complaint_count 59647, severity_sum 169075, mean_severity 2.834594, and cancellation_count 6148. Reviews describe ad frequency as a problem, including “wayyy to many ads” (e57b7127-13d5-41bc-ad83-1595256f5478) and “4 minutes of ads straight” (cd8bf064-c32e-400e-906e-a4d900819bbd).

## Alternatives considered

Playback totals are complaint_count 42261, severity_sum 146374, mean_severity 3.463572, and cancellation_count 3665. PLB-01, unexpected playback stops, has complaint_count 7860 [C6] and priority_score 26948 [C7]; it merits attention, but its issue priority is below USB-01.

Billing/support totals are complaint_count 46820, severity_sum 136100, mean_severity 2.906877, and cancellation_count 8247. BIL-02, premium-locked playback controls, has complaint_count 9937 [C8] and priority_score 29827 [C9]. It ranks below USB-01 by priority score, so I would not put it first.

## Evidence

The review excerpts support the classified themes but are examples, not representative estimates. A playback review also reports repeated stopping (811a3af2-8624-4e83-93fc-d17cfd216bb6); a billing review describes controls unavailable without Premium (b2d1098c-85a0-4acc-b481-9bdfbe844940).

## Limitations

The classification covers only its defined scope. There are 83227 pending unclassified and 165 quarantined records. Reviews are self-selected and historical, from 2022-05-17 to 2023-11-15; cancellation language is expressed intent, not observed churn. OTH-99 is the #1 baseline but lacks a specific feature target, so it should inform investigation rather than be silently skipped or treated as a directly actionable feature.
