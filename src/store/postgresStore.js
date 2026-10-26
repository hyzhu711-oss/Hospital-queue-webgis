"use strict";

const { Pool } = require("pg");

function createPool() {
  const useSsl = process.env.DATABASE_SSL === "true";
  return new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: useSsl ? { rejectUnauthorized: false } : false,
    options: "-c search_path=public,extensions"
  });
}

function mapHospital(row) {
  return {
    id: row.id,
    name: row.name,
    lastInspected: row.last_inspected,
    longitude: Number(row.longitude),
    latitude: Number(row.latitude),
    userId: row.user_id,
    queueLengthId: row.queue_length_id,
    queueDescription: row.queue_description,
    queueColour: row.queue_colour,
    cleanliness: row.cleanliness,
    latestReportAt: row.latest_report_at,
    distanceMetres: row.distance_metres == null ? undefined : Math.round(row.distance_metres)
  };
}

function createPostgresStore() {
  if (!process.env.DATABASE_URL) {
    throw new Error("DATABASE_URL is required when DATA_SOURCE=postgres");
  }

  const pool = createPool();
  const hospitalSelect = `
    SELECT id, name, last_inspected, user_id, queue_length_id,
      queue_description, queue_colour, cleanliness, latest_report_at,
      ST_X(location) AS longitude, ST_Y(location) AS latitude
    FROM hospital_latest_status`;

  return {
    mode: "postgres",

    async healthCheck() {
      await pool.query("SELECT 1");
      return { status: "ok", dataSource: "postgres" };
    },

    async getUser(userId) {
      const result = await pool.query(
        "SELECT id, display_name AS name FROM users WHERE id = $1",
        [userId]
      );
      return result.rows[0] || null;
    },

    async listQueueLengths() {
      const result = await pool.query(
        `SELECT id, description, colour, sort_order AS "sortOrder"
         FROM queue_lengths ORDER BY sort_order`
      );
      return result.rows;
    },

    async listHospitalsByUser(userId) {
      const result = await pool.query(`${hospitalSelect} WHERE user_id = $1 ORDER BY name`, [userId]);
      return result.rows.map(mapHospital);
    },

    async listNearestHospitals(latitude, longitude, limit = 5) {
      const result = await pool.query(
        `SELECT id, name, last_inspected, user_id, queue_length_id,
          queue_description, queue_colour, cleanliness, latest_report_at,
          ST_X(location) AS longitude, ST_Y(location) AS latitude,
          ST_DistanceSphere(
            location,
            ST_SetSRID(ST_MakePoint($1, $2), 4326)
          ) AS distance_metres
         FROM hospital_latest_status
         ORDER BY distance_metres
         LIMIT $3`,
        [longitude, latitude, limit]
      );
      return result.rows.map(mapHospital);
    },

    async listUnknownHospitals(userId) {
      const result = await pool.query(
        `${hospitalSelect} WHERE user_id = $1 AND queue_description = 'Unknown' ORDER BY name`,
        [userId]
      );
      return result.rows.map(mapHospital);
    },

    async getQueueSummary(userId) {
      const result = await pool.query(
        `SELECT q.id AS "queueLengthId", q.description, q.colour,
          COUNT(h.id)::int AS count
         FROM queue_lengths q
         LEFT JOIN hospital_latest_status h
           ON h.queue_length_id = q.id AND h.user_id = $1
         GROUP BY q.id, q.description, q.colour, q.sort_order
         ORDER BY q.sort_order`,
        [userId]
      );
      return result.rows;
    },

    async listReportsForHospital(hospitalId) {
      const result = await pool.query(
        `SELECT r.id, r.hospital_id AS "hospitalId", r.user_id AS "userId",
          r.queue_length_id AS "queueLengthId", r.cleanliness,
          r.created_at AS "createdAt", q.description AS "queueDescription",
          q.colour AS "queueColour", u.display_name AS "contributorName"
         FROM reports r
         JOIN queue_lengths q ON q.id = r.queue_length_id
         JOIN users u ON u.id = r.user_id
         WHERE r.hospital_id = $1
         ORDER BY r.created_at DESC`,
        [hospitalId]
      );
      return result.rows;
    },

    async getUserActivity(userId) {
      const result = await pool.query(
        `WITH counts AS (
           SELECT u.id, COUNT(r.id)::int AS report_count
           FROM users u LEFT JOIN reports r ON r.user_id = u.id
           GROUP BY u.id
         ), ranked AS (
           SELECT id, report_count,
             RANK() OVER (ORDER BY report_count DESC)::int AS rank
           FROM counts
         )
         SELECT report_count AS "reportCount", rank
         FROM ranked WHERE id = $1`,
        [userId]
      );
      return result.rows[0] || { reportCount: 0, rank: 1 };
    },

    async insertHospital(input) {
      const client = await pool.connect();
      try {
        await client.query("BEGIN");
        const hospitalResult = await client.query(
          `INSERT INTO hospitals (name, last_inspected, location, user_id)
           VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326), $5)
           RETURNING id`,
          [input.name, input.lastInspected, input.longitude, input.latitude, input.userId]
        );
        const hospitalId = hospitalResult.rows[0].id;
        await client.query(
          `INSERT INTO reports (hospital_id, user_id, queue_length_id, cleanliness)
           SELECT $1, $2, id, 'No report yet'
           FROM queue_lengths WHERE description = 'Unknown'`,
          [hospitalId, input.userId]
        );
        await client.query("COMMIT");
        const result = await pool.query(`${hospitalSelect} WHERE id = $1`, [hospitalId]);
        return mapHospital(result.rows[0]);
      } catch (error) {
        await client.query("ROLLBACK");
        throw error;
      } finally {
        client.release();
      }
    },

    async insertReport(input) {
      const previousResult = await pool.query(
        `SELECT q.description
         FROM reports r JOIN queue_lengths q ON q.id = r.queue_length_id
         WHERE r.hospital_id = $1 ORDER BY r.created_at DESC LIMIT 1`,
        [input.hospitalId]
      );
      const result = await pool.query(
        `INSERT INTO reports (hospital_id, user_id, queue_length_id, cleanliness)
         VALUES ($1, $2, $3, $4)
         RETURNING id, hospital_id AS "hospitalId", user_id AS "userId",
           queue_length_id AS "queueLengthId", cleanliness,
           created_at AS "createdAt"`,
        [input.hospitalId, input.userId, input.queueLengthId, input.cleanliness]
      );
      const queueResult = await pool.query(
        "SELECT description, colour FROM queue_lengths WHERE id = $1",
        [input.queueLengthId]
      );

      return {
        report: {
          ...result.rows[0],
          queueDescription: queueResult.rows[0].description,
          queueColour: queueResult.rows[0].colour
        },
        previousQueueDescription: previousResult.rows[0]?.description || "Unknown"
      };
    },

    async close() {
      await pool.end();
    }
  };
}

module.exports = { createPostgresStore };
