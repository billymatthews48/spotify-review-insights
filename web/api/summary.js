// Overall metrics, computed from the processed records in Postgres.
import { sql, send, fail } from "./_db.js";

export default async function handler(req, res) {
  try {
    const [status, reasons, topics, severity, meta, reuse, needs] = await Promise.all([
      sql`SELECT status, COUNT(*)::int AS n, SUM(in_scope::int)::int AS in_scope FROM records GROUP BY status`,
      sql`SELECT reason, COUNT(*)::int AS n FROM records WHERE status = 'quarantined' GROUP BY reason ORDER BY n DESC`,
      sql`SELECT topic, intent, COUNT(*)::int AS n FROM records WHERE status = 'completed' GROUP BY topic, intent`,
      sql`SELECT severity, COUNT(*)::int AS n FROM records WHERE status = 'completed' GROUP BY severity ORDER BY severity`,
      sql`SELECT key, value FROM run_meta`,
      sql`SELECT COUNT(*)::int AS n FROM records WHERE status = 'completed' AND cache_source_id IS NOT NULL`,
      sql`SELECT COUNT(*)::int AS n, AVG(sentiment)::float AS avg_sentiment FROM records WHERE status = 'completed' AND needs_review`,
    ]);
    send(res, {
      status, quarantine_reasons: reasons, topic_intent: topics, severity,
      meta: Object.fromEntries(meta.map((r) => [r.key, r.value])),
      exact_text_reuse: reuse[0].n, needs_review: needs[0].n,
    });
  } catch (e) { fail(res, e); }
}
