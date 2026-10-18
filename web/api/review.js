// Trace one review: its record, labels, cache provenance and issue membership.
import { sql, send, fail } from "./_db.js";

export default async function handler(req, res) {
  const id = String(req.query.id || "").trim();
  if (!/^[0-9a-f-]{36}$/i.test(id)) return send(res, { error: "expected a review_id (UUID)" }, 400);
  try {
    const [rec] = await sql`SELECT * FROM records WHERE review_id = ${id}`;
    if (!rec) return send(res, { error: "not found" }, 404);
    const issues = await sql`SELECT m.issue_id, i.name, r.rank FROM membership m JOIN issues i USING (issue_id)
                             LEFT JOIN ranking r USING (issue_id) WHERE m.review_id = ${id}`;
    send(res, { record: rec, issues });
  } catch (e) { fail(res, e); }
}
