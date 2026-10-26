"use strict";

require("dotenv").config();

const fs = require("fs");
const path = require("path");
const { Client } = require("pg");

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
    for (const file of files) {
      console.log(`Running ${file}`);
      await client.query(fs.readFileSync(path.join(migrationDirectory, file), "utf8"));
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
