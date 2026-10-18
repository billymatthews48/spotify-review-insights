"""Golden-set evaluation: 50 human labels vs the final pipeline's saved predictions (no new enrichment calls).

Usage: .venv/Scripts/python evals/golden_eval.py --labels evals/golden/golden_50_labeled.csv --state state/full.sqlite
       [--compare-luna]   (PAID, ~$0.002: blind gpt-6-luna-only labels on the same 50 texts, as a setup comparison)

Human labels are never model inputs: this script only reads them after predictions exist.
Pre-declared tolerances: sentiment counts as agreeing when |pred - human| <= 0.5; severity reports exact + MAE.
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import common, labels  # noqa: E402
from pipeline.enrich import open_state  # noqa: E402

OUT = ROOT / "evals" / "golden"
SENTIMENT_TOLERANCE = 0.5


def load_human(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        if not (r.get("topic") and r.get("intent") and r.get("severity")):
            raise SystemExit(f"Unlabelled golden row {r['review_id']}: finish all 50 before evaluating.")
        out[r["review_id"]] = {"text": r["review_text"], "topic": r["topic"], "intent": r["intent"], "severity": int(r["severity"]),
                               "sentiment": float(r["sentiment"]), "entities": json.loads(r.get("entities") or "[]"),
                               "evidence_quote": r.get("evidence_quote", ""),
                               "needs_review": r.get("needs_review", "false") == "true",
                               "ambiguous": r.get("ambiguous", "false") == "true", "notes": r.get("notes", "")}
    if len(out) != 50:
        raise SystemExit(f"Expected 50 golden rows, found {len(out)}")
    return out


def predictions(state):
    conn = open_state(state, Path(state).with_name(Path(state).stem + "_cache.sqlite"))
    rows = conn.execute("""
        SELECT r.review_id, r.status, r.reason, l.topic, l.intent, l.severity, l.sentiment, l.entities, l.evidence_quote,
               l.needs_review, l.review_reasons, r.label_config
        FROM records r JOIN source_rows s USING(review_id)
        LEFT JOIN cache.labels l ON l.text_sha256 = s.text_sha256 AND l.label_config = r.label_config""").fetchall()
    conn.close()
    return {r[0]: {"status": r[1], "reason": r[2], "topic": r[3], "intent": r[4], "severity": r[5], "sentiment": r[6],
                   "entities": json.loads(r[7]) if r[7] else [], "evidence_quote": r[8], "needs_review": bool(r[9]),
                   "review_reasons": json.loads(r[10]) if r[10] else [], "label_config": r[11]} for r in rows}


def score(human, pred, name):
    n = len(human)
    agree = Counter()
    sev_abs = sent_abs = 0.0
    confusion = Counter()
    per_topic = Counter()
    nr = Counter()
    cases = []
    for rid, h in human.items():
        p = pred.get(rid) or {}
        ok = p.get("status", "completed") == "completed" and p.get("topic") is not None
        t_ok, i_ok = ok and p["topic"] == h["topic"], ok and p["intent"] == h["intent"]
        s_ok = ok and p["severity"] == h["severity"]
        sent_ok = ok and abs(p["sentiment"] - h["sentiment"]) <= SENTIMENT_TOLERANCE
        agree.update({"topic": t_ok, "intent": i_ok, "severity": s_ok, "sentiment_within_tol": sent_ok,
                      "topic_intent_severity": t_ok and i_ok and s_ok})
        if ok:
            sev_abs += abs(p["severity"] - h["severity"])
            sent_abs += abs(p["sentiment"] - h["sentiment"])
        confusion[(h["topic"], p.get("topic", "<missing>"))] += 1
        per_topic[h["topic"]] += 1
        wrong = not (t_ok and i_ok) or (ok and abs(p["severity"] - h["severity"]) >= 2)
        if "needs_review" in p:
            nr[(p["needs_review"], wrong)] += 1
        case = {"review_id": rid, "text": h["text"], "human": {k: h[k] for k in ("topic", "intent", "severity", "sentiment",
                                                                               "ambiguous", "notes")},
                "pred": {k: p.get(k) for k in ("status", "topic", "intent", "severity", "sentiment", "needs_review")},
                "pass": {"topic": t_ok, "intent": i_ok, "severity": s_ok, "sentiment": sent_ok}}
        if "evidence_quote" in p and p.get("evidence_quote") is not None:
            case["quote_exact_substring"] = p["evidence_quote"] in h["text"]
            case["pred_quote"] = p["evidence_quote"]
            extra = sorted(set(p.get("entities", [])) - {e.lower() for e in h["entities"]})
            case["entities_not_in_human_list"] = extra
        cases.append(case)
    summary = {"setup": name, "n": n, "ambiguous": sum(h["ambiguous"] for h in human.values()),
               "agreement": {k: round(agree[k] / n, 4) for k in ("topic", "intent", "severity", "sentiment_within_tol",
                                                                  "topic_intent_severity")},
               "severity_mae": round(sev_abs / n, 4), "sentiment_mae": round(sent_abs / n, 4),
               "missing_or_quarantined_predictions": sum(1 for c in cases if c["pred"]["status"] not in (None, "completed")),
               "per_topic_support": dict(per_topic),
               "topic_confusion_human_to_pred": {f"{a}->{b}": c for (a, b), c in sorted(confusion.items())},
               "agreement_excluding_ambiguous": None}
    clear = [c for c in cases if not c["human"]["ambiguous"]]
    if clear:
        summary["agreement_excluding_ambiguous"] = {f: round(sum(c["pass"][f] for c in clear) / len(clear), 4)
                                                    for f in ("topic", "intent", "severity")}
    if nr:
        summary["needs_review_as_predictor"] = {f"needs_review={a},materially_wrong={b}": c for (a, b), c in sorted(nr.items())}
    if any("quote_exact_substring" in c for c in cases):
        summary["quotes_exact_substring"] = sum(c.get("quote_exact_substring", False) for c in cases)
        summary["cases_with_entities_not_in_human_list"] = sum(bool(c.get("entities_not_in_human_list")) for c in cases)
    return summary, cases


def luna_only(human):
    """Setup comparison: blind gpt-6-luna labels for the same texts (one call). Logged to its own file."""
    from pipeline import luna_labeler, runtime
    from pipeline.providers import Luna, run_with_retries
    cfg, rates = runtime.load_config(), runtime.load_rates()
    luna = Luna(60)
    ids = list(human)
    index = {i + 1: rid for i, rid in enumerate(ids)}
    user = luna_labeler.user_message([(i, human[rid]["text"]) for i, rid in index.items()])
    payload, recs, err = run_with_retries(lambda n: luna.structured(
        "gpt-6-luna", "none", luna_labeler.system_prompt(), user, luna_labeler.SCHEMA, 6000, role="eval", step="golden_luna_only",
        review_ids=ids, rates=rates, label_config="eval-luna-only", attempt=n), cfg["limits"])
    common.write_jsonl(OUT / "luna_only_calls.jsonl", recs)
    good, _ = luna_labeler.validate(payload, index)
    return {index[i]: {"status": "completed", **lab} for i, lab in good.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, default=OUT / "golden_50_labeled.csv")
    ap.add_argument("--state", type=Path, default=ROOT / "state" / "full.sqlite")
    ap.add_argument("--compare-luna", action="store_true")
    args = ap.parse_args()
    human = load_human(args.labels)
    pred = predictions(args.state)
    summary, cases = score(human, pred, "final pipeline (Jev labels + code/gpt quotes)")
    report = {"primary": summary, "sentiment_tolerance": SENTIMENT_TOLERANCE,
              "note": "Golden labels were hand-labelled by the student and never used as model inputs, examples or thresholds."}
    if args.compare_luna:
        alt_summary, alt_cases = score(human, luna_only(human), "alternative: gpt-6-luna only (blind)")
        report["alternative"] = alt_summary
        common.write_jsonl(OUT / "golden_eval_cases_luna_only.jsonl", alt_cases)
    common.write_jsonl(OUT / "golden_eval_cases.jsonl", cases)
    common.write_json(OUT / "golden_eval_report.json", report)
    common.write_json(OUT / "golden_eval_summary.json", summary)
    print(json.dumps({k: v for k, v in report.items() if k != "note"}, indent=2))


if __name__ == "__main__":
    main()
