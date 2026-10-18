// Monthly classified volume and complaints by topic (first and last months are partial).
import { sql, send, fail } from "./_db.js";

export default async function handler(req, res) {
  try {
    send(res, await sql`SELECT month, topic, classified, complaints, severity_sum FROM monthly ORDER BY month, topic`);
  } catch (e) { fail(res, e); }
}
