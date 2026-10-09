"use strict";

const { createMemoryStore } = require("./memoryStore");
const { createPostgresStore } = require("./postgresStore");

function createStore() {
  const mode = (process.env.DATA_SOURCE || "memory").toLowerCase();
  return mode === "postgres" ? createPostgresStore() : createMemoryStore();
}

module.exports = { createStore };
