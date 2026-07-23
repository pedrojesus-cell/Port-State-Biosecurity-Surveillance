// Initialize Leaflet Map
const map = L.map('map', { zoomControl: true, minZoom: 2 }).setView([10.0, -20.0], 3);

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; OpenStreetMap &copy; CARTO',
  subdomains: 'abcd',
  maxZoom: 19
}).addTo(map);

let allVessels = [];
let markersLayer = L.layerGroup().addTo(map);
let trajectoryLayer = L.layerGroup().addTo(map);

function isValidNum(v) {
  return v !== null && v !== undefined && !isNaN(parseFloat(v));
}

// Robust Multi-Path Fetch Engine for GitHub Pages
async function loadBiosecurityData() {
  const possiblePaths = [
    './data/baseline_risk.json',
    'data/baseline_risk.json',
    '/Port-State-Biosecurity-Surveillance/data/baseline_risk.json'
  ];

  for (let path of possiblePaths) {
    try {
      const response = await fetch(`${path}?t=${new Date().getTime()}`);
      if (response.ok) {
        allVessels = await response.json();
        if (Array.isArray(allVessels) && allVessels.length > 0) {
          console.log(`Successfully loaded ${allVessels.length} records from: ${path}`);
          renderDashboard(allVessels);
          return;
        }
      }
    } catch (err) {
      console.warn(`Failed fetching from ${path}:`, err);
    }
  }

  console.error("Could not locate baseline_risk.json across relative paths.");
}

function renderDashboard(records) {
  markersLayer.clearLayers();
  trajectoryLayer.clearLayers();

  let totalHighRisk = 0;
  let totalHours = 0;
  const feedContainer = document.getElementById('risk-feed');
  feedContainer.innerHTML = '';

  const boundsPoints = [];

  records.forEach((rec) => {
    const riskScore = rec.biosecurityRiskScore || 0;
    const riskPct = Math.round(riskScore * 100);
    const isHighRisk = riskScore >= 0.70;

    if (isHighRisk) totalHighRisk++;
    totalHours += parseFloat(rec.residenceHours || 0);

    // Render Circle Marker on Map for every vessel
    if (rec.vesselPos && isValidNum(rec.vesselPos[0]) && isValidNum(rec.vesselPos[1])) {
      const lat = parseFloat(rec.vesselPos[0]);
      const lon = parseFloat(rec.vesselPos[1]);
      boundsPoints.push([lat, lon]);

      const marker = L.circleMarker([lat, lon], {
        radius: isHighRisk ? 6 : 4,
        fillColor: isHighRisk ? '#ef4444' : '#38bdf8',
        color: '#ffffff',
        weight: 1,
        fillOpacity: 0.85
      });

      marker.bindPopup(getPopupHtml(rec));
      marker.on('click', () => drawVesselTrajectory(rec));
      markersLayer.addLayer(marker);
    }

    // Render Sidebar Card
    const card = document.createElement('div');
    card.className = `p-3 rounded-lg border transition-all cursor-pointer hover:border-cyan-400 ${
      isHighRisk ? 'bg-red-950/20 border-red-900/50' : 'bg-slate-800/40 border-slate-800'
    }`;

    card.innerHTML = `
      <div class="flex justify-between items-start mb-1">
        <span class="font-bold text-xs text-slate-200">${rec.vesselName} <span class="text-slate-400">[${rec.flag}]</span></span>
        <span class="text-xs font-bold ${isHighRisk ? 'text-red-400' : 'text-amber-400'}">${riskPct}% Risk</span>
      </div>
      <div class="text-[11px] text-slate-400 space-y-0.5">
        <div><span class="text-slate-500">Port Visited:</span> <span class="text-slate-200 font-semibold">${rec.portName || 'Regional Port'}</span></div>
        <div><span class="text-slate-500">Route:</span> ${rec.portOfDeparture || 'Origin'} &rarr; ${rec.portOfDestination || 'Destination'}</div>
        <div><span class="text-slate-500">Characteristics:</span> <span class="text-cyan-400">${rec.vesselType || 'Carrier'}</span> | <span class="text-slate-300">${rec.residenceHours} hrs</span></div>
      </div>
    `;

    card.addEventListener('click', () => drawVesselTrajectory(rec));
    feedContainer.appendChild(card);
  });

  // Auto-zoom map bounds to fit markers on initial load
  if (boundsPoints.length > 0) {
    map.fitBounds(L.latLngBounds(boundsPoints), { padding: [30, 30] });
  }

  document.getElementById('kpi-total-visits').innerText = records.length;
  document.getElementById('kpi-high-risk').innerText = totalHighRisk;
  document.getElementById('kpi-avg-residence').innerHTML = `${(totalHours / (records.length || 1)).toFixed(1)} <span class="text-xs font-normal">hrs</span>`;
}

// DRAW COMPLETE 2025 VOYAGE TRAJECTORY
function drawVesselTrajectory(vessel) {
  trajectoryLayer.clearLayers();

  const mmsiTarget = String(vessel.mmsi);
  const nameTarget = String(vessel.vesselName);

  const vesselEvents = allVessels.filter(v => 
    (v.mmsi && String(v.mmsi) === mmsiTarget) || (v.vesselName && String(v.vesselName) === nameTarget)
  );

  const routePoints = [];

  vesselEvents.forEach((evt, idx) => {
    if (evt.routeCoordinates && Array.isArray(evt.routeCoordinates)) {
      evt.routeCoordinates.forEach(pt => {
        if (pt && isValidNum(pt[0]) && isValidNum(pt[1])) {
          routePoints.push([parseFloat(pt[0]), parseFloat(pt[1])]);
        }
      });
    } else if (evt.vesselPos && isValidNum(evt.vesselPos[0]) && isValidNum(evt.vesselPos[1])) {
      routePoints.push([parseFloat(evt.vesselPos[0]), parseFloat(evt.vesselPos[1])]);
    }

    if (evt.vesselPos && isValidNum(evt.vesselPos[0]) && isValidNum(evt.vesselPos[1])) {
      const pLat = parseFloat(evt.vesselPos[0]);
      const pLon = parseFloat(evt.vesselPos[1]);

      const portMarker = L.circleMarker([pLat, pLon], {
        radius: 8,
        fillColor: '#06b6d4',
        color: '#ffffff',
        weight: 2,
        fillOpacity: 1
      });

      portMarker.bindPopup(`
        <div class="p-1 text-xs">
          <div class="font-bold text-cyan-300 text-sm mb-1">${evt.vesselName} (${evt.flag})</div>
          <div><b>2025 Port Stop #${idx + 1}:</b> ${evt.portName}</div>
          <div><b>Origin:</b> ${evt.portOfDeparture}</div>
          <div><b>Destination:</b> ${evt.portOfDestination}</div>
          <div><b>Residence Time:</b> ${evt.residenceHours} hrs</div>
          <div><b>Vessel Type:</b> ${evt.vesselType}</div>
        </div>
      `);

      trajectoryLayer.addLayer(portMarker);
    }
  });

  if (routePoints.length > 1) {
    const polyline = L.polyline(routePoints, {
      color: '#38bdf8',
      weight: 3,
      opacity: 0.9,
      dashArray: '6, 8'
    });
    trajectoryLayer.addLayer(polyline);
    map.fitBounds(polyline.getBounds(), { padding: [50, 50] });
  } else if (routePoints.length === 1) {
    map.setView(routePoints[0], 7, { animate: true });
  }
}

function getPopupHtml(rec) {
  return `
    <div class="p-1 text-xs">
      <div class="font-bold text-sm text-cyan-300 mb-1">${rec.vesselName} (${rec.flag})</div>
      <div><b>MMSI:</b> ${rec.mmsi}</div>
      <div><b>Vessel Type:</b> ${rec.vesselType || 'Merchant/Carrier'}</div>
      <div><b>Port Visited:</b> ${rec.portName}</div>
      <div><b>Origin Port:</b> ${rec.portOfDeparture}</div>
      <div><b>Destination Port:</b> ${rec.portOfDestination}</div>
      <div><b>Residence Duration:</b> ${rec.residenceHours} hrs</div>
      <div class="mt-2 pt-2 border-t border-slate-700 flex justify-between items-center">
        <span class="font-bold ${rec.biosecurityRiskScore >= 0.7 ? 'text-red-400' : 'text-amber-400'}">
          Bio-Risk: ${Math.round((rec.biosecurityRiskScore || 0) * 100)}%
        </span>
        <button onclick="generateVessel2025Report('${rec.mmsi}', '${rec.vesselName}')" 
          class="px-2 py-1 bg-cyan-600 hover:bg-cyan-500 text-white text-[10px] rounded font-bold transition-colors">
          📄 2025 PDF Report
        </button>
      </div>
    </div>
  `;
}

// GENERATE 2025 BIOSECURITY PDF REPORT
function generateVessel2025Report(mmsi, vesselName) {
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();

  const visits = allVessels.filter(v => String(v.mmsi) === String(mmsi) || v.vesselName === vesselName);
  const main = visits[0] || {};

  doc.setFillColor(15, 23, 42);
  doc.rect(0, 0, 210, 297, 'F');

  doc.setTextColor(56, 189, 248);
  doc.setFontSize(18);
  doc.text("BIOSECURITY & PORT SURVEILLANCE REPORT (2025)", 14, 20);

  doc.setTextColor(241, 245, 249);
  doc.setFontSize(12);
  doc.text(`Vessel Name: ${vesselName}`, 14, 32);
  doc.text(`MMSI: ${mmsi}`, 14, 40);
  doc.text(`Flag: ${main.flag || 'UNK'}`, 14, 48);
  doc.text(`Vessel Type: ${main.vesselType || 'Merchant/Carrier'}`, 14, 56);

  doc.setDrawColor(51, 65, 85);
  doc.line(14, 62, 196, 62);

  doc.setFontSize(14);
  doc.setTextColor(56, 189, 248);
  doc.text("2025 Port Visit History & Vector Characteristics", 14, 72);

  let y = 82;
  doc.setFontSize(10);
  doc.setTextColor(203, 213, 225);

  visits.forEach((v, idx) => {
    if (y > 270) { doc.addPage(); y = 20; }
    doc.text(`${idx + 1}. Port: ${v.portName} | Residence: ${v.residenceHours} hrs | Route: ${v.portOfDeparture} -> ${v.portOfDestination}`, 14, y);
    y += 8;
  });

  y += 10;
  doc.setDrawColor(51, 65, 85);
  doc.line(14, y, 196, y);
  y += 12;

  doc.setFontSize(12);
  doc.setTextColor(239, 68, 68);
  doc.text(`Biofouling Risk Index: ${Math.round((main.biosecurityRiskScore || 0.5) * 100)}%`, 14, y);

  doc.save(`${vesselName.replace(/[^a-zA-Z0-9]/g, '_')}_2025_Biosecurity_Report.pdf`);
}

// Search Filter
document.getElementById('search-input').addEventListener('input', (e) => {
  const q = e.target.value.toLowerCase().trim();
  if (!q) { renderDashboard(allVessels); return; }

  const filtered = allVessels.filter(v => 
    (v.vesselName && v.vesselName.toLowerCase().includes(q)) ||
    (v.mmsi && String(v.mmsi).toLowerCase().includes(q)) ||
    (v.portName && v.portName.toLowerCase().includes(q)) ||
    (v.flag && v.flag.toLowerCase().includes(q))
  );
  renderDashboard(filtered);
});

// Initial Load
loadBiosecurityData();
