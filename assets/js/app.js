// assets/js/app.js

async function loadBiosecurityData() {
  // Use relative path from the root index.html location
  const DATA_URL = 'data/baseline_risk.json';

  try {
    const response = await fetch(DATA_URL);
    
    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }
    
    const portData = await response.json();
    console.log(`Successfully loaded ${portData.length} port records.`, portData);
    
    // Initialize your map or visualization here
    renderMap(portData);

  } catch (error) {
    console.error('Error loading baseline_risk.json:', error);
  }
}

document.addEventListener('DOMContentLoaded', loadBiosecurityData);
