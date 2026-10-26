"use strict";

const path = require("path");
const express = require("express");
const helmet = require("helmet");
const { createApiRouter } = require("./routes/api");

function createApp({ store, demoUserId = 1 }) {
  const app = express();
  const publicDirectory = path.join(__dirname, "..", "public");

  app.disable("x-powered-by");
  app.use(
    helmet({
      contentSecurityPolicy: false,
      crossOriginEmbedderPolicy: false
    })
  );
  app.use(express.json({ limit: "100kb" }));
  app.use("/api", createApiRouter(store, demoUserId));
  app.use(express.static(publicDirectory, { extensions: ["html"] }));

  app.use((req, res) => {
    res.status(404).json({ error: "Route not found" });
  });

  app.use((error, req, res, next) => {
    if (res.headersSent) return next(error);
    if (!error.status || error.status >= 500) console.error(error);
    res.status(error.status || 500).json({
      error: error.status ? error.message : "Unexpected server error"
    });
  });

  return app;
}

module.exports = { createApp };
