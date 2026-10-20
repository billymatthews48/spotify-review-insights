# Interruption and resume evidence

**Recording (short, 4:00):** [`interruption_resume_short.mp4`](interruption_resume_short.mp4): start, Ctrl+C at about 1:00, saved summary at about 1:15, checkpoint at about 2:00, and from about 3:00 the resume printing the saved count and completing new batches.

Full 13.9-minute take (the same session, with the resumed run continuing): [`interruption_resume_recording.mp4`](interruption_resume_recording.mp4). Both are sidebar-cropped and compressed.

What it shows, in order (Oct 16, 2026):

1. `python -m pipeline enrich --state state\full.sqlite --phase initial` starts and prints `[initial] 129,564 IDs already completed and saved …; 69,646 pending distinct texts queued`.
2. After 12 batches it is interrupted with **Ctrl+C**. The pipeline prints `Interrupted: finishing in-flight batches and saving progress…`, commits the in-flight batches (15 in total) and exits with `"stop_reason": "interrupted"`, completed records **131,915**.
3. `python -m pipeline snapshot … --out out\full\checkpoint_before.json` saves `completed_ids saved: 131915`.
4. `python -m pipeline enrich … --phase resume` prints `[resume] 131,915 IDs already completed and saved (never re-sent …); 68,896 pending distinct texts queued` and continues with new batches. It later finished all 68,896 texts in 1,723 s.

| | Completed records |
|---|---|
| Before interruption ([`checkpoint_before.json`](../../grading/checkpoint_before.json)) | 131,915 |
| After resume ([`checkpoint_after.json`](../../grading/checkpoint_after.json)) | 237,987 (before ⊂ after; 106,072 new) |

Calls in [`grading/calls.jsonl.gz`](../../grading/calls.jsonl.gz) carry `phase: initial` or `phase: resume`. No `resume` call includes a before-checkpoint ID (course checker: no `reprocessed_checkpoint` issue).

**Known gap from this interruption:** the interrupt handler dropped one finished batch before committing it. The in-process ledger showed $0.528059 vs $0.525200 logged, so **$0.002859** was paid but not logged. Those texts stayed pending and were re-sent on resume. The cause (removing the batch from the queue before waiting on it) is fixed in [`pipeline/enrich.py`](../../pipeline/enrich.py).

An earlier, unplanned interruption (an agent-session restart on Oct 14 during phase A) is described in the README run log. SQLite rolled back the partial batch, and every saved label has call evidence.
