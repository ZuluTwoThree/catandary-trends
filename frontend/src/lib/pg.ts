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
  var __catandaryPool: Pool | undefined;
}

function makePool(): Pool {
  const url = process.env.DATABASE_URL;
  const pool = url
    ? new Pool({ connectionString: url, max: 10 })
    : new Pool({ host: "/var/run/postgresql", database: "catandary", max: 10 });
  pool.on("error", (err) => console.error("pg pool error:", err.message));
  return pool;
}

export function getPool(): Pool {
  if (!globalThis.__catandaryPool) {
    globalThis.__catandaryPool = makePool();
  }
  return globalThis.__catandaryPool;
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
