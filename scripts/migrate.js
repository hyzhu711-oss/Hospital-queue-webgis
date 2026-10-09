"use strict";

require("dotenv").config();

const fs = require("fs");
const path = require("path");
const { Client } = require("pg");
const { createHash } = require("crypto");

async function migrate() {
  if (!process.env.DATABASE_URL) {
    throw new Error("DATABASE_URL is required to run migrations");
  }

  const client = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: process.env.DATABASE_SSL === "true" ? { rejectUnauthorized: false } : false,
    options: "-c search_path=public,extensions"
  });
  const migrationDirectory = path.join(__dirname, "..", "database", "migrations");
  const files = fs.readdirSync(migrationDirectory).filter((file) => file.endsWith(".sql")).sort();

  await client.connect();
  try {
    await client.query("SELECT pg_advisory_lock(714025)");
    await client.query("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())");
    const existing = await client.query("SELECT name,checksum FROM schema_migrations");
    const applied = new Map(existing.rows.map((row) => [row.name,row.checksum]));
    // Adopt the existing legacy schema without replaying seed upserts against an established deployment.
    const legacy = await client.query(`SELECT to_regclass('users') IS NOT NULL AND to_regclass('hospitals') IS NOT NULL
      AND to_regclass('reports') IS NOT NULL AND to_regclass('queue_lengths') IS NOT NULL
      AND to_regclass('hospital_latest_status') IS NOT NULL AND to_regclass('hospital_report_details') IS NOT NULL AS present`);
    for (const file of files) {
      const sql = fs.readFileSync(path.join(migrationDirectory,file),"utf8");
      const checksum = createHash("sha256").update(sql).digest("hex");
      if (applied.has(file)) {
        if (applied.get(file)!==checksum) throw new Error(`Applied migration changed: ${file}`);
        continue;
      }
      await client.query("BEGIN");
      try {
        await client.query("SET LOCAL search_path TO public,extensions");
        if (!(applied.size===0 && legacy.rows[0].present && ["001_init.sql","002_seed.sql"].includes(file))) {
      console.log(`Running ${file}`);
          await client.query(sql);
        } else { console.log(`Adopting legacy migration ${file}`); }
        await client.query("INSERT INTO schema_migrations(name,checksum) VALUES($1,$2)",[file,checksum]);
        await client.query("COMMIT");
      } catch(error) { await client.query("ROLLBACK"); throw error; }
    }
    console.log("Database migrations completed");
  } finally {
    await client.end();
  }
}

migrate().catch((error) => {
  console.error(error);
  process.exit(1);
});
