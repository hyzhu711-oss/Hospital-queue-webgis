"use strict";
const express = require("express");
const { timingSafeEqual } = require("crypto");
const { catalog, executeTool } = require("../tools/service");
function createToolsRouter(store) {
  const router = express.Router();
  router.use((req, res, next) => {
    const token = process.env.GIS_TOOLS_TOKEN;
    if (!token) return next();
    const actual = Buffer.from(req.headers.authorization || ""), expected = Buffer.from(`Bearer ${token}`);
    if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) return res.status(401).json({ error: { code: "unauthorized", message: "GIS tool authorization required" } });
    next();
  });
  router.get("/catalog", (req, res) => res.json(catalog()));
  router.post("/:name", async (req, res) => {
    try { res.json(await executeTool(store, req.params.name, req.body)); }
    catch (error) { res.status(error.status || 500).json({ error: { code: error.code || "tool_execution_failure", message: error.status && error.status < 500 ? error.message : "GIS tool execution failed" } }); }
  });
  return router;
}
module.exports = { createToolsRouter };
