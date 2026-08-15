import { Pool, PoolClient } from "pg";

/**
 * PostgreSQL connection pool (singleton per server process).
 *
 * Connects via DATABASE_URL when set, otherwise over the local unix socket
 * (peer auth) to the `catandary` DB — mirrors the pipeline's pipeline/db.py.
 * Survives Next.js dev-mode HMR via globalThis stashing.
 */
declare global {
  // `var` is required for a global augmentation (let/const don't create globals).
  var __catandaryPoolV2: Pool | undefined;
}

function makePool(): Pool {
  const url = process.env.DATABASE_URL;
  // statement_timeout: Seiten-Queries dürfen nie zu Zombies werden. Ein vom
  // Client abgebrochener Request (Browser weg, curl-Timeout) lässt die
  // Postgres-Query sonst weiterlaufen — auf dem 45M-Korpus liefen so 8-Minuten-
  // Geister, die alle nachfolgenden Anfragen ausbremsten (#80, 2026-08-15).
  // 20s ist weit über jedem legitimen Seiten-Query (Ziel < 2s) und weit unter
  // Schaden. Gilt nur für Frontend-Verbindungen — Pipeline/Scripts haben
  // eigene Verbindungen ohne Limit.
  const common = { max: 10, statement_timeout: 20_000 };
  const pool = url
    ? new Pool({ connectionString: url, ...common })
    : new Pool({ host: "/var/run/postgresql", database: "catandary", ...common });
  pool.on("error", (err) => console.error("pg pool error:", err.message));
  return pool;
}

export function getPool(): Pool {
  if (!globalThis.__catandaryPoolV2) {
    globalThis.__catandaryPoolV2 = makePool();
  }
  return globalThis.__catandaryPoolV2;
}

/** Query helper: rows only. */
export async function q<T = Record<string, unknown>>(
  text: string,
  params: unknown[] = []
): Promise<T[]> {
  const res = await getPool().query(text, params as never[]);
  return res.rows as T[];
}

/** Query helper: first row or null. */
export async function q1<T = Record<string, unknown>>(
  text: string,
  params: unknown[] = []
): Promise<T | null> {
  const rows = await q<T>(text, params);
  return rows[0] ?? null;
}

/**
 * Run `fn` inside a single BEGIN/COMMIT transaction on one pooled client. On any
 * throw the transaction is rolled back (so partial writes never persist) and the
 * error re-thrown; the client is always released. Use this when several writes
 * must be all-or-nothing — e.g. consuming a magic token AND upserting its user,
 * where a burnt token with no user would lock the address out permanently.
 */
export async function withTransaction<T>(
  fn: (client: PoolClient) => Promise<T>
): Promise<T> {
  const client = await getPool().connect();
  try {
    await client.query("BEGIN");
    const result = await fn(client);
    await client.query("COMMIT");
    return result;
  } catch (e) {
    try {
      await client.query("ROLLBACK");
    } catch {
      // rollback itself failed (e.g. broken connection) — the original error matters
    }
    throw e;
  } finally {
    client.release();
  }
}
