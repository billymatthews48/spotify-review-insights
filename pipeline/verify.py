"""Stage 3 - Verify (verifier role).

A declared, seeded random sample of completed origin records is re-labelled by gpt-6-luna from the
review text and rubric alone; it never sees the enricher's answer. Code then compares field by field,
writes a disagreement report, and runs a planted-error test on a separate synthetic copy of the sample
(deliberately wrong labels) to measure whether verification catches known errors.
"""

import hashlib
import json
import math
from collections import Counter

from . import common, labels, luna_labeler

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache.verify_preds(
    review_id TEXT NOT NULL, verify_config TEXT NOT NULL, run_id TEXT NOT NULL,
    topic TEXT NOT NULL, intent TEXT NOT NULL, severity INTEGER NOT NULL, sentiment REAL NOT NULL,
    PRIMARY KEY(review_id, verify_config)
);
"""


def verify_config(cfg):
    v = cfg["verify"]
    return f"{v['model']}/{v['reasoning_effort']}+verify-{cfg['prompt_version']}+{labels.LABELS_VERSION}"


def sample_ids(conn, label_config, fraction, seed, min_n):
    """Origin records only (the ID each label was computed for), ordered by a seeded hash. Selecting by the
    label's origin keeps the declared sample identical on a warm rerun that reads the same result cache."""
    ids = [r[0] for r in conn.execute("""SELECT r.review_id FROM records r JOIN cache.labels l
                                         ON l.origin_review_id = r.review_id AND l.label_config = r.label_config
                                         WHERE r.status='completed' AND r.label_config=?""", (label_config,))]
    ids.sort(key=lambda rid: hashlib.sha256(f"{seed}:{rid}".encode()).hexdigest())
    k = min(len(ids), max(math.ceil(fraction * len(ids)), min_n))
    return ids[:k]


def run(ctx, out_dir):
    cfg, v = ctx.cfg, ctx.cfg["verify"]
    conn = ctx.conn
    conn.executescript(SCHEMA)
    vc = verify_config(cfg)
    sample = sample_ids(conn, ctx.label_config, v["sample_fraction"], v["sample_seed"], v.get("min_sample", 20))
    done = {r[0] for r in conn.execute("SELECT review_id FROM cache.verify_preds WHERE verify_config=?", (vc,))}
    todo = [rid for rid in sample if rid not in done]
    texts = dict(conn.execute(f"SELECT review_id, review_text FROM source_rows WHERE review_id IN ({','.join('?' * len(todo))})",
                              todo).fetchall()) if todo else {}
    system = luna_labeler.system_prompt()
    failures = []
    for start in range(0, len(todo), v["batch_size"]):
        chunk = todo[start:start + v["batch_size"]]
        pending = {i + 1: rid for i, rid in enumerate(chunk)}
        for _ in range(cfg["limits"]["max_attempts_per_batch"]):
            if not pending:
                break
            items = [(i, texts[rid]) for i, rid in pending.items()]
            payload, err = ctx.luna_call("verify", "luna_relabel", v["model"], v["reasoning_effort"], system,
                                         luna_labeler.user_message(items), luna_labeler.SCHEMA, v["max_output_tokens"],
                                         list(pending.values()), label_config=vc)
            good, bad = luna_labeler.validate(payload, pending)
            with conn:
                for i, lab in good.items():
                    conn.execute("INSERT OR REPLACE INTO cache.verify_preds VALUES (?,?,?,?,?,?,?)",
                                 (pending[i], vc, ctx.run_id, lab["topic"], lab["intent"], lab["severity"], lab["sentiment"]))
            pending = {i: pending[i] for i in bad}
        failures += [{"review_id": rid, "reason": "verifier output invalid after retry"} for rid in pending.values()]
    report = compare(conn, ctx.label_config, vc, sample, out_dir)
    report["verifier_failures"] = failures
    common.write_json(out_dir / "verify_summary.json", report)
    ctx.recorder.event("verify", "end", sample=len(sample), compared=report["compared"], failures=len(failures))
    return report


def compare(conn, label_config, vc, sample, out_dir):
    rows = conn.execute(f"""
        SELECT r.review_id, s.review_text, l.topic, l.intent, l.severity, l.sentiment, l.needs_review,
               v.topic, v.intent, v.severity, v.sentiment
        FROM records r JOIN source_rows s USING(review_id)
        JOIN cache.labels l ON l.text_sha256 = s.text_sha256 AND l.label_config = r.label_config
        JOIN cache.verify_preds v ON v.review_id = r.review_id AND v.verify_config = ?
        WHERE r.review_id IN ({','.join('?' * len(sample))})""", [vc, *sample]).fetchall() if sample else []
    preds, disagreements = [], []
    agree = Counter()
    confusion = Counter()
    sev_abs = sent_abs = 0.0
    nr_hit = Counter()
    for rid, text, et, ei, es, esent, nr, vt, vi, vs, vsent in rows:
        rec = {"review_id": rid, "enrich": {"topic": et, "intent": ei, "severity": es, "sentiment": esent, "needs_review": bool(nr)},
               "verifier": {"topic": vt, "intent": vi, "severity": vs, "sentiment": vsent}}
        preds.append(rec)
        agree["topic"] += et == vt
        agree["intent"] += ei == vi
        agree["severity"] += es == vs
        agree["all3"] += et == vt and ei == vi and es == vs
        confusion[(et, vt)] += 1
        sev_abs += abs(es - vs)
        sent_abs += abs(esent - vsent)
        disagree = et != vt or ei != vi or abs(es - vs) >= 2
        nr_hit[(bool(nr), disagree)] += 1
        if et != vt or ei != vi or es != vs:
            disagreements.append({**rec, "text": text[:500], "fields": [f for f, a, b in (("topic", et, vt), ("intent", ei, vi),
                                                                                         ("severity", es, vs)) if a != b]})
    n = len(rows)
    common.write_jsonl(out_dir / "verifier_predictions.jsonl", preds)
    common.write_jsonl(out_dir / "disagreements.jsonl", disagreements)
    report = {
        "verify_config": vc, "sample_declared": len(sample), "compared": n,
        "agreement": {k: round(agree[k] / n, 4) if n else None for k in ("topic", "intent", "severity", "all3")},
        "severity_mae": round(sev_abs / n, 4) if n else None,
        "sentiment_mae": round(sent_abs / n, 4) if n else None,
        "topic_confusion_enrich_vs_verifier": {f"{a}->{b}": c for (a, b), c in sorted(confusion.items()) if a != b},
        "needs_review_vs_material_disagreement": {f"needs_review={a},disagree={b}": c for (a, b), c in sorted(nr_hit.items())},
        "disagreement_count": len(disagreements),
    }
    report["planted_error_test"] = planted_errors(preds, out_dir)
    return report


def planted_errors(preds, out_dir, k=20):
    """Synthetic test copy: take up to k verified records, deliberately corrupt the enrich label, and check
    whether the (blind) verifier prediction disagrees with the planted label. Never enters business data."""
    topics = list(labels.TOPICS)
    cases = []
    for rec in preds[:k]:
        true_topic = rec["enrich"]["topic"]
        wrong_topic = topics[(topics.index(true_topic) + 3) % len(topics)]
        wrong_sev = 5 if rec["enrich"]["severity"] <= 2 else 1
        detected = rec["verifier"]["topic"] != wrong_topic or abs(rec["verifier"]["severity"] - wrong_sev) >= 2
        cases.append({"synthetic": True, "review_id": rec["review_id"], "planted": {"topic": wrong_topic, "severity": wrong_sev},
                      "original": {"topic": true_topic, "severity": rec["enrich"]["severity"]},
                      "verifier": {"topic": rec["verifier"]["topic"], "severity": rec["verifier"]["severity"]},
                      "detected": detected})
    common.write_jsonl(out_dir / "planted_error_cases.jsonl", cases)
    return {"cases": len(cases), "detected": sum(c["detected"] for c in cases),
            "note": "synthetic copy with deliberately wrong topic/severity; excluded from all business aggregates"}
