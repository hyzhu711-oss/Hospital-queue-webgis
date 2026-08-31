"use strict";

const queueLengths = [
  { id: 1, description: "Unknown", colour: "#6b7280", sortOrder: 0 },
  { id: 2, description: "No queue", colour: "#2f855a", sortOrder: 1 },
  { id: 3, description: "Under 15 minutes", colour: "#0f766e", sortOrder: 2 },
  { id: 4, description: "15-30 minutes", colour: "#d97706", sortOrder: 3 },
  { id: 5, description: "30-60 minutes", colour: "#dc6b2f", sortOrder: 4 },
  { id: 6, description: "Over 60 minutes", colour: "#b42318", sortOrder: 5 }
];

const users = [
  { id: 1, name: "Portfolio visitor" },
  { id: 2, name: "Demo contributor A" },
  { id: 3, name: "Demo contributor B" }
];

const hospitals = [
  { id: 1, name: "Bloomsbury Community Hospital", lastInspected: "2026-04-14", longitude: -0.1347, latitude: 51.5246, userId: 1 },
  { id: 2, name: "Regent Health Centre", lastInspected: "2026-03-22", longitude: -0.1451, latitude: 51.5302, userId: 1 },
  { id: 3, name: "St Pancras Medical Centre", lastInspected: "2026-05-03", longitude: -0.126, latitude: 51.534, userId: 1 },
  { id: 4, name: "Camden Riverside Hospital", lastInspected: "2026-02-18", longitude: -0.1512, latitude: 51.541, userId: 1 },
  { id: 5, name: "Fitzrovia Clinic", lastInspected: "2026-04-30", longitude: -0.142, latitude: 51.5191, userId: 1 },
  { id: 6, name: "Holborn Health Campus", lastInspected: "2026-01-29", longitude: -0.1175, latitude: 51.518, userId: 1 },
  { id: 7, name: "Marylebone Hospital", lastInspected: "2026-05-12", longitude: -0.161, latitude: 51.522, userId: 1 },
  { id: 8, name: "Islington Community Hospital", lastInspected: "2026-03-11", longitude: -0.105, latitude: 51.536, userId: 1 }
];

const reports = [
  { id: 1, hospitalId: 1, userId: 2, queueLengthId: 4, cleanliness: "Reception was busy but the waiting area was clean.", createdAt: "2026-05-18T08:30:00.000Z" },
  { id: 2, hospitalId: 1, userId: 1, queueLengthId: 3, cleanliness: "Clean seating area and clear signs.", createdAt: "2026-05-21T10:15:00.000Z" },
  { id: 3, hospitalId: 2, userId: 3, queueLengthId: 5, cleanliness: "Some litter near the entrance.", createdAt: "2026-05-20T13:45:00.000Z" },
  { id: 4, hospitalId: 2, userId: 1, queueLengthId: 4, cleanliness: "Facilities were tidy during the afternoon visit.", createdAt: "2026-05-23T14:10:00.000Z" },
  { id: 5, hospitalId: 3, userId: 1, queueLengthId: 2, cleanliness: "Very clean and quiet.", createdAt: "2026-05-24T09:05:00.000Z" },
  { id: 6, hospitalId: 4, userId: 2, queueLengthId: 6, cleanliness: "Crowded waiting room; surfaces appeared clean.", createdAt: "2026-05-19T16:20:00.000Z" },
  { id: 7, hospitalId: 4, userId: 1, queueLengthId: 5, cleanliness: "Busy, but staff kept shared areas organised.", createdAt: "2026-05-25T11:35:00.000Z" },
  { id: 8, hospitalId: 5, userId: 3, queueLengthId: 3, cleanliness: "Good overall condition.", createdAt: "2026-05-22T12:25:00.000Z" },
  { id: 9, hospitalId: 5, userId: 1, queueLengthId: 3, cleanliness: "Clean floors and seating.", createdAt: "2026-05-26T08:40:00.000Z" },
  { id: 10, hospitalId: 6, userId: 2, queueLengthId: 4, cleanliness: "Hand sanitiser was available.", createdAt: "2026-05-24T15:50:00.000Z" },
  { id: 11, hospitalId: 6, userId: 1, queueLengthId: 5, cleanliness: "Waiting area needed attention near closing time.", createdAt: "2026-05-27T17:15:00.000Z" },
  { id: 12, hospitalId: 7, userId: 3, queueLengthId: 2, cleanliness: "Bright and well maintained.", createdAt: "2026-05-28T09:30:00.000Z" },
  { id: 13, hospitalId: 1, userId: 3, queueLengthId: 2, cleanliness: "No visible issues during the morning visit.", createdAt: "2026-05-29T07:55:00.000Z" },
  { id: 14, hospitalId: 3, userId: 2, queueLengthId: 3, cleanliness: "Tidy entrance and reception.", createdAt: "2026-05-29T12:10:00.000Z" }
];

module.exports = { hospitals, queueLengths, reports, users };
