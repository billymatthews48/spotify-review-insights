"""Pipeline entry point: python -m pipeline <stage> ...

Stages run from saved handoffs; nothing here needs a chat transcript or manual pasting.
"""

import argparse
import json
from pathlib import Path

from . import common


def main():
    parser = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="Stage 1: read, profile, dedupe and queue an input CSV (no model calls)")
    p.add_argument("--input", required=True, type=Path, help="CSV with the six course fields")
    p.add_argument("--state", type=Path, default=common.DB_PATH, help="SQLite state file for this run")
    p.add_argument("--scope-size", type=int, default=None,
                   help="Classify only the lowest N IDs in course sample order (default: all nonempty)")
    p.add_argument("--samples-dir", type=Path, default=None, help="Folder with the course sample CSVs to cross-check")
    p.add_argument("--report-dir", type=Path, default=None, help="Where to write ingestion reports (default out/)")

    p = sub.add_parser("enrich", help="Stage 2: classify pending texts (PAID: Jev + gpt-6-luna calls)")
    p.add_argument("--state", type=Path, default=common.DB_PATH)
    p.add_argument("--cache", type=Path, default=None, help="Result-cache DB (default: <state>_cache.sqlite)")
    p.add_argument("--phase", choices=["initial", "resume"], default="initial")
    p.add_argument("--max-batches", type=int, default=None, help="Stop after N batches (development / demo)")
    p.add_argument("--limit-texts", type=int, default=None, help="Only the first N pending distinct texts")
    p.add_argument("--batch-size", type=int, default=50)
    p.add_argument("--batch-workers", type=int, default=4)
    p.add_argument("--jev-workers", type=int, default=None, help="Override enrich.workers in run_config.json")
    p.add_argument("--spend-cap", type=float, default=None, help="Override limits.spend_cap_usd")

    p = sub.add_parser("snapshot", help="Save completed_ids for interruption/resume evidence (no model calls)")
    p.add_argument("--state", type=Path, default=common.DB_PATH)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("prompts", help="Write the exact model prompts/questions in use to prompts/ (no model calls)")

    p = sub.add_parser("run", help="All stages on an input CSV (PAID): ingest, enrich, verify, group, rank, memo")
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path, help="Folder for this run's handoff files")
    p.add_argument("--scope-size", type=int, default=None)
    p.add_argument("--cache", type=Path, default=None)
    p.add_argument("--batch-workers", type=int, default=4)
    p.add_argument("--jev-workers", type=int, default=None)

    p = sub.add_parser("analyze", help="Stages 3-6 on an enriched state (PAID: verify/group/memo calls; cached on rerun)")
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--cache", type=Path, default=None)
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("pilot", help="PAID: measured cold+warm 100-review pilot -> cost/ evidence files")
    p.add_argument("--input", type=Path, default=common.ROOT / "data" / "dataset" / "cost_100.csv")
    p.add_argument("--confirm-paid", action="store_true", help="Required: acknowledges this makes real API calls")

    p = sub.add_parser("grading", help="Write the standardized grading/ export from saved outputs (no model calls)")
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--cache", type=Path, default=None)
    p.add_argument("--analysis", required=True, type=Path, help="Folder with membership.csv, ranking.csv, claims.csv")
    p.add_argument("--checkpoints", required=True, type=Path, help="Folder with checkpoint_before/after.json")
    p.add_argument("--out", type=Path, default=common.ROOT / "grading")

    p = sub.add_parser("report", help="Write run_log.jsonl + run_summary.json from a state DB (no model calls)")
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--cache", type=Path, default=None)
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("publish", help="Load saved outputs into Postgres (DATABASE_URL) for the dashboard (no model calls)")
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--cache", type=Path, default=None)
    p.add_argument("--analysis", required=True, type=Path)

    p = sub.add_parser("rerank", help="Rebuild ranking.csv from exported records + membership (offline, no model)")
    p.add_argument("--records", required=True, type=Path)
    p.add_argument("--membership", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "ingest":
        from .ingest import ingest
        report = ingest(args.input, args.state, args.scope_size, args.samples_dir, args.report_dir)
        print(json.dumps({k: report[k] for k in ("input", "rows", "scope", "seconds")}, indent=2))
    elif args.command == "enrich":
        from . import enrich, runtime
        cfg = runtime.load_config()
        if args.jev_workers:
            cfg["enrich"]["workers"] = args.jev_workers
        if args.spend_cap is not None:
            cfg["limits"]["spend_cap_usd"] = args.spend_cap
        cache = args.cache or args.state.with_name(args.state.stem + "_cache.sqlite")
        summary = enrich.run(args.state, cache, args.phase, args.max_batches, args.limit_texts, args.batch_size,
                             args.batch_workers, cfg)
        print(json.dumps(summary, indent=2))
    elif args.command == "snapshot":
        from . import enrich
        conn = common.connect(args.state)
        print("completed_ids saved:", enrich.snapshot(conn, args.out))
    elif args.command == "prompts":
        from . import enrich, runtime
        cfg = runtime.load_config()
        common.write_json(common.ROOT / "prompts" / "jev_questions_v1.json",
                          {"model": cfg["enrich"]["model"], "state_template": enrich.jev_state("<review_text>"),
                           "questions": enrich.jev_questions(), "label_config": runtime.label_config(cfg)})
        print("wrote prompts/jev_questions_v1.json")
    elif args.command == "run":
        from . import orchestrate
        summary = orchestrate.run_all(args.input, args.state, args.out, args.scope_size, args.cache,
                                      args.batch_workers, args.jev_workers)
        print(json.dumps({k: summary[k] for k in ("stage_seconds", "wall_clock_seconds", "memo")}, indent=2, default=str))
    elif args.command == "analyze":
        from . import orchestrate
        timings, results = orchestrate.analyze(args.state, args.cache, args.out)
        print(json.dumps({"stage_seconds": timings, **results}, indent=2, default=str))
    elif args.command == "pilot":
        if not args.confirm_paid:
            raise SystemExit("The pilot makes real paid API calls (about $0.01). Re-run with --confirm-paid.")
        from . import pilot
        meta = pilot.run(args.input)
        print(json.dumps({k: {kk: meta["runs"][k][kk] for kk in ("wall_clock_seconds", "stage_seconds")} for k in meta["runs"]},
                         indent=2))
    elif args.command == "grading":
        from . import grading
        cache = args.cache or args.state.with_name(args.state.stem + "_cache.sqlite")
        print(json.dumps(grading.write(args.state, cache, args.analysis, args.checkpoints, args.out), indent=2))
    elif args.command == "report":
        from . import report
        cache = args.cache or args.state.with_name(args.state.stem + "_cache.sqlite")
        s = report.write(args.state, cache, args.out)
        print(json.dumps({k: s[k] for k in ("record_status", "completed_total", "actual_api_charges_usd")}, indent=2))
    elif args.command == "publish":
        from . import publish
        cache = args.cache or args.state.with_name(args.state.stem + "_cache.sqlite")
        print(json.dumps(publish.run(args.state, cache, args.analysis), indent=2))
    elif args.command == "rerank":
        from . import orchestrate
        rows = orchestrate.rerank_from_files(args.records, args.membership, args.out)
        print(f"wrote {args.out}: {len(rows)} issues; top 3: {[(r['issue_id'], r['priority_score']) for r in rows[:3]]}")


if __name__ == "__main__":
    main()
