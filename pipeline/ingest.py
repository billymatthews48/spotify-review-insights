"""Stage 1 - Prepare. Reads every CSV row, preserves source values and IDs, profiles quality,
finds exact duplicate texts, quarantines empty texts and queues pending work. No model calls.

Output: <state db> source_rows + records tables, out/ingestion_report.json, out/ingestion.json
(the course helper's profile), out/data_manifest.json.
"""

import statistics
import time
from collections import Counter
from pathlib import Path

from . import common

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_rows(
    review_id TEXT PRIMARY KEY,
    row_num INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL,
    review_text TEXT NOT NULL,
    review_rating TEXT NOT NULL,
    review_likes TEXT NOT NULL,
    app_version TEXT NOT NULL,
    review_timestamp TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    is_empty INTEGER NOT NULL,
    sample_rank TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_text ON source_rows(text_sha256);
CREATE INDEX IF NOT EXISTS idx_source_rank ON source_rows(sample_rank);

-- One row per source ID; the only place record status lives.
CREATE TABLE IF NOT EXISTS records(
    review_id TEXT PRIMARY KEY REFERENCES source_rows(review_id),
    status TEXT NOT NULL CHECK(status IN ('pending', 'completed', 'quarantined')),
    in_scope INTEGER NOT NULL,
    reason TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_status ON records(status, in_scope);

CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _quantiles(values):
    if not values:
        return {}
    values = sorted(values)
    pick = lambda q: values[min(len(values) - 1, int(q * len(values)))]
    return {"min": values[0], "median": pick(0.5), "p90": pick(0.9), "p99": pick(0.99), "max": values[-1],
            "mean": round(statistics.fmean(values), 2)}


def ingest(input_csv, db_path, scope_size=None, samples_dir=None, report_dir=None):
    """Load input_csv into db_path. scope_size limits which nonempty IDs are queued for classification
    (lowest course sample rank first); None means every nonempty review."""
    input_csv = Path(input_csv)
    report_dir = Path(report_dir) if report_dir else common.OUT_DIR  # dev/pilot/test runs pass their own folder
    report_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    conn = common.connect(Path(db_path))
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM source_rows").fetchone()[0]:
        raise SystemExit(f"{db_path} already holds an ingested input; use a fresh --state path or delete it.")

    file_sha = common.file_sha(input_csv)
    manifest = common.read_json(common.MANIFEST_PATH)
    known = manifest["files"].get(input_csv.name)

    counts = Counter()
    ratings, months, text_counts = Counter(), Counter(), Counter()
    lengths, likes = [], []
    duplicate_ids, empty_ids, bad_ratings = [], [], []
    seen = set()
    rows = []
    for row_num, row in enumerate(common.csv_rows(input_csv), 1):
        rid = row["review_id"]
        counts["records"] += 1
        if rid in seen:
            # Only one final record per ID is allowed; later copies are reported, never silently merged.
            duplicate_ids.append({"row_num": row_num, "review_id": rid})
            continue
        seen.add(rid)
        text = row["review_text"]
        empty = not text.strip()
        if empty:
            empty_ids.append(rid)
        else:
            text_counts[text] += 1
            lengths.append(len(text))
        if not row["app_version"].strip():
            counts["missing_app_version"] += 1
        if row["review_rating"] not in {"1", "2", "3", "4", "5"}:
            bad_ratings.append(rid)
        ratings[row["review_rating"]] += 1
        months[row["review_timestamp"][:7]] += 1
        try:
            likes.append(int(row["review_likes"]))
        except ValueError:
            counts["nonnumeric_likes"] += 1
        rows.append((rid, row_num, common.row_sha(row), text, row["review_rating"], row["review_likes"],
                     row["app_version"], row["review_timestamp"], common.text_sha(text), int(empty),
                     common.sample_rank(rid)))

    with conn:
        conn.executemany("INSERT INTO source_rows VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        now = time.time()
        # Scope: every nonempty ID, or the lowest-ranked scope_size by the course's own seeded hash order.
        nonempty = conn.execute("SELECT review_id FROM source_rows WHERE is_empty = 0 ORDER BY sample_rank, review_id")
        nonempty_ids = [r[0] for r in nonempty]
        in_scope = set(nonempty_ids if scope_size is None else nonempty_ids[:scope_size])
        conn.executemany(
            "INSERT INTO records(review_id, status, in_scope, reason, attempts, updated_at) VALUES (?,?,?,?,0,?)",
            [(rid, "quarantined", 0, "empty_review_text", now) for rid in empty_ids]
            + [(rid, "pending", int(rid in in_scope), None, now) for rid in nonempty_ids])
        meta = {"input_path": str(input_csv), "input_sha256": file_sha, "input_bytes": str(input_csv.stat().st_size),
                "scope_size": "all" if scope_size is None else str(scope_size), "ingested_at": str(now)}
        conn.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", meta.items())

    scope_texts = conn.execute(
        "SELECT COUNT(DISTINCT s.text_sha256) FROM records r JOIN source_rows s USING(review_id) WHERE r.in_scope = 1"
    ).fetchone()[0]
    # IDs outside the scope whose exact text matches an in-scope text can reuse that result at no model cost.
    reusable = conn.execute(
        """SELECT COUNT(*) FROM records r JOIN source_rows s USING(review_id)
           WHERE r.in_scope = 0 AND s.is_empty = 0 AND s.text_sha256 IN (
             SELECT s2.text_sha256 FROM records r2 JOIN source_rows s2 USING(review_id) WHERE r2.in_scope = 1)"""
    ).fetchone()[0]

    helper_profile = common.checker.profile(input_csv)  # the course's deterministic profile, unmodified
    common.write_json(report_dir / "ingestion.json", helper_profile)

    distinct = len(text_counts)
    dup_rows = sum(c - 1 for c in text_counts.values() if c > 1)
    report = {
        "input": {"path": input_csv.name, "bytes": input_csv.stat().st_size, "sha256": file_sha,
                  "matches_course_manifest": bool(known and known["sha256"] == file_sha)},
        "rows": {"parsed": counts["records"], "unique_review_ids": len(seen), "duplicate_review_id_rows": len(duplicate_ids),
                 "empty_review_text": len(empty_ids), "nonempty_to_classify": len(seen) - len(empty_ids),
                 "missing_app_version": counts["missing_app_version"], "invalid_rating": len(bad_ratings),
                 "nonnumeric_likes": counts["nonnumeric_likes"]},
        "exact_text_duplicates": {
            "distinct_nonempty_texts": distinct, "rows_reusing_an_earlier_identical_text": dup_rows,
            "texts_appearing_more_than_once": sum(1 for c in text_counts.values() if c > 1),
            "most_common": [{"text": t[:80], "count": c} for t, c in text_counts.most_common(15)]},
        "text_length_chars": _quantiles(lengths),
        "review_likes": _quantiles(likes),
        "reviews_by_rating": dict(sorted(ratings.items())),
        "reviews_by_month": dict(sorted(months.items())),
        "first_review": helper_profile["first_review"], "last_review": helper_profile["last_review"],
        "quarantine": {"reason": "empty_review_text", "review_ids": empty_ids},
        "duplicate_review_ids": duplicate_ids[:100],
        "scope": {"rule": "all nonempty IDs" if scope_size is None else
                  f"lowest {scope_size} SHA-256('{common.SAMPLE_SEED}:' + review_id) among nonempty IDs (course sampling order)",
                  "in_scope_ids": len(in_scope), "in_scope_distinct_texts": scope_texts,
                  "out_of_scope_ids_with_exact_text_match": reusable,
                  "out_of_scope_ids_without_match": len(seen) - len(empty_ids) - len(in_scope) - reusable},
        "helper_profile_file": "ingestion.json (same folder)",
        "seconds": round(time.time() - started, 2),
    }
    report["checks_vs_manifest"] = _manifest_checks(report, manifest) if report["input"]["matches_course_manifest"] else "input is not the course file"
    if samples_dir:
        report["sample_order_checks"] = _sample_checks(conn, Path(samples_dir))
    common.write_json(report_dir / "ingestion_report.json", report)
    common.write_json(report_dir / "data_manifest.json", {
        "source": manifest["source"], "window": manifest["window"],
        "input": report["input"], "parsed_rows_sha256": helper_profile["parsed_rows_sha256"],
        "row_hash": "SHA-256 of UTF-8 compact JSON of the six source fields (course row_sha helper)",
        "scope": report["scope"]["rule"]})
    conn.close()
    return report


def _manifest_checks(report, manifest):
    expected = manifest["profile"]
    actual = {"records": report["rows"]["parsed"], "duplicate_review_ids": report["rows"]["duplicate_review_id_rows"],
              "empty_review_text": report["rows"]["empty_review_text"], "missing_app_version": report["rows"]["missing_app_version"]}
    checks = {k: {"expected": expected[k], "actual": actual[k], "ok": expected[k] == actual[k]} for k in expected}
    checks["reviews_by_rating"] = {"ok": report["reviews_by_rating"] == manifest["reviews_by_rating"]}
    checks["reviews_by_month"] = {"ok": report["reviews_by_month"] == manifest["reviews_by_month"]}
    checks["distinct_nonempty_texts"] = {"expected": 484189, "actual": report["exact_text_duplicates"]["distinct_nonempty_texts"],
                                         "ok": report["exact_text_duplicates"]["distinct_nonempty_texts"] == 484189}
    return checks


def _sample_checks(conn, samples_dir):
    """Confirm the course files are exactly the first IDs in our rank order (golden 50, then the dev samples)."""
    ordered = [r[0] for r in conn.execute(
        "SELECT review_id FROM source_rows WHERE is_empty = 0 AND review_rating IN ('1','2','3','4','5') "
        "ORDER BY sample_rank, review_id LIMIT 10050")]
    out = {}
    for name, expected in (("golden_50_to_label.csv", ordered[:50]), ("analysis_10000.csv", ordered[50:]),
                           ("checkpoint_500.csv", ordered[50:550]), ("cost_100.csv", ordered[50:150])):
        path = samples_dir / name
        if path.exists():
            ids = [r["review_id"] for r in common.csv_rows(path)]
            out[name] = {"rows": len(ids), "matches_rank_order": ids == expected}
    return out
