"""run_log.jsonl + run_summary.json for a state DB (no model calls): stage timing, statuses, attempts,
failures, usage, actual charges (usage x dated rates), spend cap and resume evidence."""

import json
import time
from collections import defaultdict
from pathlib import Path

from . import common, runtime
from .enrich import open_state

# Known accounting gaps, measured from the saved ledger vs the call log (see README "Run log").
UNLOGGED = [
    {"when": "2026-10-14 ~19:08 local", "run_id": "enrich-20261014T184618-96a23c",
     "what": "Phase A process was terminated by an agent-session restart mid-batch. Up to 4 in-flight batches "
             "(<= 200 Jev calls) may have been paid but were never logged; their texts stayed pending and were re-sent.",
     "estimated_max_usd": 0.0108},
    {"when": "2026-10-16 12:44 local", "run_id": "enrich-20261016T124241-cbe311",
     "what": "On the deliberate Ctrl+C, the interrupt handler dropped one finished batch before committing it (bug: popped "
             "before waiting; fixed). In-process ledger said $0.528059 vs $0.525200 logged.",
     "measured_usd": 0.002859},
    {"when": "2026-10-20 13:40 local", "run_id": "enrich-20261020T130208-a47b1a",
     "what": "Phase-2 run crashed on a response that was a bare JSON list (fixed: tolerant item parsing + per-batch crash "
             "guard). Up to 48 in-flight gpt-6-luna batches may have been paid but were never logged; their texts stayed "
             "pending and were re-sent.",
     "estimated_max_usd": 0.05},
]


def _memo_inputs(out_dir):
    path = Path(out_dir) / "memo_output.json"
    if not path.exists():
        return None
    m = common.read_json(path)
    return {"artifact": "memo_input.json (ranked aggregates, area totals, facts, evidence pack)",
            "input_sha256": m.get("input_sha256"), "memo_config": m.get("memo_config"),
            "note": "SHA-256 of the exact system prompt + input sent; the final memo call's review_ids list is empty by design"}


def write(state, cache, out_dir):
    out_dir = Path(out_dir)
    cfg, rates = runtime.load_config(), runtime.load_rates()
    conn = open_state(state, cache)
    log = [{"seq": r[0], "run_id": r[1], "at": r[2], "stage": r[3], "event": r[4], "detail": json.loads(r[5])}
           for r in conn.execute("SELECT seq, run_id, at, stage, event, detail FROM run_log ORDER BY seq")]
    common.write_jsonl(out_dir / "run_log.jsonl", log)
    runs = defaultdict(dict)
    for e in log:
        runs[e["run_id"]][e["event"]] = e
    calls = defaultdict(lambda: {"attempts": 0, "succeeded": 0, "failed": 0, "review_ids_sent": 0, "input_tokens": 0,
                                 "cached_input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0,
                                 "usage_unknown_attempts": 0})
    for role, phase, step, model, outcome, ids, inp, cached, out, reas, cost, status in conn.execute(
            "SELECT role, phase, step, model, outcome, review_ids, input_tokens, cached_input_tokens, output_tokens, "
            "reasoning_tokens, cost_usd, usage_status FROM calls"):
        c = calls[f"{role}/{step}/{model}/{phase}"]
        c["attempts"] += 1
        c[outcome] += 1
        c["review_ids_sent"] += len(json.loads(ids))
        c["input_tokens"] += inp or 0
        c["cached_input_tokens"] += cached or 0
        c["output_tokens"] += out or 0
        c["reasoning_tokens"] += reas or 0
        c["cost_usd"] += cost
        c["usage_unknown_attempts"] += status == "unknown_possible_charge"
    # Wall-clock span of each role within each run, from exact call timestamps (first call start -> last call end).
    # Used for the verify/group/memo stages of runs that predate per-stage timing events in run_log.
    spans = [{"run_id": rid, "role": role, "calls": n, "first_call_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(lo)),
              "wall_clock_seconds": round(hi - lo, 1)}
             for rid, role, n, lo, hi in conn.execute(
                 "SELECT run_id, role, COUNT(*), MIN(started_at), MAX(started_at + seconds) FROM calls "
                 "GROUP BY run_id, role ORDER BY MIN(started_at)")]
    status = {f"{s}/{'in_scope' if i else 'out_of_scope'}": n for s, i, n in
              conn.execute("SELECT status, in_scope, COUNT(*) FROM records GROUP BY 1, 2")}
    total = sum(c["cost_usd"] for c in calls.values())
    by_provider = defaultdict(float)
    for k, c in calls.items():
        by_provider["typesafe (Jev)" if "jev" in k else "openai (gpt-6-luna)"] += c["cost_usd"]
    summary = {
        "input": dict(conn.execute("SELECT key, value FROM meta").fetchall()),
        "label_config": runtime.label_config(cfg),
        "record_status": status,
        "completed_total": sum(v for k, v in status.items() if k.startswith("completed")),
        "exact_text_reuse_records": conn.execute(
            "SELECT COUNT(*) FROM records WHERE status='completed' AND cache_source_id IS NOT NULL").fetchone()[0],
        "distinct_texts_classified": conn.execute("SELECT COUNT(*) FROM cache.labels").fetchone()[0],
        "calls_by_role_step_model_phase": {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in sorted(calls.items())},
        "actual_api_charges_usd": {"total": round(total, 6), **{k: round(v, 6) for k, v in by_provider.items()}},
        "charges_basis": "provider-reported usage x dated rates in config/rates.csv (not a provider invoice)",
        "known_unlogged_or_estimated": UNLOGGED,
        "spend_cap_usd": cfg["limits"]["spend_cap_usd"],
        "stage_wall_clock_from_calls": spans,
        "aggregate_artifacts_consumed": {  # group/memo calls with empty review_ids read these saved files
            "memo": _memo_inputs(out_dir),
            "group_assign": "texts of completed complaint/cancellation records (review_ids listed per call)",
        },
        "timeouts_with_unknown_charge": sum(c["usage_unknown_attempts"] for c in calls.values()),
        "openai_prompt_cache": {"cached_input_tokens": sum(c["cached_input_tokens"] for k, c in calls.items() if "luna" in k),
                                "saving_vs_uncached_usd": round(sum(c["cached_input_tokens"] for k, c in calls.items() if "luna" in k)
                                                                * (rates[("gpt-6-luna", "input_uncached")]
                                                                   - rates[("gpt-6-luna", "input_cached")]), 6)},
        "maintenance_events": [e for e in log if e["event"] not in ("start", "end")],
        "runs": [{"run_id": rid, "stage": (ev.get("start") or ev.get("end"))["stage"],
                  "start": ev.get("start", {}).get("detail"), "end": ev.get("end", {}).get("detail"),
                  "seconds": (ev["end"]["at"] - ev["start"]["at"]) if "start" in ev and "end" in ev else None}
                 for rid, ev in runs.items() if "start" in ev or "end" in ev],
    }
    common.write_json(out_dir / "run_summary.json", summary)
    from .export import enriched_and_quarantine
    summary["enriched_records"], summary["quarantine_records"] = enriched_and_quarantine(conn, out_dir)
    conn.close()
    return summary
