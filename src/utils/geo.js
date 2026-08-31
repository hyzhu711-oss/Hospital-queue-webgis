"use strict";

function toRadians(value) {
  return (value * Math.PI) / 180;
}

function distanceInMetres(latitudeA, longitudeA, latitudeB, longitudeB) {
  const earthRadius = 6371000;
  const latitudeDelta = toRadians(latitudeB - latitudeA);
  const longitudeDelta = toRadians(longitudeB - longitudeA);
  const a =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(toRadians(latitudeA)) *
      Math.cos(toRadians(latitudeB)) *
      Math.sin(longitudeDelta / 2) ** 2;

  return earthRadius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function toHospitalFeature(hospital) {
  return {
    type: "Feature",
    geometry: {
      type: "Point",
      coordinates: [hospital.longitude, hospital.latitude]
    },
    properties: {
      id: hospital.id,
      name: hospital.name,
      lastInspected: hospital.lastInspected,
      userId: hospital.userId,
      queueLengthId: hospital.queueLengthId,
      queueDescription: hospital.queueDescription,
      queueColour: hospital.queueColour,
      cleanliness: hospital.cleanliness,
      latestReportAt: hospital.latestReportAt,
      distanceMetres: hospital.distanceMetres
    }
  };
}

function toFeatureCollection(hospitals) {
  return {
    type: "FeatureCollection",
    features: hospitals.map(toHospitalFeature)
  };
}

module.exports = { distanceInMetres, toFeatureCollection, toHospitalFeature };
