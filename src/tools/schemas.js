"use strict";

const id = { type: "integer", minimum: 1, maximum: 2147483647 };
const ids = { type: "array", items: id, minItems: 1, maxItems: 200, uniqueItems: true };
const latitude = { type: "number", minimum: -90, maximum: 90 };
const longitude = { type: "number", minimum: -180, maximum: 180 };
const time = { type: "string", format: "date-time" };
const window = { start_time: time, end_time: time };
const object = (properties, required) => ({ type: "object", properties, required, additionalProperties: false });
const point = { latitude, longitude };
const descriptions = {
  resolve_hospitals: "Resolve an exact or partial hospital name. Multiple matches require clarification.",
  search_nearby_hospitals: "Compute geodesic distances; optional radius in metres. complete=false means truncated candidates.",
  get_hospital_details: "Get authoritative latest reported status, location and source report ID.",
  get_hospital_reports: "Get bounded reports in the explicit UTC half-open time window [start,end).",
  get_queue_statistics: "Aggregate queue severity categories and actual reported wait minutes separately.",
  get_cleanliness_statistics: "Aggregate explicit 1–5 scores. Text observations never become ratings.",
  compare_hospitals: "Compare batch hospital metrics within the same time window.",
  rank_hospitals: "Filter all supplied candidates before weighted ranking; missing weighted metrics are excluded."
};
const inputs = {
  resolve_hospitals: object({ query: { type: "string", minLength: 1, maxLength: 100 } }, ["query"]),
  search_nearby_hospitals: object({ ...point, radius_m: { type: "number", exclusiveMinimum: 0, maximum: 100000 }, limit: { type: "integer", minimum: 1, maximum: 200 } }, ["latitude", "longitude"]),
  get_hospital_details: object({ hospital_id: id }, ["hospital_id"]),
  get_hospital_reports: object({ hospital_id: id, ...window, limit: { type: "integer", minimum: 1, maximum: 200 } }, ["hospital_id", "start_time", "end_time"]),
  get_queue_statistics: object({ hospital_id: id, ...window }, ["hospital_id", "start_time", "end_time"]),
  get_cleanliness_statistics: object({ hospital_id: id, ...window }, ["hospital_id", "start_time", "end_time"]),
  compare_hospitals: object({ hospital_ids: ids, ...window }, ["hospital_ids", "start_time", "end_time"]),
  rank_hospitals: object({
    candidate_ids: ids, ...point, ...window,
    radius_m: { type: "number", exclusiveMinimum: 0, maximum: 100000 },
    min_cleanliness: { type: "number", minimum: 1, maximum: 5 },
    max_queue_severity: { type: "number", minimum: 1, maximum: 5 },
    max_wait_minutes: { type: "number", minimum: 0, maximum: 1440 },
    distance_weight: { type: "number", minimum: 0, maximum: 1 },
    queue_weight: { type: "number", minimum: 0, maximum: 1 },
    cleanliness_weight: { type: "number", minimum: 0, maximum: 1 },
    limit: { type: "integer", minimum: 1, maximum: 20 }
  }, ["candidate_ids", "latitude", "longitude", "start_time", "end_time", "distance_weight", "queue_weight", "cleanliness_weight"])
};
const hospital = object({
  hospital_id: id, name: { type: "string" }, latitude, longitude,
  distance_m: { type: ["number", "null"], minimum: 0 },
  queue_description: { type: "string" }, cleanliness_note: { type: "string" },
  latest_report_id: { ...id, type: ["integer", "null"] },
  latest_report_at: { type: ["string", "null"] },
  cleanliness_score: { type: ["number", "null"], minimum: 1, maximum: 5 },
  queue_wait_minutes: { type: ["number", "null"], minimum: 0, maximum: 1440 }
}, ["hospital_id", "name", "latitude", "longitude", "distance_m", "queue_description", "cleanliness_note", "latest_report_id", "latest_report_at", "cleanliness_score", "queue_wait_minutes"]);
const nullableNumber = { type: ["number", "null"] };
const stats = object({
  hospital_id: id,
  report_count: { type: "integer", minimum: 0 }, known_queue_count: { type: "integer", minimum: 0 },
  average_queue_severity: nullableNumber, observed_wait_count: { type: "integer", minimum: 0 },
  average_wait_minutes: nullableNumber, cleanliness_count: { type: "integer", minimum: 0 },
  average_cleanliness: nullableNumber, min_cleanliness: nullableNumber, max_cleanliness: nullableNumber,
  first_report_at: { type: ["string", "null"] }, last_report_at: { type: ["string", "null"] },
  first_queue_severity: nullableNumber, last_queue_severity: nullableNumber,
  report_ids: { type: "array", items: id, maxItems: 200, uniqueItems: true }, report_ids_complete: { type: "boolean" }
}, ["hospital_id", "report_count", "known_queue_count", "average_queue_severity", "observed_wait_count", "average_wait_minutes", "cleanliness_count", "average_cleanliness", "min_cleanliness", "max_cleanliness", "first_report_at", "last_report_at", "first_queue_severity", "last_queue_severity", "report_ids", "report_ids_complete"]);
const outputs = {
  resolve_hospitals: object({ hospitals: { type: "array", items: hospital }, complete: { type: "boolean" } }, ["hospitals", "complete"]),
  search_nearby_hospitals: object({ hospitals: { type: "array", items: hospital }, complete: { type: "boolean" } }, ["hospitals", "complete"]),
  get_hospital_details: hospital,
  get_hospital_reports: object({ reports: { type: "array", items: object({
    report_id: id, hospital_id: id, user_id: id, queue_length_id: id,
    cleanliness_note: {type:"string"}, cleanliness_score:{type:["number","null"],minimum:1,maximum:5},
    queue_wait_minutes:{type:["number","null"],minimum:0,maximum:1440}, created_at:time
  },["report_id","hospital_id","user_id","queue_length_id","cleanliness_note","cleanliness_score","queue_wait_minutes","created_at"]) }, complete: { type: "boolean" } }, ["reports", "complete"]),
  get_queue_statistics: stats,
  get_cleanliness_statistics: stats,
  compare_hospitals: object({ hospitals: { type: "array", items: hospital }, statistics: { type: "array", items: stats } }, ["hospitals", "statistics"]),
  rank_hospitals: object({
    hospitals: { type: "array", items: hospital }, statistics: { type: "array", items: stats },
    candidate_hospitals: { type: "array", items: hospital },
    ranking: { type: "array", items: object({ hospital_id: id, score: { type: "number", minimum: 0, maximum: 1 }, rank: { type: "integer", minimum: 1 } }, ["hospital_id", "score", "rank"]) },
    excluded_ids: { type: "array", items: id }, algorithm: { const: "weighted-cost-v1" }, distance_scale_m: { type: "number", exclusiveMinimum: 0 }
  }, ["candidate_hospitals", "hospitals", "statistics", "ranking", "excluded_ids", "algorithm", "distance_scale_m"])
};

module.exports = { inputs, outputs, descriptions };
