"use strict";

const express = require("express");
const { toFeatureCollection } = require("../utils/geo");

function parsePositiveInteger(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function requireFields(body, fields) {
  const missing = fields.filter((field) => body[field] === undefined || body[field] === "");
  if (missing.length) {
    const error = new Error(`Missing required field(s): ${missing.join(", ")}`);
    error.status = 400;
    throw error;
  }
}

function validateCoordinates(latitude, longitude) {
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
    const error = new Error("Latitude must be between -90 and 90");
    error.status = 400;
    throw error;
  }
  if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
    const error = new Error("Longitude must be between -180 and 180");
    error.status = 400;
    throw error;
  }
}

function asyncRoute(handler) {
  return (req, res, next) => Promise.resolve(handler(req, res, next)).catch(next);
}

function requireNonBlank(value, label) {
  const text = String(value).trim();
  if (!text) {
    const error = new Error(`${label} cannot be blank`);
    error.status = 400;
    throw error;
  }
  return text;
}

function createApiRouter(store, demoUserId) {
  const router = express.Router();

  router.get("/health", (req, res) => {
    res.json({ status: "ok", dataSource: store.mode });
  });

  router.get("/user", asyncRoute(async (req, res) => {
    const userId = parsePositiveInteger(req.query.userId, demoUserId);
    const user = await store.getUser(userId);
    if (!user) return res.status(404).json({ error: "User not found" });
    res.json(user);
  }));

  router.get("/queue-lengths", asyncRoute(async (req, res) => {
    res.json(await store.listQueueLengths());
  }));

  router.get("/hospitals", asyncRoute(async (req, res) => {
    const userId = parsePositiveInteger(req.query.userId, demoUserId);
    res.json(toFeatureCollection(await store.listHospitalsByUser(userId)));
  }));

  router.get("/hospitals/nearest", asyncRoute(async (req, res) => {
    const latitude = Number(req.query.lat);
    const longitude = Number(req.query.lon);
    validateCoordinates(latitude, longitude);
    const limit = Math.min(parsePositiveInteger(req.query.limit, 5), 20);
    res.json(toFeatureCollection(await store.listNearestHospitals(latitude, longitude, limit)));
  }));

  router.get("/hospitals/unknown", asyncRoute(async (req, res) => {
    const userId = parsePositiveInteger(req.query.userId, demoUserId);
    res.json(toFeatureCollection(await store.listUnknownHospitals(userId)));
  }));

  router.get("/hospitals/summary", asyncRoute(async (req, res) => {
    const userId = parsePositiveInteger(req.query.userId, demoUserId);
    res.json(await store.getQueueSummary(userId));
  }));

  router.get("/hospitals/:hospitalId/reports", asyncRoute(async (req, res) => {
    const hospitalId = parsePositiveInteger(req.params.hospitalId, 0);
    if (!hospitalId) return res.status(400).json({ error: "Invalid hospital id" });
    res.json(await store.listReportsForHospital(hospitalId));
  }));

  router.get("/users/:userId/activity", asyncRoute(async (req, res) => {
    const userId = parsePositiveInteger(req.params.userId, 0);
    if (!userId) return res.status(400).json({ error: "Invalid user id" });
    res.json(await store.getUserActivity(userId));
  }));

  router.post("/hospitals", asyncRoute(async (req, res) => {
    requireFields(req.body, ["name", "lastInspected", "latitude", "longitude", "userId"]);
    const latitude = Number(req.body.latitude);
    const longitude = Number(req.body.longitude);
    validateCoordinates(latitude, longitude);
    const hospital = await store.insertHospital({
      name: requireNonBlank(req.body.name, "Hospital name"),
      lastInspected: req.body.lastInspected,
      latitude,
      longitude,
      userId: parsePositiveInteger(req.body.userId, demoUserId)
    });
    res.status(201).json(hospital);
  }));

  router.post("/reports", asyncRoute(async (req, res) => {
    requireFields(req.body, ["hospitalId", "queueLengthId", "cleanliness", "userId"]);
    const result = await store.insertReport({
      hospitalId: parsePositiveInteger(req.body.hospitalId, 0),
      queueLengthId: parsePositiveInteger(req.body.queueLengthId, 0),
      cleanliness: requireNonBlank(req.body.cleanliness, "Cleanliness observation"),
      userId: parsePositiveInteger(req.body.userId, demoUserId)
    });
    res.status(201).json(result);
  }));

  return router;
}

module.exports = { createApiRouter };
