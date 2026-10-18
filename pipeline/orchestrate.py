"""Orchestrator: input CSV -> ingest -> enrich -> verify -> group -> rank -> memo, with saved handoffs.

Code decides the order and every stop condition; models only answer bounded questions inside a stage.
Each stage reads the previous stage's saved output from the state DB, so any stage can be rerun alone.
"""

import json
import time
from pathlib import Path

from . import common, enrich, group, memo, rank, runtime, verify
from .ingest import ingest
from .stage import Context


def analyze(state, cache, out_dir, cfg=None, phase="initial"):
    """Stages 3-6 on an already-enriched state. Returns per-stage timings and summaries."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = Context(state, cache, phase, "analyze", cfg)
    timings, results = {}, {}
    try:
        t = time.time()
        results["verify"] = verify.run(ctx, out_dir)
        timings["verify"] = round(time.time() - t, 2)
        t = time.time()
        results["group"] = group.run(ctx, out_dir)
        timings["group"] = round(time.time() - t, 2)
        gc = results["group"]["group_config"]
        t = time.time()
        agg = rank.run(ctx, out_dir, gc)
        timings["rank"] = round(time.time() - t, 2)
        results["rank"] = {"issues": len(agg), "top5": [(r["issue_id"], r["name"], r["priority_score"]) for r in agg[:5]]}
        t = time.time()
        res = memo.run(ctx, out_dir, gc, agg)
        timings["memo"] = round(time.time() - t, 2)
        results["memo"] = {"attempts": res["attempts"], "problems": res["problems"],
                           "area": (res["memo"] or {}).get("recommendation", {}).get("area")}
    finally:
        ctx.close()
    return timings, results


def run_all(input_csv, state, out_dir, scope_size=None, cache=None, batch_workers=4, jev_workers=None, cfg=None,
            phase="initial"):
    cfg = cfg or runtime.load_config()
    if jev_workers:
        cfg["enrich"]["workers"] = jev_workers
    state, out_dir = Path(state), Path(out_dir)
    cache = Path(cache) if cache else state.with_name(state.stem + "_cache.sqlite")
    started = time.time()
    timings = {}
    t = time.time()
    if not state.exists():
        ingest(input_csv, state, scope_size, report_dir=out_dir)
    timings["ingest"] = round(time.time() - t, 2)
    t = time.time()
    enrich_summary = enrich.run(state, cache, phase, batch_workers=batch_workers, cfg=cfg)
    timings["enrich"] = round(time.time() - t, 2)
    stage_t, results = analyze(state, cache, out_dir, cfg, phase)
    timings.update(stage_t)
    summary = {"input": str(input_csv), "input_sha256": common.file_sha(input_csv), "state": str(state),
               "cache": str(cache), "label_config": runtime.label_config(cfg), "enrich": enrich_summary,
               **results, "stage_seconds": timings, "wall_clock_seconds": round(time.time() - started, 2),
               "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    common.write_json(out_dir / "run_summary.json", summary)
    return summary


def rerank_from_files(records_jsonl, membership_csv, out_csv):
    """Offline, no DB, no model, no API key: rebuild the baseline ranking from exported files."""
    import csv
    import gzip
    opener = gzip.open if str(records_jsonl).endswith(".gz") else open
    records = {}
    with opener(records_jsonl, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                if r.get("status") == "completed":
                    records[r["review_id"]] = r
    with open(membership_csv, encoding="utf-8", newline="") as f:
        membership = [(row["issue_id"], row["review_id"]) for row in csv.DictReader(f)]
    rows = rank.compute(records, membership)
    rank.write_ranking(rows, out_csv)
    return rows
