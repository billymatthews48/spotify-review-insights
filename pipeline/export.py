"""Exports in the GRADING_CONTRACT.md formats (records, calls, membership, ranking, claims, checkpoints).
No model calls. Reads only the saved state + result cache."""

import gzip
import json
import shutil
from pathlib import Path

from . import common

OUT_OF_SCOPE_REASON = "not_classified_outside_declared_100k_budget_scope"
BUDGET_REASON = "not_classified_api_credit_limit_reached"


def records(conn, out_of_scope_as="quarantined"):
    """One final record per source ID in the contract shape. Out-of-scope rows that were never sent to a
    model are reported as quarantined with an explicit reason (never as completed classifications)."""
    q = conn.execute("""
        SELECT r.review_id, s.source_sha256, r.status, r.reason, r.in_scope, r.label_config, r.cache_source_id,
               r.cache_origin_run, l.topic, l.intent, l.sentiment, l.severity, l.entities, l.evidence_quote, l.needs_review,
               l.review_reasons, l.quote_source
        FROM records r JOIN source_rows s USING(review_id)
        LEFT JOIN cache.labels l ON l.text_sha256 = s.text_sha256 AND l.label_config = r.label_config
        ORDER BY s.row_num""")
    for (rid, src, status, reason, in_scope, lc, cache_src, cache_run, topic, intent, sentiment, severity,
         entities, quote, needs_review, reasons, quote_source) in q:
        if status == "completed":
            rec = {"review_id": rid, "source_sha256": src, "status": "completed", "topic": topic, "intent": intent,
                   "sentiment": sentiment, "severity": severity, "entities": json.loads(entities),
                   "evidence_quote": quote, "needs_review": bool(needs_review), "label_config": lc}
            if cache_src:
                rec["cache_source_id"] = cache_src
            if cache_run:
                rec["result_cache_run"] = cache_run
            rec["review_reasons"] = json.loads(reasons)
            rec["quote_source"] = quote_source
            yield rec
        elif status == "quarantined":
            yield {"review_id": rid, "source_sha256": src, "status": "quarantined", "reason": reason}
        else:  # pending: never sent to a model (or a transient failure left it unlabelled)
            if out_of_scope_as == "quarantined":
                why = OUT_OF_SCOPE_REASON if not in_scope else (reason or BUDGET_REASON)
                yield {"review_id": rid, "source_sha256": src, "status": "quarantined", "reason": why}
            else:
                yield {"review_id": rid, "source_sha256": src, "status": "pending",
                       "reason": reason or "pending_not_yet_classified"}


def calls(conn, run_ids=None):
    """Every attempted call in the contract shape plus our extra billing/timing fields."""
    where = ""
    params = []
    if run_ids:
        where = f"WHERE run_id IN ({','.join('?' * len(run_ids))})"
        params = list(run_ids)
    for row in conn.execute(f"SELECT * FROM calls {where} ORDER BY started_at, request_id", params):
        r = dict(row)
        yield {"request_id": r["request_id"], "role": r["role"], "review_ids": json.loads(r["review_ids"]),
               "model": r["model"], "phase": r["phase"], "outcome": r["outcome"], "label_config": r["label_config"],
               "input_tokens": r["input_tokens"] or 0, "output_tokens": r["output_tokens"] or 0,
               "cached_input_tokens": r["cached_input_tokens"] or 0, "reasoning_tokens": r["reasoning_tokens"] or 0,
               "usage_status": r["usage_status"], "cost_usd": r["cost_usd"], "step": r["step"], "provider": r["provider"],
               "effort": r["effort"], "attempt": r["attempt"], "error": r["error"], "run_id": r["run_id"],
               "started_at": r["started_at"], "seconds": r["seconds"], "provider_request_id": r["provider_request_id"]}


def enriched_and_quarantine(conn, out_dir):
    """Separate result files named in the brief: enriched.jsonl.gz (every completed record with its validated
    labels, provenance and review reasons) and quarantine.jsonl.gz (every record not successfully classified, with
    reason and attempt count). records.jsonl in grading/ combines both."""
    out_dir = Path(out_dir)
    attempts = dict(conn.execute("SELECT review_id, attempts FROM records"))
    in_scope = dict(conn.execute("SELECT review_id, in_scope FROM records"))
    enriched, quarantine = [], []
    for r in records(conn):
        if r["status"] == "completed":
            enriched.append(r)
        else:
            # source_sha256 stays in grading/records.jsonl; the log keeps what explains the status.
            quarantine.append({"review_id": r["review_id"], "status": r["status"], "reason": r["reason"],
                               "attempts": attempts[r["review_id"]], "in_scope": bool(in_scope[r["review_id"]])})
    write_jsonl(out_dir / "enriched.jsonl", enriched, gz=True)
    write_jsonl(out_dir / "quarantine.jsonl", quarantine, gz=True)
    return len(enriched), len(quarantine)


def write_jsonl(path, rows, gz=False):
    path = Path(path)
    if gz:
        path = path.with_name(path.name + ".gz")
        tmp = path.with_name(path.name + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
        tmp.replace(path)
    else:
        common.write_jsonl(path, rows)
    return path


def copy(src, dst):
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
