"use strict";

const demoData = require("../data/demoData");
const { distanceInMetres } = require("../utils/geo");
const { statistics } = require("../domain/statistics");

function copy(value) {
  return JSON.parse(JSON.stringify(value));
}

function createMemoryStore(seed = demoData) {
  const users = copy(seed.users);
  const queueLengths = copy(seed.queueLengths);
  const hospitals = copy(seed.hospitals);
  const reports = copy(seed.reports);

  const queueById = () => new Map(queueLengths.map((item) => [Number(item.id), item]));

  function latestReportForHospital(hospitalId) {
    return reports
      .filter((report) => Number(report.hospitalId) === Number(hospitalId))
      .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt) || b.id - a.id)[0];
  }

  function enrichHospital(hospital) {
    const latest = latestReportForHospital(hospital.id);
    const queue = queueById().get(Number(latest?.queueLengthId)) || queueLengths[0];

    return {
      ...copy(hospital),
      queueLengthId: queue.id,
      queueDescription: queue.description,
      queueColour: queue.colour,
      cleanliness: latest?.cleanliness || "No report yet",
      latestReportAt: latest?.createdAt || null,
      latestReportId: latest?.id ?? null,
      cleanlinessScore: latest?.cleanlinessScore ?? null,
      queueWaitMinutes: latest?.queueWaitMinutes ?? null
    };
  }

  return {
    mode: "memory",

    async healthCheck() {
      return { status: "ok", dataSource: "memory" };
    },

    async getUser(userId) {
      return copy(users.find((user) => Number(user.id) === Number(userId)) || null);
    },

    async listQueueLengths() {
      return copy(queueLengths).sort((a, b) => a.sortOrder - b.sortOrder);
    },

    async listHospitalsByUser(userId) {
      return hospitals
        .filter((hospital) => Number(hospital.userId) === Number(userId))
        .map(enrichHospital);
    },

    async listNearestHospitals(latitude, longitude, limit = 5) {
      return hospitals
        .map(enrichHospital)
        .map((hospital) => ({
          ...hospital,
          distanceMetres: Math.round(
            distanceInMetres(latitude, longitude, hospital.latitude, hospital.longitude)
          )
        }))
        .sort((a, b) => a.distanceMetres - b.distanceMetres)
        .slice(0, limit);
    },

    async listUnknownHospitals(userId) {
      const items = await this.listHospitalsByUser(userId);
      return items.filter((hospital) => hospital.queueDescription === "Unknown");
    },

    async getQueueSummary(userId) {
      const items = await this.listHospitalsByUser(userId);
      return queueLengths.map((queue) => ({
        queueLengthId: queue.id,
        description: queue.description,
        colour: queue.colour,
        count: items.filter((hospital) => hospital.queueLengthId === queue.id).length
      }));
    },

    async listReportsForHospital(hospitalId) {
      const queueMap = queueById();
      return reports
        .filter((report) => Number(report.hospitalId) === Number(hospitalId))
        .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt) || b.id - a.id)
        .map((report) => {
          const queue = queueMap.get(Number(report.queueLengthId));
          const user = users.find((item) => Number(item.id) === Number(report.userId));
          return {
            ...copy(report),
            queueDescription: queue.description,
            queueColour: queue.colour,
            contributorName: user?.name || "Anonymous"
          };
        });
    },

    async getUserActivity(userId) {
      const counts = users
        .map((user) => ({
          userId: user.id,
          count: reports.filter((report) => Number(report.userId) === Number(user.id)).length
        }))
        .sort((a, b) => b.count - a.count);
      const userCount = counts.find((item) => Number(item.userId) === Number(userId))?.count || 0;
      const rank = counts.filter((item) => item.count > userCount).length + 1;

      return { reportCount: userCount, rank: rank || counts.length + 1 };
    },

    async insertHospital(input) {
      const hospital = {
        id: Math.max(0, ...hospitals.map((item) => item.id)) + 1,
        name: input.name,
        lastInspected: input.lastInspected,
        longitude: Number(input.longitude),
        latitude: Number(input.latitude),
        userId: Number(input.userId)
      };
      hospitals.push(hospital);

      reports.push({
        id: Math.max(0, ...reports.map((item) => item.id)) + 1,
        hospitalId: hospital.id,
        userId: hospital.userId,
        queueLengthId: 1,
        cleanliness: "No report yet",
        createdAt: new Date().toISOString()
      });

      return enrichHospital(hospital);
    },

    async insertReport(input) {
      const hospital = hospitals.find((item) => Number(item.id) === Number(input.hospitalId));
      if (!hospital) {
        const error = new Error("Hospital not found");
        error.status = 404;
        throw error;
      }

      const queue = queueById().get(Number(input.queueLengthId));
      if (!queue) {
        const error = new Error("Queue length option not found");
        error.status = 400;
        throw error;
      }

      const previous = latestReportForHospital(hospital.id);
      const previousQueue = queueById().get(Number(previous?.queueLengthId));
      const report = {
        id: Math.max(0, ...reports.map((item) => item.id)) + 1,
        hospitalId: hospital.id,
        userId: Number(input.userId),
        queueLengthId: queue.id,
        cleanliness: input.cleanliness,
        cleanlinessScore: input.cleanlinessScore ?? null,
        queueWaitMinutes: input.queueWaitMinutes ?? null,
        createdAt: new Date().toISOString()
      };
      reports.push(report);

      return {
        report: {
          ...copy(report),
          queueDescription: queue.description,
          queueColour: queue.colour
        },
        previousQueueDescription: previousQueue?.description || "Unknown"
      };
    },

    async toolReadSnapshot(callback) {
      return callback(createMemoryStore({ users, queueLengths, hospitals, reports }));
    },
    async toolResolveHospitals(query) {
      const exact = hospitals.filter((h) => h.name.toLowerCase() === query.toLowerCase());
      return (exact.length ? exact : hospitals.filter((h) => h.name.toLowerCase().includes(query.toLowerCase()))).sort((a,b) => a.id-b.id).slice(0,201).map(enrichHospital);
    },
    async toolGetHospitals(ids, origin) {
      return hospitals.filter((h) => ids.includes(h.id)).sort((a,b)=>a.id-b.id).map(enrichHospital).map((h)=>({ ...h, distanceMetresRaw: origin ? distanceInMetres(origin.latitude, origin.longitude, h.latitude, h.longitude) : null }));
    },
    async toolSearchHospitals(input) {
      const rows = await this.toolGetHospitals(hospitals.map((h)=>h.id), input);
      return rows.filter((h)=>input.radius_m === undefined || h.distanceMetresRaw <= input.radius_m).sort((a,b)=>a.distanceMetresRaw-b.distanceMetresRaw || a.id-b.id).slice(0,input.limit);
    },
    async toolGetReports(ids, start, end, limit) {
      return copy(reports.filter((r)=>ids.includes(r.hospitalId) && Date.parse(r.createdAt)>=Date.parse(start) && Date.parse(r.createdAt)<Date.parse(end)).sort((a,b)=>Date.parse(b.createdAt)-Date.parse(a.createdAt)||b.id-a.id).slice(0,limit));
    },
    async toolStatistics(ids, start, end) {
      return ids.map((id)=>statistics(id,reports.filter((r)=>r.hospitalId===id && Date.parse(r.createdAt)>=Date.parse(start)&&Date.parse(r.createdAt)<Date.parse(end)),queueLengths));
    },
    async close() {}
  };
}

module.exports = { createMemoryStore };
