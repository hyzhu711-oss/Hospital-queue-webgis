"use strict";

const request = require("supertest");
const { createApp } = require("../src/app");
const { createMemoryStore } = require("../src/store/memoryStore");

function buildApp() {
  const store = createMemoryStore();
  return { app: createApp({ store, demoUserId: 1 }), store };
}

describe("Hospital Queue WebGIS API", () => {
  test("reports health and active data source", async () => {
    const { app } = buildApp();
    const response = await request(app).get("/api/health").expect(200);
    expect(response.body).toEqual({ status: "ok", dataSource: "memory" });
  });

  test("returns the portfolio demo user", async () => {
    const { app } = buildApp();
    const response = await request(app).get("/api/user").expect(200);
    expect(response.body).toMatchObject({ id: 1, name: "Portfolio visitor" });
  });

  test("returns ordered queue length options", async () => {
    const { app } = buildApp();
    const response = await request(app).get("/api/queue-lengths").expect(200);
    expect(response.body).toHaveLength(6);
    expect(response.body[0].description).toBe("Unknown");
    expect(response.body.at(-1).description).toBe("Over 60 minutes");
  });

  test("returns hospitals as a GeoJSON FeatureCollection", async () => {
    const { app } = buildApp();
    const response = await request(app).get("/api/hospitals?userId=1").expect(200);
    expect(response.body.type).toBe("FeatureCollection");
    expect(response.body.features).toHaveLength(8);
    expect(response.body.features[0]).toMatchObject({
      type: "Feature",
      geometry: { type: "Point" }
    });
    expect(response.body.features[0].geometry.coordinates).toHaveLength(2);
  });

  test("returns five nearest hospitals in ascending distance order", async () => {
    const { app } = buildApp();
    const response = await request(app)
      .get("/api/hospitals/nearest?lat=51.5246&lon=-0.1347&limit=5")
      .expect(200);
    expect(response.body.features).toHaveLength(5);
    const distances = response.body.features.map((feature) => feature.properties.distanceMetres);
    expect(distances).toEqual([...distances].sort((a, b) => a - b));
    expect(distances[0]).toBe(0);
  });

  test("rejects invalid coordinates", async () => {
    const { app } = buildApp();
    const response = await request(app)
      .get("/api/hospitals/nearest?lat=120&lon=-0.1")
      .expect(400);
    expect(response.body.error).toMatch(/Latitude/);
  });

  test("returns hospitals without a known queue status", async () => {
    const { app } = buildApp();
    const response = await request(app).get("/api/hospitals/unknown?userId=1").expect(200);
    expect(response.body.features).toHaveLength(1);
    expect(response.body.features[0].properties.name).toBe("Islington Community Hospital");
  });

  test("returns a queue summary whose counts match the hospital total", async () => {
    const { app } = buildApp();
    const response = await request(app).get("/api/hospitals/summary?userId=1").expect(200);
    expect(response.body.reduce((total, item) => total + item.count, 0)).toBe(8);
  });

  test("returns reporting activity and rank", async () => {
    const { app } = buildApp();
    const response = await request(app).get("/api/users/1/activity").expect(200);
    expect(response.body).toEqual({ reportCount: 6, rank: 1 });
  });

  test("returns hospital reports newest first", async () => {
    const { app } = buildApp();
    const response = await request(app).get("/api/hospitals/1/reports").expect(200);
    expect(response.body).toHaveLength(3);
    expect(new Date(response.body[0].createdAt).getTime()).toBeGreaterThan(
      new Date(response.body[1].createdAt).getTime()
    );
  });

  test("adds a hospital with an initial Unknown report", async () => {
    const { app } = buildApp();
    const created = await request(app)
      .post("/api/hospitals")
      .send({
        name: "Test Health Centre",
        lastInspected: "2026-08-01",
        latitude: 51.51,
        longitude: -0.12,
        userId: 1
      })
      .expect(201);
    expect(created.body).toMatchObject({ name: "Test Health Centre", queueDescription: "Unknown" });

    const hospitals = await request(app).get("/api/hospitals?userId=1").expect(200);
    expect(hospitals.body.features).toHaveLength(9);
  });

  test("validates required hospital fields", async () => {
    const { app } = buildApp();
    const response = await request(app)
      .post("/api/hospitals")
      .send({ latitude: 51.51, longitude: -0.12, userId: 1 })
      .expect(400);
    expect(response.body.error).toMatch(/Missing required/);
  });

  test("adds a report and updates the latest hospital status", async () => {
    const { app } = buildApp();
    const response = await request(app)
      .post("/api/reports")
      .send({ hospitalId: 8, queueLengthId: 5, cleanliness: "Clean and organised.", userId: 1 })
      .expect(201);
    expect(response.body.previousQueueDescription).toBe("Unknown");

    const hospitals = await request(app).get("/api/hospitals?userId=1").expect(200);
    const updated = hospitals.body.features.find((feature) => feature.properties.id === 8);
    expect(updated.properties.queueDescription).toBe("30-60 minutes");

    const activity = await request(app).get("/api/users/1/activity").expect(200);
    expect(activity.body.reportCount).toBe(7);
  });

  test("rejects a report with an unknown queue option", async () => {
    const { app } = buildApp();
    const response = await request(app)
      .post("/api/reports")
      .send({ hospitalId: 1, queueLengthId: 99, cleanliness: "Clean.", userId: 1 })
      .expect(400);
    expect(response.body.error).toMatch(/Queue length option/);
  });

  test("does not expose unknown routes", async () => {
    const { app } = buildApp();
    await request(app).get("/api/not-a-route").expect(404);
  });
});
