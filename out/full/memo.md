# Next-quarter product effort: usability

Prioritize usability, beginning with excessive ad interruptions. Usability leads the compared actionable areas in complaint count (13516) and severity sum (37865); its highest-ranked specific issue, USB-01, has priority score 21043 [C2]. Treat the #1 baseline issue, OTH-99, as broad dissatisfaction rather than a feature-level workstream: it has priority score 65484 [C1] but explicitly names no specific product problem.

## Why

The area totals support usability: complaint_count 13516, severity_sum 37865, mean_severity 2.801495. Evidence includes reports of four minutes of ads straight (review cd8bf064-c32e-400e-906e-a4d900819bbd) and ads after each song (review 93fd1ace-380d-4530-9f2b-45f37ecd6331). These reviews illustrate the issue; they do not establish its prevalence beyond the saved aggregates.

## Alternatives considered

- **Playback:** complaint_count 8199, severity_sum 27479, mean_severity 3.351506. PLB-05, wrong song or queue behavior, has priority score 6077 [C3]; a review describes an older queued song playing unexpectedly (review aeccadff-168c-476e-95fb-20c5a905aefd). Playback ranks below usability on area totals.
- **Billing/support:** complaint_count 7859, severity_sum 22279, mean_severity 2.834839. BIL-99, other billing complaints, has priority score 9312 [C4]. It is a broad catch-all, and billing/support's area totals are below usability's.

OTH-99 is the baseline catch-all for complaints naming no specific feature; I do not silently discard it, but distinguish it from issues that suggest a concrete intervention. BIL-99 is also a catch-all, but for billing complaints that do not fit a specific billing issue.

## Evidence

Other OTH-99 examples are “I hate this app” (review 30ac8728-8a7a-476e-baca-55a8eae7d588) and “Really bad experience” (review bebc380e-3f89-42af-822c-7fe8ce93a760). Their vagueness reinforces why OTH-99 is a baseline signal rather than a specific workstream.

## Limitations

The classification covers 100050 in-scope records; 422622 remain pending unclassified and 13 are quarantined. The window is 2022-05-17 to 2023-11-15. Reviews are self-selected and historical; cancellation language is expressed intent, not observed churn. The aggregates do not establish causes or represent all users.
