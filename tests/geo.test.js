"use strict";

const { distanceInMetres, toFeatureCollection } = require("../src/utils/geo");

describe("geospatial utilities", () => {
  test("calculates zero distance for identical coordinates", () => {
    expect(distanceInMetres(51.5, -0.1, 51.5, -0.1)).toBe(0);
  });

  test("calculates a plausible central London distance", () => {
    const distance = distanceInMetres(51.5246, -0.1347, 51.5302, -0.1451);
    expect(distance).toBeGreaterThan(900);
    expect(distance).toBeLessThan(1000);
  });

  test("converts enriched hospitals into GeoJSON", () => {
    const result = toFeatureCollection([{
      id: 1,
      name: "Example",
      longitude: -0.1,
      latitude: 51.5,
      userId: 1,
      lastInspected: "2026-01-01",
      queueLengthId: 2,
      queueDescription: "No queue",
      queueColour: "#2f855a",
      cleanliness: "Clean",
      latestReportAt: null
    }]);
    expect(result).toMatchObject({
      type: "FeatureCollection",
      features: [{ geometry: { type: "Point", coordinates: [-0.1, 51.5] } }]
    });
  });
});
