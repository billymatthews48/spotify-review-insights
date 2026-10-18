"""Load saved pipeline outputs into Postgres (Neon) for the deployed backend + dashboard. No model calls.

Tables: records, issues, ranking, membership, claims, memo, monthly, evals, run_meta.
Re-running replaces the published data atomically (one transaction), so the dashboard never shows a mix.
"""

import csv
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from . import common, export
from .enrich import open_state

DDL = """
DROP TABLE IF EXISTS records, issues, ranking, membership, claims, memo, monthly, evals, run_meta CASCADE;
CREATE TABLE run_meta(key TEXT PRIMARY KEY, value JSONB NOT NULL);
CREATE TABLE records(
  review_id TEXT PRIMARY KEY, status TEXT NOT NULL, reason TEXT, in_scope BOOLEAN NOT NULL,
  topic TEXT, intent TEXT, severity INT, sentiment REAL, needs_review BOOLEAN, evidence_quote TEXT,
  review_text TEXT, review_rating INT, review_likes INT, app_version TEXT, review_month TEXT,
  label_config TEXT, cache_source_id TEXT);
CREATE TABLE issues(issue_id TEXT PRIMARY KEY, topic TEXT, name TEXT, definition TEXT, source TEXT);
CREATE TABLE ranking(rank INT PRIMARY KEY, issue_id TEXT UNIQUE, complaint_count INT, severity_sum INT,
  mean_severity TEXT, priority_score INT, cancellation_count INT, severity_4plus_count INT, needs_review_count INT);
CREATE TABLE membership(issue_id TEXT, review_id TEXT, PRIMARY KEY(issue_id, review_id));
CREATE TABLE claims(claim_id TEXT PRIMARY KEY, issue_id TEXT, metric TEXT, value TEXT);
CREATE TABLE memo(id INT PRIMARY KEY, area TEXT, headline TEXT, rationale TEXT, issue_ids JSONB, alternatives JSONB,
  limitations JSONB, evidence_review_ids JSONB, memo_markdown TEXT, problems JSONB, model TEXT);
CREATE TABLE monthly(month TEXT, topic TEXT, classified INT, complaints INT, severity_sum INT, PRIMARY KEY(month, topic));
CREATE TABLE evals(name TEXT PRIMARY KEY, payload JSONB);
CREATE INDEX ON records(status);
CREATE INDEX ON records(topic, intent);
CREATE INDEX ON membership(review_id);
"""


def _csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def run(state, cache, analysis_dir, database_url=None):
    import psycopg
    load_dotenv(common.ROOT / ".env")
    url = database_url or os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is empty: add your Neon connection string to .env")
    analysis_dir = Path(analysis_dir)
    conn = open_state(state, cache)
    src = {r[0]: r[1:] for r in conn.execute(
        "SELECT review_id, review_text, review_rating, review_likes, app_version, substr(review_timestamp,1,7) FROM source_rows")}
    in_scope = dict(conn.execute("SELECT review_id, in_scope FROM records").fetchall())
    memo_out = common.read_json(analysis_dir / "memo_output.json")
    m = memo_out["memo"]
    evals = {"verify": analysis_dir / "verify_summary.json", "golden": common.ROOT / "evals" / "golden" / "golden_eval_summary.json",
             "system_tests": common.ROOT / "evals" / "system_tests" / "results.json",
             "cost_report": common.ROOT / "cost" / "report.json", "ingestion": common.OUT_DIR / "ingestion_report.json",
             "run_summary": analysis_dir / "run_summary.json"}
    monthly = conn.execute("""
        SELECT substr(s.review_timestamp,1,7), l.topic, COUNT(*), SUM(l.intent IN ('complaint','cancellation')),
               SUM(CASE WHEN l.intent IN ('complaint','cancellation') THEN l.severity ELSE 0 END)
        FROM records r JOIN source_rows s USING(review_id)
        JOIN cache.labels l ON l.text_sha256 = s.text_sha256 AND l.label_config = r.label_config
        WHERE r.status='completed' GROUP BY 1, 2""").fetchall()

    with psycopg.connect(url, autocommit=False) as pg, pg.cursor() as cur:
        cur.execute(DDL)
        with cur.copy("COPY records(review_id,status,reason,in_scope,topic,intent,severity,sentiment,needs_review,evidence_quote,"
                      "review_text,review_rating,review_likes,app_version,review_month,label_config,cache_source_id) FROM STDIN") as cp:
            n = 0
            for r in export.records(conn):
                text, rating, likes, version, month = src[r["review_id"]]
                done = r["status"] == "completed"
                cp.write_row((r["review_id"], r["status"], r.get("reason"), bool(in_scope[r["review_id"]]),
                              r.get("topic"), r.get("intent"), r.get("severity"), r.get("sentiment"), r.get("needs_review"),
                              r.get("evidence_quote"), text if done else None, int(rating) if rating.isdigit() else None,
                              int(likes) if likes.lstrip("-").isdigit() else None, version or None, month,
                              r.get("label_config"), r.get("cache_source_id")))
                n += 1
        catalog = common.read_json(analysis_dir / "issues_catalog.json")["issues"]
        cur.executemany("INSERT INTO issues VALUES (%s,%s,%s,%s,%s)",
                        [(i["issue_id"], i["topic"], i["name"], i["definition"], i["source"]) for i in catalog])
        agg = _csv(analysis_dir / "aggregates.csv")
        cur.executemany("INSERT INTO ranking VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        [(int(a["rank"]), a["issue_id"], int(a["complaint_count"]), int(a["severity_sum"]), a["mean_severity"],
                          int(a["priority_score"]), int(a["cancellation_count"]), int(a["severity_4plus_count"]),
                          int(a["needs_review_count"])) for a in agg])
        with cur.copy("COPY membership(issue_id, review_id) FROM STDIN") as cp:
            for row in _csv(analysis_dir / "membership.csv"):
                cp.write_row((row["issue_id"], row["review_id"]))
        cur.executemany("INSERT INTO claims VALUES (%s,%s,%s,%s)",
                        [(c["claim_id"], c["issue_id"], c["metric"], c["value"]) for c in _csv(analysis_dir / "claims.csv")])
        rec = m["recommendation"]
        cur.execute("INSERT INTO memo VALUES (1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rec["area"], rec["headline"], rec["rationale"], json.dumps(rec["issue_ids"]), json.dumps(m["alternatives"]),
                     json.dumps(m["limitations"]), json.dumps(m["evidence_review_ids"]), m["memo_markdown"],
                     json.dumps(memo_out["problems"]), memo_out.get("memo_config", "")))
        cur.executemany("INSERT INTO monthly VALUES (%s,%s,%s,%s,%s)", [tuple(r) for r in monthly])
        for name, path in evals.items():
            if Path(path).exists():
                cur.execute("INSERT INTO evals VALUES (%s,%s)", (name, Path(path).read_text(encoding="utf-8")))
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        status = dict(conn.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())
        for k, v in {"input_sha256": meta["input_sha256"], "scope_size": meta["scope_size"], "record_status": status,
                     "published_records": n}.items():
            cur.execute("INSERT INTO run_meta VALUES (%s,%s)", (k, json.dumps(v)))
        pg.commit()
    conn.close()
    return {"records": n, "issues": len(catalog), "ranking_rows": len(agg)}
