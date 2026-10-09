"use strict";

function statistics(hospitalId, reports, queues) {
  const queueById = new Map(queues.map((q) => [q.id, q]));
  const known = reports.map((r) => queueById.get(r.queueLengthId)?.sortOrder).filter((v) => v > 0);
  const waits = reports.map((r) => r.queueWaitMinutes).filter((v) => Number.isFinite(v));
  const scores = reports.map((r) => r.cleanlinessScore).filter((v) => Number.isFinite(v));
  const mean = (values) => values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
  const sorted = [...reports].sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt) || a.id - b.id);
  return {
    hospital_id: hospitalId,
    report_count: reports.length,
    known_queue_count: known.length,
    average_queue_severity: mean(known),
    observed_wait_count: waits.length,
    average_wait_minutes: mean(waits),
    cleanliness_count: scores.length,
    average_cleanliness: mean(scores),
    min_cleanliness: scores.length ? Math.min(...scores) : null,
    max_cleanliness: scores.length ? Math.max(...scores) : null,
    first_report_at: sorted[0]?.createdAt || null,
    last_report_at: sorted.at(-1)?.createdAt || null,
    first_queue_severity: sorted.length ? (queueById.get(sorted[0].queueLengthId)?.sortOrder || null) : null,
    last_queue_severity: sorted.length ? (queueById.get(sorted.at(-1).queueLengthId)?.sortOrder || null) : null,
    report_ids: sorted.slice(0, 200).map((r) => r.id),
    report_ids_complete: sorted.length <= 200
  };
}

module.exports = { statistics };
