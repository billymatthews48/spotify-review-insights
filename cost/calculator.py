"""100-review cost and runtime calculator (COST_CALCULATOR.md).

DEFAULT = OFFLINE REPLAY. Standard library only: no API key, no network, no model calls.
    python cost/calculator.py                 # recompute everything from saved usage + cost/rates.csv
    python cost/calculator.py --rates-multiplier 2   # what-if: every API rate doubled (usage fixed)
Paid pilot execution is a separate, explicit command (see cost/README.md):
    python -m pipeline pilot --confirm-paid

Inputs (all saved files): pilot_calls.jsonl, pilot_runs.json, pilot_records.jsonl, rates.csv, assumptions.json,
checkpoint_500_calls.jsonl / checkpoint_500_run.json and, when present, checkpoint_10000_calls.jsonl / _run.json.
Outputs: usage.csv (every billed item per call), report.md, report.html, report.json.

Cost of a billing item = billed_units x price_per_unit. Input, cached input and output are mutually exclusive:
uncached input = input_tokens - cached_input_tokens; reasoning tokens are already inside output tokens.
"""

import argparse
import csv
import html
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_rates(path, multiplier=1.0):
    rates, sources = {}, {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["model"], row["billing_item"])
            rates[key] = float(row["price_per_unit_usd"]) * multiplier
            sources[key] = row
    return rates, sources


def billing_items(call, rates):
    """Mutually exclusive billed items for one call: [(item, units, unit_price, cost)]."""
    model = call["model"]
    inp, cached, out = call.get("input_tokens", 0), call.get("cached_input_tokens", 0), call.get("output_tokens", 0)
    if (model, "input_uncached") in rates:
        items = [("input_uncached", inp - cached, rates[(model, "input_uncached")]),
                 ("input_cached", cached, rates[(model, "input_cached")]),
                 ("output", out, rates[(model, "output")])]
    elif (model, "input") in rates:
        items = [("input", inp, rates[(model, "input")]), ("output", out, rates.get((model, "output"), 0.0))]
    else:
        raise SystemExit(f"No rate for model {model} in rates.csv; add it rather than assuming zero.")
    return [(name, units, price, units * price) for name, units, price in items]


def stage_of(call):
    return {"jev_labels": "enrich: Jev labels", "luna_quotes": "enrich: gpt quotes", "luna_relabel": "verify",
            "luna_discover_issues": "group: discover", "luna_assign_issue": "group: assign",
            "luna_memo": "memo"}.get(call.get("step"), call.get("role"))


def summarize_calls(calls, rates):
    by_stage = defaultdict(lambda: {"requests": 0, "attempts": 0, "failed": 0, "review_ids_sent": 0, "input_tokens": 0,
                                    "cached_input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost": 0.0,
                                    "models": set(), "usage_missing": 0, "seconds_summed": 0.0})
    usage_rows = []
    for c in calls:
        s = by_stage[stage_of(c)]
        s["attempts"] += 1
        s["requests"] += c.get("attempt", 1) == 1
        s["failed"] += c["outcome"] == "failed"
        s["review_ids_sent"] += len(c["review_ids"])
        for k in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"):
            s[k] += c.get(k, 0) or 0
        s["models"].add(f"{c['model']}" + (f" (effort {c['effort']})" if c.get("effort") else ""))
        s["usage_missing"] += c.get("usage_status") not in ("reported", "none_reported")
        s["seconds_summed"] += c.get("seconds", 0) or 0
        for item, units, price, cost in billing_items(c, rates):
            s["cost"] += cost
            usage_rows.append({"request_id": c["request_id"], "run": c.get("pilot_run", c.get("phase")), "stage": stage_of(c),
                               "provider": c.get("provider"), "model": c["model"], "outcome": c["outcome"],
                               "usage_status": c.get("usage_status"), "billing_item": item, "billed_units": units,
                               "unit": "token", "price_per_unit_usd": f"{price:.12f}", "cost_usd": f"{cost:.10f}"})
    for s in by_stage.values():
        s["models"] = sorted(s["models"])
    return dict(by_stage), usage_rows


def per_unit(stage, units):
    return {k: (stage[k] / units if units else 0.0) for k in ("input_tokens", "cached_input_tokens", "output_tokens", "cost")}


def project(scenario, name, measured, a, rates_cost_per_unit, throughput, distinct_texts, ids_total, completed_ids):
    """Stage-by-stage projection: variable work x measured unit cost (+ retry allowance) + fixed overhead once."""
    retry = a[name]["extra_attempt_rate"] if a[name]["extra_attempt_rate"] is not None else measured["retry_rate"]
    long_share = measured["long_text_share"] * a[name]["long_text_share_multiplier"]
    complaint_share = min(1.0, measured["complaint_share"] * a[name]["complaint_share_multiplier"])
    verify_n = math.ceil(a["verify_fraction"] * distinct_texts)
    c = rates_cost_per_unit
    lines = [
        ("enrich: Jev labels", distinct_texts, c["jev_per_text"] * distinct_texts * (1 + retry)),
        ("enrich: gpt quotes", round(distinct_texts * long_share), c["quote_per_long_text"] * distinct_texts * long_share * (1 + retry)),
        ("verify", verify_n, c["verify_per_text"] * verify_n * (1 + retry)),
        ("group: assign", round(distinct_texts * complaint_share), c["assign_per_text"] * distinct_texts * complaint_share * (1 + retry)),
        ("group: discover (fixed)", a["group_discovery"]["topics"], c["discover_fixed"]),
        ("memo (fixed)", a[name]["memo_attempts"], c["memo_per_call"] * a[name]["memo_attempts"]),
    ]
    total = sum(x[2] for x in lines)
    tp = throughput * a[name].get("throughput_multiplier", 1.0)
    enrich_seconds = distinct_texts / tp if tp else None
    return {"scenario": scenario, "case": name, "distinct_texts_sent": distinct_texts, "source_ids_accounted": ids_total,
            "completed_classifications": completed_ids, "lines": [{"stage": s, "work_units": round(u), "api_cost_usd": v} for s, u, v in lines],
            "api_cost_usd": total, "enrich_throughput_texts_per_s": tp, "enrich_hours": enrich_seconds / 3600 if enrich_seconds else None,
            "assumptions": {"extra_attempt_rate": retry, "long_text_share": long_share, "complaint_share": complaint_share,
                            "verify_fraction": a["verify_fraction"]}}


def main():
    ap = argparse.ArgumentParser(description="Offline replay of the measured 100-review pilot + full-run projections")
    ap.add_argument("--rates", type=Path, default=HERE / "rates.csv")
    ap.add_argument("--assumptions", type=Path, default=HERE / "assumptions.json")
    ap.add_argument("--rates-multiplier", type=float, default=1.0, help="What-if: scale every API rate (usage fixed)")
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rates, sources = load_rates(args.rates, args.rates_multiplier)
    a = json.loads(args.assumptions.read_text(encoding="utf-8"))
    runs = json.loads((HERE / "pilot_runs.json").read_text(encoding="utf-8"))
    calls = load_jsonl(HERE / "pilot_calls.jsonl")
    records = load_jsonl(HERE / "pilot_records.jsonl")
    cold_calls = [c for c in calls if c["pilot_run"] == "cold"]
    warm_calls = [c for c in calls if c["pilot_run"] == "warm"]
    cold, usage_rows = summarize_calls(cold_calls, rates)
    warm, warm_usage = summarize_calls(warm_calls, rates)
    usage_rows += warm_usage

    with (args.out / "usage.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(usage_rows[0]) if usage_rows else ["request_id"], lineterminator="\n")
        w.writeheader()
        w.writerows(usage_rows)

    # ---- measured pilot ----
    cold_run, warm_run = runs["runs"]["cold"], runs["runs"]["warm"]
    n = len(records)
    completed = sum(r["status"] == "completed" for r in records)
    failed = n - completed
    texts = cold_run["enrich"]["completed"]  # distinct texts sent to the enricher
    cold_cost = sum(s["cost"] for s in cold.values())
    warm_cost = sum(s["cost"] for s in warm.values())
    attempts = sum(s["attempts"] for s in cold.values())
    failed_attempts = sum(s["failed"] for s in cold.values())
    long_texts = cold.get("enrich: gpt quotes", {}).get("review_ids_sent", 0)
    assigned = cold.get("group: assign", {}).get("review_ids_sent", 0)
    measured = {"retry_rate": failed_attempts / attempts if attempts else 0.0, "long_text_share": long_texts / texts if texts else 0,
                "complaint_share": (sum(1 for r in records if r.get("intent") in ("complaint", "cancellation")) / completed) if completed else 0}
    unit = {
        "jev_per_text": cold["enrich: Jev labels"]["cost"] / cold["enrich: Jev labels"]["review_ids_sent"],
        "quote_per_long_text": (cold["enrich: gpt quotes"]["cost"] / long_texts) if long_texts else 0.0,
        "verify_per_text": cold["verify"]["cost"] / cold["verify"]["review_ids_sent"],
        "assign_per_text": (cold["group: assign"]["cost"] / assigned) if assigned else 0.0,
        "memo_per_call": cold["memo"]["cost"] / cold["memo"]["attempts"],
    }
    disc = cold.get("group: discover")
    if disc:  # discovery scales with examples shown, not with corpus size: fixed overhead once per run
        per_example_cost = disc["cost"] / max(1, disc["review_ids_sent"])
        unit["discover_fixed"] = per_example_cost * a["group_discovery"]["topics"] * a["group_discovery"]["examples_per_topic"]
    else:
        unit["discover_fixed"] = 0.0

    # ---- throughput refreshes: pilot (1 worker), checkpoint 500, checkpoint 10000 when available ----
    refreshes = []
    pilot_tp = texts / cold_run["stage_seconds"]["enrich"]
    refreshes.append({"checkpoint": "pilot 100 (cold, 1 worker)", "texts": texts, "enrich_seconds": cold_run["stage_seconds"]["enrich"],
                      "texts_per_s": pilot_tp, "jev_cost_per_text": unit["jev_per_text"],
                      "workers": "batch 1 / jev 1"})
    for name in ("checkpoint_500", "checkpoint_10000"):
        cp_calls = load_jsonl(HERE / f"{name}_calls.jsonl")
        meta_path = HERE / f"{name}_run.json"
        if not cp_calls or not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        # A checkpoint may have several measured segments (e.g. before/after a fix); each is its own row.
        for seg in meta.get("segments", [meta]):
            seg_calls = [c for c in cp_calls if not seg.get("run_id") or c.get("run_id") == seg["run_id"]]
            st, _ = summarize_calls(seg_calls, rates)
            jev = st.get("enrich: Jev labels")
            refreshes.append({"checkpoint": f"{name} {seg.get('label', '')}".strip(), "texts": seg["end"]["completed"],
                              "enrich_seconds": seg["end"]["seconds"], "texts_per_s": seg["end"]["completed"] / seg["end"]["seconds"],
                              "jev_cost_per_text": jev["cost"] / jev["review_ids_sent"] if jev else None,
                              "workers": f"batch {seg['start'].get('batch_workers')} / jev {seg['start'].get('jev_workers')}"})
    latest_tp = refreshes[-1]["texts_per_s"]

    vol = a["volumes"]
    scenarios = []
    specs = [("100k scope, exact-text reuse (chosen)", vol["scope_100k"]["distinct_texts"], vol["full_corpus"]["rows"],
              vol["scope_100k"]["in_scope_ids"] + vol["scope_100k"]["out_of_scope_ids_reusing_exact_text"]),
             ("Full corpus, exact-text reuse", vol["full_corpus"]["distinct_nonempty_texts"], vol["full_corpus"]["rows"],
              vol["full_corpus"]["nonempty"]),
             ("Full corpus, NO reuse (comparison)", vol["full_corpus"]["nonempty"], vol["full_corpus"]["rows"],
              vol["full_corpus"]["nonempty"])]
    for label, distinct, ids_total, completed_ids in specs:
        for case in ("base", "conservative"):
            p = project(label, case, measured, a, unit, latest_tp, distinct, ids_total, completed_ids)
            p["over_budget"] = p["api_cost_usd"] > a["budget_usd"]
            scenarios.append(p)

    report = {
        "rates_multiplier": args.rates_multiplier,
        "measured": {
            "input": runs["input"], "records": n, "completed": completed, "failed_or_quarantined": failed,
            "distinct_texts_enriched": texts, "result_cache_hits_warm": sum(1 for r in load_jsonl(HERE / "pilot_records_warm.jsonl")
                                                                            if r.get("result_cache_run")),
            "cold": {"wall_clock_seconds": cold_run["wall_clock_seconds"], "stage_seconds": cold_run["stage_seconds"],
                     "api_cost_usd": cold_cost, "requests": sum(s["requests"] for s in cold.values()), "attempts": attempts,
                     "failed_attempts": failed_attempts, "cost_per_1000_inputs": cold_cost / n * 1000,
                     "cost_per_completed_record": cold_cost / completed if completed else None,
                     "throughput_records_per_s": n / cold_run["wall_clock_seconds"]},
            "warm": {"wall_clock_seconds": warm_run["wall_clock_seconds"], "stage_seconds": warm_run["stage_seconds"],
                     "api_cost_usd": warm_cost, "new_calls": len(warm_calls),
                     "new_enrichment_calls": sum(1 for c in warm_calls if c["role"] == "enrich")},
            "by_stage": {k: {**v, "cost": v["cost"]} for k, v in cold.items()},
            "unit_costs": unit, "measured_rates": measured, "settings": runs["settings"],
        },
        "refreshes": refreshes, "scenarios": scenarios, "budget_usd": a["budget_usd"], "controls": a["controls"],
        "local_compute": a["local_compute"], "infrastructure": a["infrastructure"],
        "rate_sources": [dict(v) for v in sources.values()],
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    md = render_md(report)
    (args.out / "report.md").write_text(md, encoding="utf-8", newline="\n")
    (args.out / "report.html").write_text(render_html(md), encoding="utf-8", newline="\n")
    print(f"Offline replay done (no API calls). Cold pilot API cost ${cold_cost:.6f}; warm ${warm_cost:.6f}; "
          f"rates x{args.rates_multiplier}. Wrote report.md, report.html, report.json, usage.csv")
    for s in scenarios:
        flag = "  ** OVER BUDGET **" if s["over_budget"] else ""
        print(f"  {s['scenario']:42} {s['case']:12} ${s['api_cost_usd']:.2f}{flag}")


def money(x):
    return "n/a" if x is None else (f"${x:.6f}" if x < 0.01 else f"${x:,.4f}" if x < 1 else f"${x:,.2f}")


def render_md(r):
    m = r["measured"]
    L = ["# 100-review cost and runtime calculator", "",
         f"Offline replay of saved measurements; rates multiplier **x{r['rates_multiplier']}**. "
         "Regenerate with `python cost/calculator.py` (no API key, no model calls).", "",
         "## Measured pilot (cost_100.csv, unchanged)", "",
         f"- Input: `{m['input']['file']}` sha256 `{m['input']['sha256']}`; {m['records']} source IDs; "
         f"{m['completed']} completed, {m['failed_or_quarantined']} failed/quarantined; {m['distinct_texts_enriched']} distinct texts enriched.",
         f"- Settings: label_config `{m['settings']['label_config']}`; enrichment batch <= {m['settings']['batch_size']} reviews; "
         f"workers: batch {m['settings']['batch_workers']}, Jev {m['settings']['jev_workers']} (one worker, as specified).",
         f"- Models: " + "; ".join(f"{k}: `{v}`" for k, v in m["settings"]["models"].items()) + ".",
         f"- Prompt versions: " + ", ".join(f"{k} `{v}`" for k, v in m["settings"]["prompt_versions"].items()) + "; schema `schema-v1`.", "",
         "| | Cold (empty result cache) | Warm (saved result cache) |", "|---|---|---|",
         f"| End-to-end wall clock | {m['cold']['wall_clock_seconds']:.2f} s | {m['warm']['wall_clock_seconds']:.2f} s |",
         f"| API cost | {money(m['cold']['api_cost_usd'])} | {money(m['warm']['api_cost_usd'])} |",
         f"| Requests / attempts / failed | {m['cold']['requests']} / {m['cold']['attempts']} / {m['cold']['failed_attempts']} | "
         f"{m['warm']['new_calls']} new calls ({m['warm']['new_enrichment_calls']} enrichment) |",
         f"| Result-cache hits | 0 | {m['result_cache_hits_warm']} of {m['records']} |",
         f"| Cost per 1,000 inputs | {money(m['cold']['cost_per_1000_inputs'])} | $0 |",
         f"| Cost per completed record | {money(m['cold']['cost_per_completed_record'])} | $0 |",
         f"| Throughput | {m['cold']['throughput_records_per_s']:.2f} records/s | {m['records'] / m['warm']['wall_clock_seconds']:.1f} records/s |", "",
         "Stage seconds (cold): " + ", ".join(f"{k} {v}" for k, v in m["cold"]["stage_seconds"].items()) + ". "
         "Stage seconds (warm): " + ", ".join(f"{k} {v}" for k, v in m["warm"]["stage_seconds"].items()) + ".", "",
         "### Cold run by stage (actual usage x editable rates)", "",
         "| Stage | Provider | Model (effort) | Prompt / schema | Batch limit | Workers | Requests | Attempts | Failed | Review IDs sent | Input tok | Cached tok | Output tok | Cost |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    pv = m["settings"]["prompt_versions"]
    jw, bw = m["settings"]["jev_workers"], m["settings"]["batch_workers"]
    stage_meta = {  # what each pilot stage ran with (from pilot_runs.json settings and the pipeline design)
        "enrich: Jev labels": ("TypeSafe", f"{pv['labels']} (jev_questions_v1) / schema-v1", "1 review per request; batches of 50", f"Jev {jw}"),
        "enrich: gpt quotes": ("OpenAI", f"{pv['labels']} (quote_v1) / schema-v1", "<= 50 reviews per request", f"batch {bw}"),
        "verify": ("OpenAI", f"{pv['labels']} (verify_system) / schema-v1", "<= 50 reviews per request", "1"),
        "group: discover": ("OpenAI", f"{pv['group']} / schema-v1", "<= 120 examples per topic", "1"),
        "group: assign": ("OpenAI", f"{pv['group']} / schema-v1", "<= 50 reviews per request", "1"),
        "memo": ("OpenAI", f"{pv['memo']} / schema-v1", "1 request (aggregates only)", "1"),
    }
    for k, s in m["by_stage"].items():
        prov, prompt, batch, workers = stage_meta.get(k, ("", "", "", ""))
        L.append(f"| {k} | {prov} | {', '.join(s['models'])} | {prompt} | {batch} | {workers} | {s['requests']} | {s['attempts']} | "
                 f"{s['failed']} | {s['review_ids_sent']} | {s['input_tokens']:,} | {s['cached_input_tokens']:,} | "
                 f"{s['output_tokens']:,} | {money(s['cost'])} |")
    L += ["", "Retries: 0 failed attempts in the pilot, so the base projection adds no retry allowance; the conservative case adds 10%. "
          "Verification: a declared seeded sample (3% of distinct texts, minimum 20; 20 in the pilot). Fallbacks: none configured "
          "(no stronger model); a quote failure falls back to an exact text prefix in code at zero API cost.", "",
          "## Estimate refreshes (100 -> 500 -> 10,000)", "", "| Checkpoint | Distinct texts | Enrich seconds | Texts/s | Jev cost/text | Workers |",
          "|---|---|---|---|---|---|"]
    for x in r["refreshes"]:
        L.append(f"| {x['checkpoint']} | {x['texts']:,} | {x['enrich_seconds']:.1f} | {x['texts_per_s']:.2f} | {money(x['jev_cost_per_text'])} | {x['workers']} |")
    L += ["", "Projections use the latest refresh's enrichment throughput. Elapsed time is modeled from measured throughput, "
          "not from summed call durations (calls overlap when workers > 1).", "",
          f"## Full-run projections (budget {money(r['budget_usd'])})", "",
          "| Scenario | Case | Distinct texts sent | Completed classifications | API cost | Enrich time | Budget |", "|---|---|---|---|---|---|---|"]
    for s in r["scenarios"]:
        L.append(f"| {s['scenario']} | {s['case']} | {s['distinct_texts_sent']:,} | {s['completed_classifications']:,} | "
                 f"{money(s['api_cost_usd'])} | {s['enrich_hours']:.2f} h | {'**OVER BUDGET**' if s['over_budget'] else 'within'} |")
    L += ["", "All scenarios account for all 660,622 source rows and 13 empty-text quarantines. Stage detail (work units x unit cost):", ""]
    for s in r["scenarios"]:
        L.append(f"- **{s['scenario']} / {s['case']}**: " + "; ".join(f"{x['stage']} {x['work_units']:,} -> {money(x['api_cost_usd'])}"
                                                                    for x in s["lines"]) +
                 f". Assumptions: extra attempts {s['assumptions']['extra_attempt_rate']:.0%}, long-text share "
                 f"{s['assumptions']['long_text_share']:.3f}, complaint share {s['assumptions']['complaint_share']:.3f}.")
    c = r["controls"]
    L += ["", "## Controls", "",
          f"- Spending limit: {money(r['budget_usd'])} (`limits.spend_cap_usd` in config/run_config.json; the pipeline reserves an "
          "estimated worst case before every call and stops admitting work when spent + reserved + next > cap).",
          f"- Output-token cap per request: {c['output_token_cap_per_request']:,}; max reviews per enrichment request: "
          f"{c['max_reviews_per_enrich_request']}.",
          f"- Max workers: Jev {c['max_jev_workers']}, batch {c['max_batch_workers']}; shared rate limiter and one spend ledger.",
          f"- Max fallback fraction: {c['max_fallback_fraction']:.0%}; fallback model: {c['fallback_model']}.", "",
          "## Not API spend", "",
          f"- Local compute: **{r['local_compute']['api_free_local_cost']}**. {r['local_compute']['detail']}",
          "- Infrastructure: " + "; ".join(f"{k}: {v}" for k, v in r["infrastructure"].items()) + ".", "",
          "## Rates used (editable: cost/rates.csv)", "", "| Provider | Model | Item | Price per unit | Quoted as | Checked | Source |",
          "|---|---|---|---|---|---|---|"]
    for s in r["rate_sources"]:
        L.append(f"| {s['provider']} | {s['model']} | {s['billing_item']} | {float(s['price_per_unit_usd']) * r['rates_multiplier']:.12f} | "
                 f"{s['price_quoted_as']} | {s['checked_on']} | {s['source_url']} |")
    L += ["", "Every charged item per call is in `usage.csv` (request_id -> billing item -> billed units x price). "
          "Raw per-attempt usage and timing are in `pilot_calls.jsonl`.", ""]
    return "\n".join(L)


def render_html(md):
    """Tiny markdown-table renderer so the report opens in a browser without dependencies."""
    out, in_table = [], False
    for line in md.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("### "):
            out.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("- "):
            out.append(f"<li>{_inline(line[2:])}</li>")
        elif line.strip():
            out.append(f"<p>{_inline(line)}</p>")
    if in_table:
        out.append("</table>")
    style = ("body{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#1c1c1a;background:#fff}"
             "table{border-collapse:collapse;margin:8px 0 16px;font-size:13px}td,th{border:1px solid #ddd;padding:4px 8px;text-align:left}"
             "th{background:#f3f3f0}code{background:#f3f3f0;padding:1px 4px;border-radius:3px}")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Cost calculator report</title><style>{style}</style></head><body>" \
           + "\n".join(out) + "</body></html>\n"


def _inline(s):
    import re
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", s)


if __name__ == "__main__":
    main()
