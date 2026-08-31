"use strict";

require("dotenv").config();

const { createApp } = require("./app");
const { createStore } = require("./store");

const port = Number(process.env.PORT) || 3000;
const demoUserId = Number(process.env.DEMO_USER_ID) || 1;
const store = createStore();
const app = createApp({ store, demoUserId });
const server = app.listen(port, "0.0.0.0", () => {
  console.log(`Hospital Queue WebGIS listening on http://localhost:${port} (${store.mode})`);
});

async function shutdown() {
  server.close(async () => {
    await store.close();
    process.exit(0);
  });
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
