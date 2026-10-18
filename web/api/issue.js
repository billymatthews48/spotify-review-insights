// One issue: definition, numbers, monthly volume and member reviews (traceable by review_id).
import { sql, send, fail } from "./_db.js";

export default async function handler(req, res) {
  const id = String(req.query.id || "");
  if (!/^[A-Z]{3}-\d{2}$/.test(id)) return send(res, { error: "bad issue id" }, 400);
  try {
    const [issue, months, reviews] = await Promise.all([
      sql`SELECT r.*, i.topic, i.name, i.definition FROM ranking r JOIN issues i USING (issue_id) WHERE issue_id = ${id}`,
      sql`SELECT rc.review_month AS month, COUNT(*)::int AS n FROM membership m JOIN records rc USING (review_id)
          WHERE m.issue_id = ${id} GROUP BY 1 ORDER BY 1`,
      sql`SELECT rc.review_id, rc.review_text, rc.evidence_quote, rc.severity, rc.intent, rc.review_month,
                 rc.review_likes, rc.needs_review, rc.cache_source_id
          FROM membership m JOIN records rc USING (review_id)
          WHERE m.issue_id = ${id} AND rc.cache_source_id IS NULL
          ORDER BY rc.review_likes DESC NULLS LAST, rc.review_id LIMIT 25`,
    ]);
    if (!issue.length) return send(res, { error: "not found" }, 404);
    send(res, { issue: issue[0], months, reviews });
  } catch (e) { fail(res, e); }
}
