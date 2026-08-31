"use strict";

const demoData = require("../data/demoData");
const { distanceInMetres } = require("../utils/geo");

function copy(value) {
  return JSON.parse(JSON.stringify(value));
}

function createMemoryStore() {
  const users = copy(demoData.users);
  const queueLengths = copy(demoData.queueLengths);
  const hospitals = copy(demoData.hospitals);
  const reports = copy(demoData.reports);

  const queueById = () => new Map(queueLengths.map((item) => [Number(item.id), item]));

  function latestReportForHospital(hospitalId) {
    return reports
      .filter((report) => Number(report.hospitalId) === Number(hospitalId))
      .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))[0];
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
      latestReportAt: latest?.createdAt || null
    };
  }

  return {
    mode: "memory",

    async getUser(userId) {
      return copy(users.find((user) => Number(user.id) === Number(userId)) || users[0]);
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
        .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
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
      const rank = counts.findIndex((item) => Number(item.userId) === Number(userId)) + 1;

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

    async close() {}
  };
}

module.exports = { createMemoryStore };
