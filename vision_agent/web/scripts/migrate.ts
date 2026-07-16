import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { Pool } from "@neondatabase/serverless";

async function main() {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) throw new Error("DATABASE_URL is required");
  const migration = await readFile(join(process.cwd(), "migrations", "0001_atlas_foundation.sql"), "utf8");
  const pool = new Pool({ connectionString });
  try {
    await pool.query(migration);
    console.log("Applied 0001_atlas_foundation.sql");
  } finally {
    await pool.end();
  }
}

void main();
