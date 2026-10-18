"""PAID: the measured 100-review pilot required by COST_CALCULATOR.md.

Cold run: cost_100.csv unchanged, empty result cache, one worker, every stage (enrich, declared verification
sample, grouping, ranking, memo). Warm run: same input and settings, fresh run state, the saved result cache.
Exports cost/pilot_records.jsonl, cost/pilot_calls.jsonl, cost/pilot_runs.json. Replay never calls this.
"""

import json
import shutil
import time
from pathlib import Path

from . import common, export, orchestrate, runtime

PILOT_DIR = common.ROOT / "state" / "pilot"
COST_DIR = common.ROOT / "cost"


def run(input_csv):
    input_csv = Path(input_csv)
    manifest = common.read_json(common.MANIFEST_PATH)
    digest = common.file_sha(input_csv)
    if digest != manifest["files"]["cost_100.csv"]["sha256"]:
        raise SystemExit(f"{input_csv} is not the unchanged course cost_100.csv (sha256 {digest})")
    if PILOT_DIR.exists():
        shutil.rmtree(PILOT_DIR)  # empty result cache for the cold experiment
    PILOT_DIR.mkdir(parents=True)
    cache = PILOT_DIR / "result_cache.sqlite"
    cfg = runtime.load_config()
    runs = {}
    for name in ("cold", "warm"):
        state = PILOT_DIR / f"{name}.sqlite"
        out = COST_DIR / "pilot" / name
        t = time.time()
        summary = orchestrate.run_all(input_csv, state, out, cache=cache, batch_workers=1, jev_workers=1, cfg=cfg)
        wall = round(time.time() - t, 3)
        conn = common.connect(state)
        conn.execute("ATTACH DATABASE ? AS cache", (str(cache),))
        calls = list(export.calls(conn))
        for c in calls:
            c["pilot_run"] = name
        recs = list(export.records(conn))
        conn.close()
        runs[name] = {"wall_clock_seconds": wall, "stage_seconds": summary["stage_seconds"],
                      "enrich": summary["enrich"], "verify": {k: summary["verify"].get(k) for k in
                                                              ("sample_declared", "compared", "agreement", "severity_mae")},
                      "group": summary["group"], "memo": summary["memo"], "calls": calls, "records": recs,
                      "finished_at": summary["finished_at"]}
    COST_DIR.mkdir(exist_ok=True)
    export.write_jsonl(COST_DIR / "pilot_records.jsonl", runs["cold"]["records"])
    export.write_jsonl(COST_DIR / "pilot_records_warm.jsonl", runs["warm"]["records"])
    export.write_jsonl(COST_DIR / "pilot_calls.jsonl", runs["cold"]["calls"] + runs["warm"]["calls"])
    meta = {"input": {"file": input_csv.name, "sha256": digest, "rows": len(runs["cold"]["records"])},
            "settings": {"label_config": runtime.label_config(cfg), "batch_size": 50, "batch_workers": 1, "jev_workers": 1,
                         "verify_fraction": cfg["verify"]["sample_fraction"], "verify_min_sample": cfg["verify"]["min_sample"],
                         "models": {"enrich": cfg["enrich"]["model"], "quote": f"{cfg['quote']['model']}/{cfg['quote']['reasoning_effort']}",
                                    "verify": f"{cfg['verify']['model']}/{cfg['verify']['reasoning_effort']}",
                                    "group": f"{cfg['group']['model_discover']}/{cfg['group']['reasoning_effort']}",
                                    "memo": f"{cfg['memo']['model']}/{cfg['memo']['reasoning_effort']}"},
                         "prompt_versions": {"labels": cfg["prompt_version"], "group": cfg["group"]["prompt_version"],
                                             "memo": cfg["memo"]["prompt_version"]}},
            "runs": {k: {kk: vv for kk, vv in v.items() if kk not in ("calls", "records")} for k, v in runs.items()}}
    common.write_json(COST_DIR / "pilot_runs.json", meta)
    return meta
