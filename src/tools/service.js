"use strict";

const Ajv = require("ajv");
const { randomUUID } = require("crypto");
const { inputs, outputs, descriptions } = require("./schemas");
const ajv = new Ajv({ strict: true, allowUnionTypes: true, allErrors: true, coerceTypes: false });
ajv.addFormat("date-time", (value) => {
  const match=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.exec(value);
  if(!match||!Number.isFinite(Date.parse(value)))return false;
  const [year,month,day,hour,minute,second]=match.slice(1).map(Number);
  const calendar=new Date(`${match[1]}-${match[2]}-${match[3]}T00:00:00Z`);
  return calendar.getUTCFullYear()===year&&calendar.getUTCMonth()+1===month&&calendar.getUTCDate()===day&&hour<24&&minute<60&&second<60;
});
const validators = Object.fromEntries(Object.entries(inputs).map(([name, schema]) => [name, ajv.compile(schema)]));
const outputValidators = Object.fromEntries(Object.entries(outputs).map(([name, schema]) => [name, ajv.compile(schema)]));
function toolError(code, message, status = 400) { return Object.assign(new Error(message), { code, status }); }
function hospitalDto(h) {
  return {
    hospital_id: h.id, name: h.name, latitude: Number(h.latitude), longitude: Number(h.longitude),
    distance_m: h.distanceMetresRaw ?? null, queue_description: h.queueDescription || "Unknown",
    cleanliness_note: h.cleanliness || "No report yet", latest_report_id: h.latestReportId ?? null,
    latest_report_at: h.latestReportAt ? new Date(h.latestReportAt).toISOString() : null,
    cleanliness_score: h.cleanlinessScore ?? null, queue_wait_minutes: h.queueWaitMinutes ?? null
  };
}
function catalog() {
  return { version: "1.0", tools: Object.entries(inputs).map(([name, input_schema]) => ({ name, description: descriptions[name], input_schema, output_schema: outputs[name] })) };
}
function validateArguments(name, args) {
  if (!validators[name]) throw toolError("unknown_tool", "Unknown GIS tool", 404);
  if (!validators[name](args)) throw toolError("invalid_arguments", ajv.errorsText(validators[name].errors));
  if (args.start_time) {
    const span = Date.parse(args.end_time) - Date.parse(args.start_time);
    if (!(span > 0 && span <= 366 * 86400000)) throw toolError("invalid_window", "Time window must be positive and at most 366 days");
  }
  if (name === "resolve_hospitals" && !args.query.trim()) throw toolError("invalid_arguments", "Hospital name cannot be blank");
  if (name === "rank_hospitals" && Math.abs(args.distance_weight + args.queue_weight + args.cleanliness_weight - 1) > 1e-9) throw toolError("invalid_weights", "Weights must sum to one");
}
async function ensureHospitals(store, ids, origin) {
  const hospitals = await store.toolGetHospitals(ids, origin);
  if (hospitals.length !== ids.length) throw toolError("hospital_not_found", "One or more hospital IDs do not exist", 404);
  return hospitals;
}
async function runTool(store, name, args) {
  if (name === "resolve_hospitals") {
    const rows = await store.toolResolveHospitals(args.query.trim());
    return { hospitals: rows.slice(0, 200).map(hospitalDto), complete: rows.length <= 200 };
  }
  if (name === "search_nearby_hospitals") {
    const limit = args.limit ?? 200;
    const rows = await store.toolSearchHospitals({ ...args, limit: limit + 1 });
    return { hospitals: rows.slice(0, limit).map(hospitalDto), complete: rows.length <= limit };
  }
  const ids = args.hospital_ids || args.candidate_ids || [args.hospital_id];
  const hospitals = await ensureHospitals(store, ids, name === "rank_hospitals" ? args : undefined);
  if (name === "get_hospital_details") return hospitalDto(hospitals[0]);
  if (name === "get_hospital_reports") {
    const limit = args.limit ?? 200;
    const reports = await store.toolGetReports(ids, args.start_time, args.end_time, limit + 1);
    return { reports: reports.slice(0, limit).map((r)=>({report_id:r.id,hospital_id:r.hospitalId,user_id:r.userId,
      queue_length_id:r.queueLengthId,cleanliness_note:r.cleanliness,cleanliness_score:r.cleanlinessScore??null,
      queue_wait_minutes:r.queueWaitMinutes??null,created_at:new Date(r.createdAt).toISOString()})), complete: reports.length <= limit };
  }
  const stats = await store.toolStatistics(ids, args.start_time, args.end_time);
  if (name === "get_queue_statistics" || name === "get_cleanliness_statistics") return stats[0];
  if (name === "compare_hospitals") return { hospitals: hospitals.map(hospitalDto), statistics: stats };
  const byId = new Map(stats.map((s) => [s.hospital_id, s]));
  const scale = args.radius_m ?? 5000;
  const eligible = [], excluded = [];
  for (const h of hospitals) {
    const s = byId.get(h.id), d = h.distanceMetresRaw;
    const missing = (args.queue_weight > 0 && s.average_queue_severity == null) || (args.cleanliness_weight > 0 && s.average_cleanliness == null);
    const filtered = (args.radius_m !== undefined && d > args.radius_m) ||
      (args.min_cleanliness !== undefined && (s.average_cleanliness == null || s.average_cleanliness < args.min_cleanliness)) ||
      (args.max_queue_severity !== undefined && (s.average_queue_severity == null || s.average_queue_severity > args.max_queue_severity)) ||
      (args.max_wait_minutes !== undefined && (s.average_wait_minutes == null || s.average_wait_minutes > args.max_wait_minutes));
    if (missing || filtered) { excluded.push(h.id); continue; }
    const score = args.distance_weight * Math.min(d / scale, 1) +
      args.queue_weight * ((s.average_queue_severity ?? 1) - 1) / 4 +
      args.cleanliness_weight * (5 - (s.average_cleanliness ?? 5)) / 4;
    eligible.push({ hospital_id: h.id, score });
  }
  eligible.sort((a, b) => a.score - b.score || a.hospital_id - b.hospital_id);
  const ranking = eligible.slice(0, args.limit ?? 3).map((r, i) => ({ ...r, rank: i + 1 }));
  return { candidate_hospitals:hospitals.map(hospitalDto), hospitals: ranking.map((r) => hospitalDto(hospitals.find((h) => h.id === r.hospital_id))), statistics: stats, ranking, excluded_ids: excluded, algorithm: "weighted-cost-v1", distance_scale_m: scale };
}
async function executeTool(store, name, args) {
  validateArguments(name, args);
  const started = Date.now(), requestId = randomUUID();
  const data = store.toolReadSnapshot ? await store.toolReadSnapshot((snapshot) => runTool(snapshot, name, args)) : await runTool(store, name, args);
  if (!outputValidators[name](data)) throw toolError("invalid_tool_output", "GIS tool returned an invalid result", 500);
  return {
    version: "1.0", tool: name, arguments: args, data,
    evidence: { request_id: requestId, data_source: store.mode, spatial_method: store.mode === "postgres" ? "PostGIS geography WGS84 spheroid" : "Haversine sphere R=6371000m (demo)", generated_at: new Date().toISOString(), duration_ms: Date.now() - started, time_window: args.start_time ? { start: new Date(args.start_time).toISOString(), end: new Date(args.end_time).toISOString(), end_exclusive: true } : null },
    warnings: store.mode === "memory" ? ["Synthetic in-memory data; distances use a sphere, not the PostGIS spheroid."] : []
  };
}
module.exports = { executeTool, catalog, validateArguments };
