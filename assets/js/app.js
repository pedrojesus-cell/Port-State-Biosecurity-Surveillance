const REGION_BOUNDS = {
  HORMUZ: [[24.5, 54.0], [27.5, 57.5]],
  EU_EEZ: [[34.0, -25.0], [71.0, 40.0]]
};

document.getElementById("region-filter").addEventListener("change", (e) => {
  const selected = e.target.value;
  if (REGION_BOUNDS[selected]) {
    map.fitBounds(REGION_BOUNDS[selected]);
  } else {
    map.setView([15.0, 10.0], 2);
  }
});
