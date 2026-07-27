// Initialize Leaflet Map
const map = L.map('map', { zoomControl: true, minZoom: 2 }).setView([20.0, 0.0], 2);

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; OpenStreetMap &copy; CARTO',
  subdomains: 'abcd',
  maxZoom: 19
}).addTo(map);

let allPorts = [];
let markersLayer = L.layerGroup().addTo(map);

function isValidNum(v) {
  return v !== null && v !== undefined && !isNaN(parseFloat(v));
}

// Color coding for Port Markers
function getPortColor(highRiskCount, moderateRiskCount) {
  if (highRiskCount > 0) return '#ef4444';     // Red: Contains High Fouling Risk (>=70%)
  if (moderateRiskCount > 0) return '#f59e0b'; // Amber: Contains Moderate Vectors (40%-69%)
  return '#38bdf8';                            // Blue: Low Risk Only
}

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
        allPorts = await response.json();
        if (Array.isArray(allPorts) && allPorts.length > 0) {
          renderDashboard(allPorts);
          return;
        }
      }
    } catch (err) {
      console.warn(`Failed fetching from ${path}:`, err);
    }
  }
}

function renderDashboard(portRecords) {
  markersLayer.clearLayers();

  let globalHighRisk = 0;
  let globalVisits = 0;
  let totalHoursSum = 0;
  let totalVesselsCount = 0;

  const feedContainer = document.getElementById('risk-feed');
  feedContainer.innerHTML = '';

  const boundsPoints = [];

  portRecords.forEach((port) => {
    globalHighRisk += port.highRiskCount || 0;
    globalVisits += port.totalPortVisits || 0;

    const portColor = getPortColor(port.highRiskCount, port.moderateRiskCount);

    if (port.location && isValidNum(port.location[0]) && isValidNum(port.location[1])) {
      const lat = parseFloat(port.location[0]);
      const lon = parseFloat(port.location[1]);
      boundsPoints.push([lat, lon]);

      // Calculate radius dynamically based on visit volume
      const radiusSize = Math.min(18, Math.max(8, Math.sqrt(port.totalPortVisits) * 1.5));

      const marker = L.circleMarker([lat, lon], {
        radius: radiusSize,
        fillColor: portColor,
        color: '#ffffff',
        weight: 1.5,
        fillOpacity: 0.85
      });

      marker.bindPopup(getPortPopupHtml(port));
      markersLayer.addLayer(marker);
    }

    // Render Port Summary Card in Sidebar
    const card = document.createElement('div');
    card.className = `p-3 rounded-lg border transition-all cursor-pointer hover:border-cyan-400 ${
      port.highRiskCount > 0 ? 'bg-red-950/20 border-red-900/50' : 
      port.moderateRiskCount > 0 ? 'bg-amber-950/20 border-amber-900/50' : 'bg-slate-800/40 border-slate-800'
    }`;

    card.innerHTML = `
      <div class="flex justify-between items-start mb-1">
        <span class="font-bold text-xs text-slate-200">${port.portName}</span>
        <span class="text-xs font-bold text-slate-400">2025 Data</span>
      </div>
      <div class="text-[11px] text-slate-400 space-y-1 mt-2">
        <div class="flex justify-between">
          <span>🔴 High Fouling Risk (≥70%):</span>
          <span class="font-bold text-red-400">${port.highRiskCount}</span>
        </div>
        <div class="flex justify-between">
          <span>🟠 Moderate Vectors (40-69%):</span>
          <span class="font-bold text-amber-400">${port.moderateRiskCount}</span>
        </div>
        <div class="flex justify-between border-t border-slate-700/50 pt-1 mt-1 text-slate-300">
          <span>Total Monitored Visits:</span>
          <span class="font-bold text-cyan-400">${port.totalPortVisits}</span>
        </div>
      </div>
    `;

    card.addEventListener('click', () => {
      if (port.location) {
        map.setView([port.location[0], port.location[1]], 6, { animate: true });
      }
    });

    feedContainer.appendChild(card);

    // Sum residence times
    if (port.vessels) {
      port.vessels.forEach(v => {
        totalHoursSum += v.residenceHours || 0;
        totalVesselsCount++;
      });
    }
  });

  if (boundsPoints.length > 0) {
    map.fitBounds(L.latLngBounds(boundsPoints), { padding: [40, 40] });
  }

  document.getElementById('kpi-total-visits').innerText = globalVisits;
  document.getElementById('kpi-high-risk').innerText = globalHighRisk;
  document.getElementById('kpi-avg-residence').innerHTML = `${(totalHoursSum / (totalVesselsCount || 1)).toFixed(1)} <span class="text-xs font-normal">hrs</span>`;
}

function getPortPopupHtml(port) {
  let vesselListHtml = '';
  
  if (port.vessels && port.vessels.length > 0) {
    // Show top 5 highest risk vessels in popup
    const sortedVessels = [...port.vessels].sort((a, b) => b.biosecurityRiskScore - a.biosecurityRiskScore).slice(0, 5);
    vesselListHtml = sortedVessels.map(v => `
      <div class="text-[10px] py-1 border-b border-slate-700/50 flex justify-between items-center">
        <span><b>${v.vesselName}</b> (${v.flag})</span>
        <span class="font-bold ${v.biosecurityRiskScore >= 0.7 ? 'text-red-400' : 'text-amber-400'}">
          ${Math.round(v.biosecurityRiskScore * 100)}%
        </span>
      </div>
    `).join('');
  }

  return `
    <div class="p-1 text-xs max-w-xs">
      <div class="font-bold text-sm text-cyan-300 mb-1">${port.portName} (2025)</div>
      <div class="space-y-0.5 my-2 text-[11px]">
        <div class="text-red-400 font-semibold">🔴 High Fouling Risk (≥70%): ${port.highRiskCount} vessels</div>
        <div class="text-amber-400 font-semibold">🟠 Moderate Vectors (40-69%): ${port.moderateRiskCount} vessels</div>
        <div class="text-slate-300">🔵 Low Risk (<40%): ${port.lowRiskCount} vessels</div>
      </div>
      <div class="mt-2 pt-2 border-t border-slate-700">
        <div class="font-bold text-slate-300 mb-1">Recorded Vessel Samples:</div>
        ${vesselListHtml}
      </div>
      <div class="mt-2 pt-2 border-t border-slate-700 text-right">
        <button onclick="generatePort2025Report('${port.portName}')" 
          class="px-2 py-1 bg-cyan-600 hover:bg-cyan-500 text-white text-[10px] rounded font-bold transition-colors">
          📄 Download 2025 Port PDF
        </button>
      </div>
    </div>
  `;
}

function generatePort2025Report(portName) {
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();

  const portData = allPorts.find(p => p.portName === portName) || {};
  const vessels = portData.vessels || [];

  doc.setFillColor(15, 23, 42);
  doc.rect(0, 0, 210, 297, 'F');

  doc.setTextColor(56, 189, 248);
  doc.setFontSize(16);
  doc.text(`PORT BIOSECURITY SURVEILLANCE REPORT (2025)`, 14, 20);

  doc.setTextColor(241, 245, 249);
  doc.setFontSize(12);
  doc.text(`Port: ${portName}`, 14, 30);
  doc.text(`Total Recorded Visits: ${portData.totalPortVisitEvents || portData.totalPortVisits || 0}`, 14, 38);
  doc.text(`High Fouling Risk Vessels (>=70%): ${portData.highRiskCount || 0}`, 14, 46);
  doc.text(`Moderate Vector Vessels (40-69%): ${portData.moderateRiskCount || 0}`, 14, 54);

  doc.setDrawColor(51, 65, 85);
  doc.line(14, 60, 196, 60);

  doc.setFontSize(12);
  doc.setTextColor(56, 189, 248);
  doc.text("2025 Recorded Vessel Breakdown", 14, 70);

  let y = 80;
  doc.setFontSize(9);
  doc.setTextColor(203, 213, 225);

  vessels.forEach((v, idx) => {
    if (y > 270) { doc.addPage(); y = 20; }
    doc.text(`${idx + 1}. ${v.vesselName} | Flag: ${v.flag} | Residence: ${v.residenceHours} hrs | Bio-Risk: ${Math.round(v.biosecurityRiskScore * 100)}% (${v.riskCategory})`, 14, y);
    y += 7;
  });

  doc.save(`${portName.replace(/[^a-zA-Z0-9]/g, '_')}_2025_Port_Report.pdf`);
}

document.getElementById('search-input').addEventListener('input', (e) => {
  const q = e.target.value.toLowerCase().trim();
  if (!q) { renderDashboard(allPorts); return; }

  const filtered = allPorts.filter(p => 
    p.portName && p.portName.toLowerCase().includes(q)
  );
  renderDashboard(filtered);
});

loadBiosecurityData();
