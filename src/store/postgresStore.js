"use strict";

const { Pool } = require("pg");

function createPool() {
  const useSsl = process.env.DATABASE_SSL === "true";
  return new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: useSsl ? { rejectUnauthorized: false } : false,
    options: "-c search_path=public,extensions -c statement_timeout=5000"
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

function createPostgresStore({ pool: suppliedPool } = {}) {
  if (!suppliedPool && !process.env.DATABASE_URL) {
    throw new Error("DATABASE_URL is required when DATA_SOURCE=postgres");
  }

  const pool = suppliedPool || createPool();
  const hospitalSelect = `
    SELECT id, name, last_inspected, user_id, queue_length_id,
      queue_description, queue_colour, cleanliness, latest_report_at,
      ST_X(location) AS longitude, ST_Y(location) AS latitude
    FROM hospital_latest_status`;
  const toolHospitalSelect = `SELECT h.id,h.name,h.user_id,h.last_inspected,
    ST_X(h.location) AS longitude,ST_Y(h.location) AS latitude,
    r.id AS latest_report_id,r.created_at AS latest_report_at,r.cleanliness,
    r.cleanliness_score,r.queue_wait_minutes,q.id AS queue_length_id,
    COALESCE(q.description,'Unknown') AS queue_description,COALESCE(q.colour,'#6b7280') AS queue_colour,
    CASE WHEN $2::double precision IS NULL THEN NULL ELSE
      ST_Distance(h.location::geography,ST_SetSRID(ST_MakePoint($2,$3),4326)::geography) END AS distance_metres_raw
    FROM hospitals h LEFT JOIN LATERAL
      (SELECT * FROM reports WHERE hospital_id=h.id ORDER BY created_at DESC,id DESC LIMIT 1) r ON TRUE
    LEFT JOIN queue_lengths q ON q.id=r.queue_length_id`;
  const toolMap = (row) => ({...mapHospital(row),latestReportId:row.latest_report_id,
    cleanlinessScore:row.cleanliness_score==null?null:Number(row.cleanliness_score),
    queueWaitMinutes:row.queue_wait_minutes==null?null:Number(row.queue_wait_minutes),
    distanceMetresRaw:row.distance_metres_raw==null?null:Number(row.distance_metres_raw)});

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
          `INSERT INTO reports (hospital_id, user_id, queue_length_id, cleanliness, cleanliness_score, queue_wait_minutes)
         VALUES ($1, $2, $3, $4, $5, $6)
         RETURNING id, hospital_id AS "hospitalId", user_id AS "userId",
           queue_length_id AS "queueLengthId", cleanliness,
           created_at AS "createdAt"`,
        [input.hospitalId, input.userId, input.queueLengthId, input.cleanliness, input.cleanlinessScore ?? null, input.queueWaitMinutes ?? null]
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

    async toolReadSnapshot(callback) {
      const client = await pool.connect();
      try {
        await client.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY");
        const result = await callback(createPostgresStore({pool:client}));
        await client.query("COMMIT");
        return result;
      } catch (error) { await client.query("ROLLBACK"); throw error; }
      finally { client.release(); }
    },
    async toolResolveHospitals(query) {
      const result = await pool.query(`${toolHospitalSelect}
        WHERE lower(h.name)=lower($1) OR (strpos(lower(h.name),lower($1))>0
          AND NOT EXISTS(SELECT 1 FROM hospitals WHERE lower(name)=lower($1))) ORDER BY h.id LIMIT 201`,[query,null,null]);
      return result.rows.map(toolMap);
    },
    async toolGetHospitals(ids, origin) {
      const result=await pool.query(`${toolHospitalSelect} WHERE h.id=ANY($1::int[]) ORDER BY h.id`,[ids,origin?.longitude??null,origin?.latitude??null]);
      return result.rows.map(toolMap);
    },
    async toolSearchHospitals(input) {
      const result=await pool.query(`${toolHospitalSelect}
        WHERE ($1::double precision IS NULL OR ST_DWithin(h.location::geography,
          ST_SetSRID(ST_MakePoint($2,$3),4326)::geography,$1))
        ORDER BY distance_metres_raw,h.id LIMIT $4`,[input.radius_m??null,input.longitude,input.latitude,input.limit]);
      return result.rows.map(toolMap);
    },
    async toolGetReports(ids,start,end,limit) {
      const result=await pool.query(`SELECT id,hospital_id AS "hospitalId",user_id AS "userId",
        queue_length_id AS "queueLengthId",cleanliness,cleanliness_score AS "cleanlinessScore",
        queue_wait_minutes AS "queueWaitMinutes",created_at AS "createdAt"
        FROM reports WHERE hospital_id=ANY($1::int[]) AND created_at >= $2::timestamptz AND created_at < $3::timestamptz
        ORDER BY created_at DESC,id DESC LIMIT $4`,[ids,start,end,limit]);
      return result.rows.map((r)=>({...r,createdAt:new Date(r.createdAt).toISOString(),cleanlinessScore:r.cleanlinessScore==null?null:Number(r.cleanlinessScore),queueWaitMinutes:r.queueWaitMinutes==null?null:Number(r.queueWaitMinutes)}));
    },
    async toolStatistics(ids,start,end) {
      const result=await pool.query(`SELECT h.id AS hospital_id,COUNT(r.id)::int AS report_count,
        COUNT(r.id) FILTER(WHERE q.sort_order>0)::int AS known_queue_count,
        AVG(q.sort_order) FILTER(WHERE q.sort_order>0) AS average_queue_severity,
        COUNT(r.queue_wait_minutes)::int AS observed_wait_count,AVG(r.queue_wait_minutes) AS average_wait_minutes,
        COUNT(r.cleanliness_score)::int AS cleanliness_count,AVG(r.cleanliness_score) AS average_cleanliness,
        MIN(r.cleanliness_score) AS min_cleanliness,MAX(r.cleanliness_score) AS max_cleanliness,
        MIN(r.created_at) AS first_report_at,MAX(r.created_at) AS last_report_at,
        (array_agg(NULLIF(q.sort_order,0) ORDER BY r.created_at,r.id))[1] AS first_queue_severity,
        (array_agg(NULLIF(q.sort_order,0) ORDER BY r.created_at DESC,r.id DESC))[1] AS last_queue_severity,
        (array_agg(r.id ORDER BY r.created_at,r.id) FILTER(WHERE r.id IS NOT NULL))[1:200] AS report_ids,
        COUNT(r.id)<=200 AS report_ids_complete
        FROM hospitals h LEFT JOIN reports r ON r.hospital_id=h.id AND r.created_at >= $2::timestamptz AND r.created_at < $3::timestamptz
        LEFT JOIN queue_lengths q ON q.id=r.queue_length_id WHERE h.id=ANY($1::int[]) GROUP BY h.id ORDER BY h.id`,[ids,start,end]);
      const numeric=["average_queue_severity","average_wait_minutes","average_cleanliness","min_cleanliness","max_cleanliness"];
      return result.rows.map((r)=>{for(const key of numeric)r[key]=r[key]==null?null:Number(r[key]); for(const key of ["first_report_at","last_report_at"])r[key]=r[key]?new Date(r[key]).toISOString():null;r.report_ids=r.report_ids||[];return r;});
    },
    async close() {
      await pool.end();
    }
  };
}

module.exports = { createPostgresStore };
