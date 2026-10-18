// Baseline issue ranking (priority_score = complaint_count x mean_severity) with issue names.
import { sql, send, fail } from "./_db.js";

export default async function handler(req, res) {
  try {
    const rows = await sql`
      SELECT r.*, i.topic, i.name, i.definition, i.source
      FROM ranking r JOIN issues i USING (issue_id) ORDER BY r.rank`;
    send(res, rows);
  } catch (e) { fail(res, e); }
}
