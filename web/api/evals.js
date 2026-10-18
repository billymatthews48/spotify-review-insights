// Saved evaluation evidence: golden set, independent verifier, system tests, cost report.
import { sql, send, fail } from "./_db.js";

export default async function handler(req, res) {
  try {
    const rows = await sql`SELECT name, payload FROM evals`;
    send(res, Object.fromEntries(rows.map((r) => [r.name, r.payload])));
  } catch (e) { fail(res, e); }
}
