import {
  Pool,
  neon,
  type NeonQueryFunction,
  type PoolClient,
} from "@neondatabase/serverless";

let queryClient: NeonQueryFunction<false, false> | null = null;

export function sql() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is required for persistent ATLAS operations");
  queryClient ??= neon(url);
  return queryClient;
}

export async function withTransaction<T>(work: (client: PoolClient) => Promise<T>): Promise<T> {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is required for persistent ATLAS operations");
  const pool = new Pool({ connectionString: url });
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const result = await work(client);
    await client.query("COMMIT");
    return result;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
    await pool.end();
  }
}
