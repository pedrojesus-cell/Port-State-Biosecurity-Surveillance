document.addEventListener("DOMContentLoaded", () => {
  const map = L.map("map").setView([15.0, 10.0], 2);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; OpenStreetMap &copy; CARTO &copy; Global Fishing Watch',
    maxZoom: 18
  }).addTo(map);

  fetch("data/baseline_risk.json")
    .then(res => res.json())
    .then(data => {
      renderDashboard(data, map);
    })
    .catch(err => {
      console.warn("Baseline data unavailable, rendering fallback data.", err);
      renderDashboard(getFallbackData(), map);
    });
});

function renderDashboard(records, map) {
  let totalHighRisk = 0;
  let totalResidence = 0;
  const feedContainer = document.getElementById("event-feed");
  feedContainer.innerHTML = ""; // Clear existing feed

  records.forEach(rec => {
    totalResidence += rec.residenceHours;
    const isHighRisk = rec.biosecurityRiskScore >= 0.7;
    if (isHighRisk) totalHighRisk++;

    const color = isHighRisk ? "#ef4444" : rec.biosecurityRiskScore >= 0.4 ? "#f59e0b" : "#10b981";

    if (rec.lat && rec.lon) {
      const circle = L.circleMarker([rec.lat, rec.lon], {
        radius: isHighRisk ? 8 : 5,
        fillColor: color,
        color: "#fff",
        weight: 1,
        fillOpacity: 0.8
      }).addTo(map);

      circle.bindPopup(`
        <div style="color:#0f172a; font-family:sans-serif;">
          <h3 style="font-weight:bold;">${rec.vesselName} (${rec.flag})</h3>
          <p><b>Port:</b> ${rec.portName}</p>
          <p><b>Departure:</b> ${rec.portOfDeparture || 'N/A'}</p>
          <p><b>Destination:</b> ${rec.portOfDestination || 'N/A'}</p>
          <p><b>ETA:</b> ${rec.eta || 'N/A'}</p>
          <p><b>In-Port Duration:</b> ${Number(rec.residenceHours).toFixed(1)} hrs</p>
          <p><b>Fouling Risk:</b> ${(rec.biosecurityRiskScore * 100).toFixed(0)}%</p>
        </div>
      `);
    }

    // Updated Feed Card Format
    const card = document.createElement("div");
    card.className = "p-3 bg-slate-900 border border-slate-700 rounded-lg text-xs space-y-1.5";
    card.innerHTML = `
      <div class="flex justify-between font-bold text-slate-200">
        <span>${rec.vesselName} [${rec.flag}]</span>
        <span style="color: ${color}">${(rec.biosecurityRiskScore * 100).toFixed(0)}% Risk</span>
      </div>
      <div class="text-slate-400">Current Port: <span class="text-slate-200 font-medium">${rec.portName}</span></div>
      <div class="text-slate-400">Port of Departure: <span class="text-slate-300">${rec.portOfDeparture || 'N/A'}</span></div>
      <div class="text-slate-400">In-Port Duration: <span class="text-teal-400 font-semibold">${Number(rec.residenceHours).toFixed(1)} hrs</span></div>
      <div class="text-slate-400">Port of Destination: <span class="text-slate-300">${rec.portOfDestination || 'N/A'}</span></div>
      <div class="text-slate-400">ETA: <span class="text-amber-300">${rec.eta || 'N/A'}</span></div>
    `;
    feedContainer.appendChild(card);
  });

  document.getElementById("kpi-total-entries").textContent = records.length;
  document.getElementById("kpi-high-risk").textContent = totalHighRisk;
  document.getElementById("kpi-avg-residence").textContent = records.length 
    ? (totalResidence / records.length).toFixed(1) 
    : 0;
}
