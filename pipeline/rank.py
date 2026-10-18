"""Stage 5 - Rank. Pure code, no model: recomputes the baseline ranking from saved records + membership.

priority_score(issue) = complaint_count x mean_severity = severity_sum (integer arithmetic, no rounding loss).
Order: descending score, then ascending issue_id. Means: six decimals, decimal half-up.
Re-running on the same saved inputs gives byte-identical outputs.
"""

import csv
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path


def mean6(total, n):
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def compute(records, membership):
    """records: {review_id: {"intent", "severity", ...}} completed records; membership: [(issue_id, review_id)].
    Returns ranking rows. Only complaint/cancellation records count; each (issue, review) pair once."""
    members = defaultdict(set)
    for iid, rid in membership:
        rec = records.get(rid)
        if rec and rec["intent"] in ("complaint", "cancellation"):
            members[iid].add(rid)
    rows = []
    for iid, rids in members.items():
        sev = sum(records[r]["severity"] for r in rids)
        rows.append({"issue_id": iid, "complaint_count": len(rids), "severity_sum": sev,
                     "mean_severity": mean6(sev, len(rids)), "priority_score": sev})
    rows.sort(key=lambda r: (-r["priority_score"], r["issue_id"]))
    for n, r in enumerate(rows, 1):
        r["rank"] = n
    return rows


def write_ranking(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r[c] for c in cols})


def load_from_db(conn, label_config, group_config):
    records = {r[0]: {"intent": r[1], "severity": r[2], "topic": r[3], "month": r[4], "cancel": r[1] == "cancellation"}
               for r in conn.execute("""
        SELECT r.review_id, l.intent, l.severity, l.topic, substr(s.review_timestamp, 1, 7)
        FROM records r JOIN source_rows s USING(review_id)
        JOIN cache.labels l ON l.text_sha256 = s.text_sha256 AND l.label_config = r.label_config
        WHERE r.status = 'completed' AND r.label_config = ?""", (label_config,))}
    membership = [tuple(r) for r in conn.execute(
        "SELECT issue_id, review_id FROM membership WHERE group_config = ? ORDER BY issue_id, review_id", (group_config,))]
    return records, membership


def aggregates(conn, label_config, group_config, rows):
    """Extra per-issue and per-topic context for the memo/dashboard (not part of the baseline score)."""
    info = {r[0]: r[1:] for r in conn.execute("SELECT issue_id, topic, name, definition FROM cache.issues WHERE group_config=?",
                                              (group_config,))}
    extra = {r[0]: r[1:] for r in conn.execute("""
        SELECT m.issue_id, SUM(l.intent = 'cancellation'), SUM(l.severity >= 4), SUM(l.needs_review)
        FROM membership m JOIN source_rows s ON s.review_id = m.review_id
        JOIN records r ON r.review_id = m.review_id
        JOIN cache.labels l ON l.text_sha256 = s.text_sha256 AND l.label_config = r.label_config
        WHERE m.group_config = ? GROUP BY m.issue_id""", (group_config,))}
    out = []
    for r in rows:
        topic, name, definition = info.get(r["issue_id"], ("", "", ""))
        cancels, blocked, needs_review = extra.get(r["issue_id"], (0, 0, 0))
        out.append({**r, "topic": topic, "name": name, "definition": definition, "cancellation_count": cancels,
                    "severity_4plus_count": blocked, "needs_review_count": needs_review})
    return out


def run(ctx, out_dir, group_config):
    records, membership = load_from_db(ctx.conn, ctx.label_config, group_config)
    rows = compute(records, membership)
    write_ranking(rows, out_dir / "ranking.csv")
    agg = aggregates(ctx.conn, ctx.label_config, group_config, rows)
    cols = ["rank", "issue_id", "topic", "name", "complaint_count", "severity_sum", "mean_severity", "priority_score",
            "cancellation_count", "severity_4plus_count", "needs_review_count", "definition"]
    with (out_dir / "aggregates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in agg:
            w.writerow({c: r[c] for c in cols})
    with (out_dir / "membership.csv").open("w", newline="", encoding="utf-8") as f:
        f.write("issue_id,review_id\n")
        for iid, rid in membership:
            f.write(f"{iid},{rid}\n")
    ctx.recorder.event("rank", "end", issues=len(rows), memberships=len(membership))
    return agg
