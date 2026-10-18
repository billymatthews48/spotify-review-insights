// AI-generated recommendation (memo role output, saved by the pipeline) with live claim checks:
// every claim value is re-compared with the ranking table on each request.
import { sql, send, fail } from "./_db.js";

export default async function handler(req, res) {
  try {
    const [memo] = await sql`SELECT * FROM memo WHERE id = 1`;
    if (!memo) return send(res, { error: "no memo published" }, 404);
    const claims = await sql`
      SELECT c.claim_id, c.issue_id, c.metric, c.value, i.name,
             CASE c.metric WHEN 'complaint_count' THEN r.complaint_count::text WHEN 'severity_sum' THEN r.severity_sum::text
                           WHEN 'mean_severity' THEN r.mean_severity WHEN 'priority_score' THEN r.priority_score::text END AS saved_value
      FROM claims c LEFT JOIN ranking r USING (issue_id) LEFT JOIN issues i USING (issue_id) ORDER BY c.claim_id`;
    const ids = memo.evidence_review_ids || [];
    const evidence = ids.length
      ? await sql`SELECT review_id, evidence_quote, severity, intent, topic, review_month FROM records WHERE review_id = ANY(${ids})`
      : [];
    send(res, { memo, claims: claims.map((c) => ({ ...c, matches: c.value === c.saved_value })), evidence });
  } catch (e) { fail(res, e); }
}
