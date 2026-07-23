async function loadBiosecurityData() {
  // Array of potential relative paths for GitHub Pages environments
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
