"use strict";

const dashboardState = {
  userId: 1,
  viewer: null,
  features: [],
  entityByHospitalId: new Map(),
  queueColours: new Map(),
  chart: null
};

const dashboardElements = {};

async function dashboardApi(path) {
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${response.status})`);
  }
  return response.json();
}

function cacheDashboardElements() {
  [
    "cleanlinessChart", "dashboardRank", "dashboardReportCount", "dashboardReportRows",
    "dashboardStatusDot", "dashboardToast", "dashboardToastMessage", "dashboardUserName",
    "globeLegend", "hospitalSelect", "knownQueues", "selectedHospitalName",
    "selectedHospitalStatus", "totalHospitals"
  ].forEach((id) => { dashboardElements[id] = document.getElementById(id); });
}

function initialiseGlobe() {
  dashboardState.viewer = new Cesium.Viewer("cesiumContainer", {
    animation: false,
    baseLayerPicker: false,
    fullscreenButton: false,
    geocoder: false,
    homeButton: false,
    imageryProvider: false,
    infoBox: false,
    navigationHelpButton: false,
    sceneModePicker: false,
    selectionIndicator: true,
    timeline: false,
    terrainProvider: new Cesium.EllipsoidTerrainProvider()
  });
  dashboardState.viewer.imageryLayers.addImageryProvider(
    new Cesium.UrlTemplateImageryProvider({
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
      maximumLevel: 19,
      credit: "Tiles by Esri"
    })
  );
  dashboardState.viewer.scene.globe.depthTestAgainstTerrain = false;
  dashboardState.viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(-0.134, 51.528, 10500),
    duration: 0
  });
  const handler = new Cesium.ScreenSpaceEventHandler(dashboardState.viewer.scene.canvas);
  handler.setInputAction((movement) => {
    const picked = dashboardState.viewer.scene.pick(movement.position);
    const hospitalId = picked?.id?.properties?.hospitalId?.getValue();
    if (hospitalId) selectDashboardHospital(Number(hospitalId), false);
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
}

function renderGlobeHospitals(features) {
  dashboardState.viewer.entities.removeAll();
  dashboardState.entityByHospitalId.clear();
  dashboardElements.hospitalSelect.innerHTML = "";

  features.forEach((feature, index) => {
    const properties = feature.properties;
    const [longitude, latitude] = feature.geometry.coordinates;
    const entity = dashboardState.viewer.entities.add({
      name: properties.name,
      position: Cesium.Cartesian3.fromDegrees(longitude, latitude, 40),
      point: {
        pixelSize: 13,
        color: Cesium.Color.fromCssColorString(properties.queueColour),
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 3,
        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
      },
      label: {
        text: properties.name,
        font: "12px sans-serif",
        fillColor: Cesium.Color.fromCssColorString("#18201f"),
        showBackground: true,
        backgroundColor: Cesium.Color.WHITE.withAlpha(0.86),
        backgroundPadding: new Cesium.Cartesian2(7, 5),
        pixelOffset: new Cesium.Cartesian2(0, -25),
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 8500),
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      },
      properties: { hospitalId: properties.id }
    });
    dashboardState.entityByHospitalId.set(properties.id, entity);
    const option = document.createElement("option");
    option.value = properties.id;
    option.textContent = properties.name;
    dashboardElements.hospitalSelect.appendChild(option);
    if (index === 0) dashboardElements.hospitalSelect.value = properties.id;
  });
}

function renderGlobeLegend(summary) {
  dashboardElements.globeLegend.innerHTML = "";
  summary.forEach((item) => {
    const row = document.createElement("div");
    row.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = item.colour;
    const label = document.createElement("span");
    label.textContent = item.description;
    row.append(swatch, label);
    dashboardElements.globeLegend.appendChild(row);
  });
}

async function selectDashboardHospital(hospitalId, fly = true) {
  const feature = dashboardState.features.find((item) => Number(item.properties.id) === Number(hospitalId));
  if (!feature) return;
  const properties = feature.properties;
  dashboardElements.hospitalSelect.value = properties.id;
  dashboardElements.selectedHospitalName.textContent = properties.name;
  dashboardElements.dashboardStatusDot.style.background = properties.queueColour;
  dashboardElements.selectedHospitalStatus.textContent =
    `${properties.queueDescription}. ${properties.cleanliness || "No cleanliness observation."}`;
  dashboardState.viewer.selectedEntity = dashboardState.entityByHospitalId.get(properties.id);

  if (fly) {
    const [longitude, latitude] = feature.geometry.coordinates;
    dashboardState.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(longitude, latitude, 2200),
      duration: 0.8
    });
  }

  dashboardElements.dashboardReportRows.innerHTML = '<tr><td colspan="3">Loading reports...</td></tr>';
  try {
    const reports = await dashboardApi(`/api/hospitals/${properties.id}/reports`);
    renderDashboardReports(reports);
    renderCleanlinessChart(reports);
  } catch (error) {
    dashboardElements.dashboardReportRows.innerHTML = "";
    const row = dashboardElements.dashboardReportRows.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 3;
    cell.textContent = error.message;
  }
}

function renderDashboardReports(reports) {
  dashboardElements.dashboardReportRows.innerHTML = "";
  if (!reports.length) {
    const row = dashboardElements.dashboardReportRows.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 3;
    cell.textContent = "No reports submitted.";
    return;
  }

  reports.forEach((report) => {
    const row = dashboardElements.dashboardReportRows.insertRow();
    const dateCell = row.insertCell();
    dateCell.textContent = new Intl.DateTimeFormat("en-GB", {
      day: "2-digit", month: "short", year: "2-digit"
    }).format(new Date(report.createdAt));
    const queueCell = row.insertCell();
    const queue = document.createElement("span");
    queue.className = "table-queue";
    queue.style.setProperty("--queue-colour", report.queueColour);
    queue.textContent = report.queueDescription;
    queueCell.appendChild(queue);
    row.insertCell().textContent = report.cleanliness;
  });
}

function classifyCleanliness(text) {
  const value = String(text).toLowerCase();
  const concernWords = ["litter", "dirty", "needed attention", "unclean", "poor"];
  const positiveWords = ["clean", "tidy", "bright", "maintained", "organised", "good"];
  if (concernWords.some((word) => value.includes(word))) return "Needs attention";
  if (positiveWords.some((word) => value.includes(word))) return "Positive";
  return "Neutral";
}

function renderCleanlinessChart(reports) {
  const counts = { Positive: 0, Neutral: 0, "Needs attention": 0 };
  reports.forEach((report) => { counts[classifyCleanliness(report.cleanliness)] += 1; });
  if (dashboardState.chart) dashboardState.chart.destroy();
  dashboardState.chart = new Chart(dashboardElements.cleanlinessChart, {
    type: "bar",
    data: {
      labels: Object.keys(counts),
      datasets: [{
        data: Object.values(counts),
        backgroundColor: ["#2f855a", "#0e7490", "#d97706"],
        borderRadius: 3,
        borderSkipped: false
      }]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#e7ecea" } },
        y: { grid: { display: false } }
      },
      plugins: { legend: { display: false } },
      animation: { duration: 250 }
    }
  });
}

function showDashboardError(message) {
  dashboardElements.dashboardToastMessage.textContent = message;
  dashboardElements.dashboardToast.hidden = false;
}

async function initialiseDashboard() {
  cacheDashboardElements();
  lucide.createIcons();
  try {
    initialiseGlobe();
    const [user, hospitals, summary, activity] = await Promise.all([
      dashboardApi(`/api/user?userId=${dashboardState.userId}`),
      dashboardApi(`/api/hospitals?userId=${dashboardState.userId}`),
      dashboardApi(`/api/hospitals/summary?userId=${dashboardState.userId}`),
      dashboardApi(`/api/users/${dashboardState.userId}/activity`)
    ]);
    dashboardState.features = hospitals.features || [];
    dashboardState.queueColours=new Map(summary.map(q=>[q.description,q.colour]));
    dashboardElements.dashboardUserName.textContent = user.name;
    dashboardElements.dashboardReportCount.textContent = activity.reportCount;
    dashboardElements.dashboardRank.textContent = activity.rank;
    dashboardElements.totalHospitals.textContent = dashboardState.features.length;
    dashboardElements.knownQueues.textContent = dashboardState.features.filter(
      (feature) => feature.properties.queueDescription !== "Unknown"
    ).length;
    renderGlobeHospitals(dashboardState.features);
    renderGlobeLegend(summary);
    dashboardElements.hospitalSelect.addEventListener("change", (event) => {
      selectDashboardHospital(Number(event.target.value));
    });
    if (dashboardState.features.length) {
      await selectDashboardHospital(dashboardState.features[0].properties.id, false);
    }
    if(window.QueueLensAgentUI)await window.QueueLensAgentUI.initialise({host:document.getElementById("agentPanel"),adapter:cesiumAgentAdapter(),getLocation:()=>null});
  } catch (error) {
    showDashboardError(`Unable to initialise dashboard: ${error.message}`);
  }
}

document.addEventListener("DOMContentLoaded", initialiseDashboard);

function cesiumAgentAdapter(){
  const viewer=dashboardState.viewer;
  return {
    prepare(entities){for(const h of entities){const old=dashboardState.features.find(f=>f.properties.id===h.hospital_id);const colour=dashboardState.queueColours.get(h.queue_description)||"#087f72";if(!old){const feature={type:"Feature",geometry:{type:"Point",coordinates:[h.longitude,h.latitude]},properties:{id:h.hospital_id,name:h.name,queueDescription:h.queue_description,cleanliness:h.cleanliness_note,queueColour:colour}};dashboardState.features.push(feature);const entity=viewer.entities.add({name:h.name,position:Cesium.Cartesian3.fromDegrees(h.longitude,h.latitude,40),point:{pixelSize:13,color:Cesium.Color.fromCssColorString(colour),outlineColor:Cesium.Color.WHITE,outlineWidth:3},label:{text:h.name,font:"12px sans-serif"},properties:{hospitalId:h.hospital_id}});dashboardState.entityByHospitalId.set(h.hospital_id,entity);const option=document.createElement("option");option.value=h.hospital_id;option.textContent=h.name;dashboardElements.hospitalSelect.append(option);}else{old.geometry.coordinates=[h.longitude,h.latitude];Object.assign(old.properties,{name:h.name,queueDescription:h.queue_description,cleanliness:h.cleanliness_note,queueColour:colour});const entity=dashboardState.entityByHospitalId.get(h.hospital_id);entity.show=true;entity.position=Cesium.Cartesian3.fromDegrees(h.longitude,h.latitude,40);entity.point.color=Cesium.Color.fromCssColorString(colour);}}},
    filter(ids){for(const[id,entity]of dashboardState.entityByHospitalId)entity.show=ids.includes(id);},
    fit_bounds(ids){return viewer.flyTo(ids.map(id=>dashboardState.entityByHospitalId.get(id)),{duration:0.6});},
    highlight(ids){for(const[id,entity]of dashboardState.entityByHospitalId){entity.point.outlineColor=ids.includes(id)?Cesium.Color.CYAN:Cesium.Color.WHITE;entity.point.pixelSize=ids.includes(id)?17:13;}},
    rank(ids){for(const[id,entity]of dashboardState.entityByHospitalId){const index=ids.indexOf(id);entity.label.text=(index>=0?`${index+1}. `:"")+entity.name;}},
    compare(ids){this.highlight(ids);},
    fly_to(id){const f=dashboardState.features.find(f=>f.properties.id===id);viewer.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(...f.geometry.coordinates,2200),duration:0.8});},
    open_popup(id){return selectDashboardHospital(id,false);}
  };
}
