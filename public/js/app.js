"use strict";

const state = {
  userId: 1,
  map: null,
  hospitalLayer: null,
  locationMarker: null,
  allFeatures: [],
  visibleFeatures: [],
  queueLengths: [],
  selectedFeature: null,
  addMode: false,
  summaryChart: null,
  watchId: null,
  proximitySamples: [],
  toastTimer: null,
  currentLocation: null,
  locationAt: 0,
  markerByHospitalId: new Map()
};

const elements = {};

function cacheElements() {
  [
    "addHospitalButton", "cancelAddButton", "closeDetailButton", "coordinateDisplay",
    "detailCleanliness", "detailInspection", "detailName", "detailPanel", "detailQueue",
    "controlRail", "detailReportedAt", "detailSwatch", "emptyDetail", "hospitalDetail", "hospitalDialog",
    "hospitalForm", "locateButton", "mapInstruction", "mobileControlsButton", "proximityToggle", "queueLegend",
    "queueSelect", "refreshButton", "reportButton", "reportCount", "reportDialog",
    "reportForm", "reportHistory", "reportHospitalName", "toast", "toastMessage",
    "userName", "userRank"
  ].forEach((id) => { elements[id] = document.getElementById(id); });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.error || message;
    } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

function initialiseMap() {
  state.map = L.map("map", { zoomControl: false }).setView([51.5265, -0.134], 14);
  L.control.zoom({ position: "bottomright" }).addTo(state.map);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(state.map);
  state.hospitalLayer = L.layerGroup().addTo(state.map);
  state.map.on("click", handleMapClick);
}

function markerIcon(colour) {
  return L.divIcon({
    className: "hospital-div-icon",
    html: `<span class="hospital-marker" style="--marker-colour:${colour}"></span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 28]
  });
}

function renderHospitals(featureCollection, { fit = false } = {}) {
  state.visibleFeatures = featureCollection.features || [];
  state.hospitalLayer.clearLayers();
  state.markerByHospitalId.clear();
  const bounds = [];

  state.visibleFeatures.forEach((feature) => {
    const [longitude, latitude] = feature.geometry.coordinates;
    const marker = L.marker([latitude, longitude], {
      icon: markerIcon(feature.properties.queueColour || "#6b7280"),
      title: feature.properties.name
    });
    marker.on("click", () => selectHospital(feature));
    marker.addTo(state.hospitalLayer);
    state.markerByHospitalId.set(feature.properties.id, marker);
    bounds.push([latitude, longitude]);
  });

  if (fit && bounds.length) {
    state.map.fitBounds(bounds, { padding: [42, 42], maxZoom: 15 });
  }
}

async function selectHospital(feature) {
  state.selectedFeature = feature;
  const properties = feature.properties;
  elements.emptyDetail.hidden = true;
  elements.hospitalDetail.hidden = false;
  elements.detailPanel.classList.add("open");
  elements.detailName.textContent = properties.name;
  elements.detailQueue.textContent = properties.queueDescription;
  elements.detailSwatch.style.setProperty("--status-colour", properties.queueColour);
  elements.detailSwatch.parentElement.style.setProperty("--status-colour", properties.queueColour);
  elements.detailInspection.textContent = formatDate(properties.lastInspected, false);
  elements.detailReportedAt.textContent = properties.latestReportAt
    ? formatDate(properties.latestReportAt, true)
    : "No report yet";
  elements.detailCleanliness.textContent = properties.cleanliness || "No report yet";
  elements.reportHistory.innerHTML = '<div class="loading-line"></div><div class="loading-line"></div>';

  try {
    const reports = await api(`/api/hospitals/${properties.id}/reports`);
    renderReportHistory(reports);
  } catch (error) {
    elements.reportHistory.innerHTML = "";
    const message = document.createElement("p");
    message.className = "muted-message";
    message.textContent = error.message;
    elements.reportHistory.appendChild(message);
  }
}

function closeDetail() {
  state.selectedFeature = null;
  elements.hospitalDetail.hidden = true;
  elements.emptyDetail.hidden = false;
  elements.detailPanel.classList.remove("open");
}

function renderReportHistory(reports) {
  elements.reportHistory.innerHTML = "";
  if (!reports.length) {
    const empty = document.createElement("p");
    empty.className = "muted-message";
    empty.textContent = "No reports have been submitted for this hospital.";
    elements.reportHistory.appendChild(empty);
    return;
  }

  reports.slice(0, 6).forEach((report) => {
    const item = document.createElement("article");
    item.className = "report-item";
    const header = document.createElement("div");
    header.className = "report-item-header";
    const queue = document.createElement("span");
    queue.className = "queue-label";
    queue.style.setProperty("--queue-colour", report.queueColour);
    queue.textContent = report.queueDescription;
    const time = document.createElement("time");
    time.className = "report-time";
    time.dateTime = report.createdAt;
    time.textContent = formatDate(report.createdAt, true);
    const note = document.createElement("p");
    note.className = "report-note";
    note.textContent = report.cleanliness;
    header.append(queue, time);
    item.append(header, note);
    elements.reportHistory.appendChild(item);
  });
}

function renderQueueOptions() {
  elements.queueSelect.innerHTML = "";
  state.queueLengths
    .filter((queue) => queue.description !== "Unknown")
    .forEach((queue) => {
      const option = document.createElement("option");
      option.value = queue.id;
      option.textContent = queue.description;
      elements.queueSelect.appendChild(option);
    });
}

function renderSummary(summary) {
  elements.queueLegend.innerHTML = "";
  summary.forEach((item) => {
    const row = document.createElement("div");
    row.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = item.colour;
    const label = document.createElement("span");
    label.textContent = item.description;
    const count = document.createElement("span");
    count.className = "legend-count";
    count.textContent = item.count;
    row.append(swatch, label, count);
    elements.queueLegend.appendChild(row);
  });

  if (state.summaryChart) state.summaryChart.destroy();
  const chartContext = document.getElementById("queueSummaryChart");
  state.summaryChart = new Chart(chartContext, {
    type: "doughnut",
    data: {
      labels: summary.map((item) => item.description),
      datasets: [{
        data: summary.map((item) => item.count),
        backgroundColor: summary.map((item) => item.colour),
        borderColor: "#ffffff",
        borderWidth: 2,
        hoverOffset: 3
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "64%",
      plugins: { legend: { display: false }, tooltip: { displayColors: true } },
      animation: { duration: 300 }
    }
  });
}

async function loadOverview({ fit = false } = {}) {
  const [user, queueLengths, hospitals, activity, summary] = await Promise.all([
    api(`/api/user?userId=${state.userId}`),
    api("/api/queue-lengths"),
    api(`/api/hospitals?userId=${state.userId}`),
    api(`/api/users/${state.userId}/activity`),
    api(`/api/hospitals/summary?userId=${state.userId}`)
  ]);
  state.queueLengths = queueLengths;
  state.allFeatures = hospitals.features || [];
  elements.userName.textContent = user.name;
  elements.reportCount.textContent = activity.reportCount;
  elements.userRank.textContent = activity.rank;
  renderHospitals(hospitals, { fit });
  renderQueueOptions();
  renderSummary(summary);
}

function setActiveLayer(name) {
  document.querySelectorAll("[data-layer]").forEach((button) => {
    button.classList.toggle("active", button.dataset.layer === name);
  });
}

function setMobileControls(open) {
  elements.controlRail.classList.toggle("open", open);
  document.body.classList.toggle("controls-open", open);
  elements.mobileControlsButton.setAttribute("aria-expanded", String(open));
}

async function changeLayer(name) {
  try {
    if (name === "all") {
      renderHospitals({ type: "FeatureCollection", features: state.allFeatures }, { fit: true });
    } else if (name === "unknown") {
      renderHospitals(await api(`/api/hospitals/unknown?userId=${state.userId}`), { fit: true });
    } else if (name === "nearest") {
      const position = await getBrowserPosition();
      showLocation(position.coords.latitude, position.coords.longitude);
      const data = await api(
        `/api/hospitals/nearest?lat=${position.coords.latitude}&lon=${position.coords.longitude}&limit=5`
      );
      renderHospitals(data, { fit: true });
    }
    setActiveLayer(name);
    closeDetail();
  } catch (error) {
    showToast(error.message, true);
    setActiveLayer("all");
  }
}

function getBrowserPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Geolocation is not supported by this browser."));
    navigator.geolocation.getCurrentPosition(resolve, () => {
      reject(new Error("Location permission is required for this feature."));
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 });
  });
}

function showLocation(latitude, longitude) {
  state.currentLocation={latitude,longitude};
  state.locationAt=Date.now();
  if (state.locationMarker) state.locationMarker.remove();
  state.locationMarker = L.circleMarker([latitude, longitude], {
    radius: 7,
    color: "#ffffff",
    weight: 3,
    fillColor: "#0e7490",
    fillOpacity: 1
  }).addTo(state.map).bindTooltip("Your location");
}

async function locateUser() {
  try {
    const position = await getBrowserPosition();
    const { latitude, longitude } = position.coords;
    showLocation(latitude, longitude);
    state.map.flyTo([latitude, longitude], 16);
  } catch (error) {
    showToast(error.message, true);
  }
}

function setAddMode(active) {
  state.addMode = active;
  document.querySelector(".map-stage").classList.toggle("is-adding", active);
  elements.mapInstruction.hidden = !active;
  elements.addHospitalButton.disabled = active;
}

function handleMapClick(event) {
  if (!state.addMode) return;
  const { lat, lng } = event.latlng;
  elements.hospitalForm.reset();
  elements.hospitalForm.elements.latitude.value = lat.toFixed(6);
  elements.hospitalForm.elements.longitude.value = lng.toFixed(6);
  elements.coordinateDisplay.value = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  elements.hospitalForm.elements.lastInspected.value = new Date().toISOString().slice(0, 10);
  elements.hospitalDialog.showModal();
}

async function submitHospital(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    elements.hospitalDialog.close();
    setAddMode(false);
    return;
  }
  if (!elements.hospitalForm.reportValidity()) return;

  const form = new FormData(elements.hospitalForm);
  try {
    await api("/api/hospitals", {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        lastInspected: form.get("lastInspected"),
        latitude: Number(form.get("latitude")),
        longitude: Number(form.get("longitude")),
        userId: state.userId
      })
    });
    elements.hospitalDialog.close();
    setAddMode(false);
    await loadOverview({ fit: true });
    setActiveLayer("all");
    showToast("Hospital added to the demo map.");
  } catch (error) {
    showToast(error.message, true);
  }
}

function openReportDialog() {
  if (!state.selectedFeature) return;
  elements.reportForm.reset();
  elements.reportHospitalName.textContent = state.selectedFeature.properties.name;
  elements.reportDialog.showModal();
}

async function submitReport(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    elements.reportDialog.close();
    return;
  }
  if (!elements.reportForm.reportValidity() || !state.selectedFeature) return;

  const form = new FormData(elements.reportForm);
  const observations = {};
  for (const field of ["cleanlinessScore", "queueWaitMinutes"]) {
    const value = form.get(field);
    if (typeof value === "string" && value.trim()) observations[field] = Number(value);
  }
  try {
    const result = await api("/api/reports", {
      method: "POST",
      body: JSON.stringify({
        hospitalId: state.selectedFeature.properties.id,
        queueLengthId: Number(form.get("queueLengthId")),
        cleanliness: form.get("cleanliness"),
        userId: state.userId,
        ...observations
      })
    });
    elements.reportDialog.close();
    const selectedId = state.selectedFeature.properties.id;
    await loadOverview();
    const refreshed = state.allFeatures.find((feature) => feature.properties.id === selectedId);
    if (refreshed) await selectHospital(refreshed);
    showToast(`Report saved. Previous queue: ${result.previousQueueDescription}.`);
  } catch (error) {
    showToast(error.message, true);
  }
}

function distanceInMetres(latitudeA, longitudeA, latitudeB, longitudeB) {
  const toRadians = (value) => (value * Math.PI) / 180;
  const radius = 6371000;
  const latitudeDelta = toRadians(latitudeB - latitudeA);
  const longitudeDelta = toRadians(longitudeB - longitudeA);
  const a = Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(toRadians(latitudeA)) * Math.cos(toRadians(latitudeB)) *
    Math.sin(longitudeDelta / 2) ** 2;
  return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function checkProximity() {
  if (state.proximitySamples.length < 5) return;
  const nearby = state.allFeatures.find((feature) => {
    const [longitude, latitude] = feature.geometry.coordinates;
    return state.proximitySamples.every((sample) =>
      distanceInMetres(sample.latitude, sample.longitude, latitude, longitude) <= 25
    );
  });
  if (nearby) {
    showToast(`You are near ${nearby.properties.name}. A queue report would help other visitors.`);
    state.proximitySamples = [];
  }
}

function toggleProximityMonitoring() {
  if (!elements.proximityToggle.checked) {
    if (state.watchId !== null) navigator.geolocation.clearWatch(state.watchId);
    state.watchId = null;
    state.proximitySamples = [];
    return;
  }
  if (!navigator.geolocation) {
    elements.proximityToggle.checked = false;
    showToast("Geolocation is not supported by this browser.", true);
    return;
  }
  state.watchId = navigator.geolocation.watchPosition((position) => {
    const sample = { latitude: position.coords.latitude, longitude: position.coords.longitude };
    state.proximitySamples.push(sample);
    state.proximitySamples = state.proximitySamples.slice(-5);
    showLocation(sample.latitude, sample.longitude);
    checkProximity();
  }, () => {
    elements.proximityToggle.checked = false;
    toggleProximityMonitoring();
    showToast("Location permission is required for nearby prompts.", true);
  }, { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 });
}

function formatDate(value, includeTime) {
  if(!value)return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit" } : {})
  }).format(date);
}

function showToast(message, isError = false) {
  window.clearTimeout(state.toastTimer);
  elements.toastMessage.textContent = message;
  elements.toast.classList.toggle("error", isError);
  elements.toast.hidden = false;
  state.toastTimer = window.setTimeout(() => { elements.toast.hidden = true; }, 4500);
}

function bindEvents() {
  document.querySelectorAll("[data-layer]").forEach((button) => {
    button.addEventListener("click", async () => {
      await changeLayer(button.dataset.layer);
      setMobileControls(false);
    });
  });
  elements.refreshButton.addEventListener("click", async () => {
    try {
      await loadOverview();
      setActiveLayer("all");
      showToast("Map data refreshed.");
    } catch (error) { showToast(error.message, true); }
  });
  elements.locateButton.addEventListener("click", locateUser);
  elements.mobileControlsButton.addEventListener("click", () => {
    setMobileControls(!elements.controlRail.classList.contains("open"));
  });
  elements.addHospitalButton.addEventListener("click", () => setAddMode(true));
  elements.cancelAddButton.addEventListener("click", () => setAddMode(false));
  elements.closeDetailButton.addEventListener("click", closeDetail);
  elements.reportButton.addEventListener("click", openReportDialog);
  elements.hospitalForm.addEventListener("submit", submitHospital);
  elements.reportForm.addEventListener("submit", submitReport);
  elements.proximityToggle.addEventListener("change", toggleProximityMonitoring);
}

async function initialise() {
  cacheElements();
  initialiseMap();
  bindEvents();
  lucide.createIcons();
  try {
    await loadOverview({ fit: true });
    if(window.QueueLensAgentUI)await window.QueueLensAgentUI.initialise({host:document.getElementById("agentPanel"),adapter:leafletAgentAdapter(),getLocation:()=>Date.now()-state.locationAt<300000?state.currentLocation:null});
  } catch (error) {
    showToast(`Unable to load the application: ${error.message}`, true);
  }
}

document.addEventListener("DOMContentLoaded", initialise);

function leafletAgentAdapter(){
  let features=new Map();
  const mark=(ids,ranked=false)=>{for(const [id,marker] of state.markerByHospitalId){const h=features.get(id);const colour=h?.properties.queueColour||state.visibleFeatures.find(f=>f.properties.id===id)?.properties.queueColour||"#087f72";const index=ids.indexOf(id);marker.setIcon(L.divIcon({className:"hospital-div-icon",html:`<span class="hospital-marker ${index>=0?'agent-highlight':''} ${ranked&&index>=0?'agent-ranked':''}" style="--marker-colour:${colour}">${ranked&&index>=0?index+1:''}</span>`,iconSize:[30,30],iconAnchor:[15,28]}));}};
  return {
    prepare(entities){
      features=new Map(entities.map(h=>[h.hospital_id,{type:"Feature",geometry:{type:"Point",coordinates:[h.longitude,h.latitude]},properties:{id:h.hospital_id,name:h.name,queueDescription:h.queue_description,queueColour:state.queueLengths.find(q=>q.description===h.queue_description)?.colour||"#087f72",cleanliness:h.cleanliness_note,latestReportAt:h.latest_report_at,lastInspected:state.allFeatures.find(f=>f.properties.id===h.hospital_id)?.properties.lastInspected||null}}]));
      for(const [id,feature] of features){
        let marker=state.markerByHospitalId.get(id);
        const [lon,lat]=feature.geometry.coordinates;
        if(!marker){
          marker=L.marker([lat,lon],{icon:markerIcon(feature.properties.queueColour),title:feature.properties.name}).addTo(state.hospitalLayer);
          state.markerByHospitalId.set(id,marker);
        }else{
          marker.setLatLng([lat,lon]);
          marker.getElement()?.setAttribute("title",feature.properties.name);
        }
        marker.off("click").on("click",()=>selectHospital(feature));
      }
    },
    filter(ids){renderHospitals({features:ids.map(id=>features.get(id))});},
    fit_bounds(ids){state.map.fitBounds(ids.map(id=>{const [lon,lat]=features.get(id).geometry.coordinates;return[lat,lon];}),{padding:[42,42],maxZoom:15});},
    highlight(ids){mark(ids);},rank(ids){mark(ids,true);},compare(ids){mark(ids);},
    fly_to(id){const[lon,lat]=features.get(id).geometry.coordinates;state.map.flyTo([lat,lon],16);},
    async open_popup(id){const feature=features.get(id),content=document.createElement("div");content.textContent=feature.properties.name;state.markerByHospitalId.get(id)?.bindPopup(content).openPopup();await selectHospital(feature);}
  };
}
