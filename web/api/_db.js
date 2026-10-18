// Server-side only: DATABASE_URL lives in Vercel env vars, never in browser code.
import { neon } from "@neondatabase/serverless";

export const sql = neon(process.env.DATABASE_URL);

export function send(res, data, status = 200) {
  res.setHeader("Cache-Control", "public, s-maxage=300, stale-while-revalidate=600");
  res.status(status).json(data);
}

export function fail(res, err) {
  console.error(err);
  res.status(500).json({ error: "database query failed" });
}
