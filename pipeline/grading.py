"""Write the standardized grading/ folder (GRADING_CONTRACT.md). No model calls.

grading/run.json, ingestion.json, records.jsonl.gz, membership.csv, ranking.csv, claims.csv, calls.jsonl.gz,
checkpoint_before.json, checkpoint_after.json
"""

import json
from pathlib import Path

from . import common, export
from .enrich import open_state


def write(state, cache, analysis_dir, checkpoints_dir, out_dir):
    out_dir, analysis_dir, checkpoints_dir = Path(out_dir), Path(analysis_dir), Path(checkpoints_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = open_state(state, cache)
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    profile = common.read_json(common.OUT_DIR / "ingestion.json")
    total = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    common.write_json(out_dir / "run.json", {
        "version": "a5-audit-v1", "analysis_count": total, "analysis_sha256": meta["input_sha256"],
        "classification_input_fields": ["review_text"], "allow_multi_issue": False,
        "declared_scope": {"classified": f"lowest {meta['scope_size']} course-sample-rank nonempty IDs, plus exact-text "
                                         "reuse for any other ID with identical text",
                           "out_of_scope_reason": export.OUT_OF_SCOPE_REASON,
                           "note": "Out-of-scope rows are accounted for as quarantined with an explicit reason; they are "
                                   "NOT successful classifications and are excluded from every business aggregate."}})
    export.copy(common.OUT_DIR / "ingestion.json", out_dir / "ingestion.json")
    for old in ("records.jsonl", "calls.jsonl"):
        (out_dir / old).unlink(missing_ok=True)  # never leave both plain and .gz copies
    export.write_jsonl(out_dir / "records.jsonl", export.records(conn), gz=True)
    export.write_jsonl(out_dir / "calls.jsonl", export.calls(conn), gz=True)
    for name in ("membership.csv", "ranking.csv", "claims.csv"):
        export.copy(analysis_dir / name, out_dir / name)
    for name in ("checkpoint_before.json", "checkpoint_after.json"):
        snap = common.read_json(checkpoints_dir / name)
        common.write_json(out_dir / name, {"completed_ids": snap["completed_ids"]})
    counts = dict(conn.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())
    conn.close()
    return {"records": total, "status": counts, "profile_rows": profile["counts"]["records"]}
