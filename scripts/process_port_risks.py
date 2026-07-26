import os
import glob
from pathlib import Path
import pandas as pd

# Define base project path
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

# Fix 1 & 2: Point to the actual filename (accounting for .csv.csv)
ANCHORAGES = CONFIG_DIR / "gfw_anchorages.csv.csv"
EEZ_GEOJSON = BASE_DIR / "data" / "marine_regions_eez.geojson"
OUTPUT_JSON = BASE_DIR / "data" / "baseline_risk.json"

def load_and_clean_data():
    """Dynamically load and concatenate all port_visit-events CSVs in /config."""
    # Find all port visit CSVs inside /config
    port_files = glob.glob(str(CONFIG_DIR / "port_visit-events-*.csv"))
    
    if not port_files:
        raise FileNotFoundError(f"No port event CSV files found in {CONFIG_DIR}")
        
    print(f"[+] Found {len(port_files)} regional port log files. Merging...")
    
    # Read and merge all regional CSVs into a single DataFrame
    df_list = [pd.read_csv(f) for f in port_files]
    logs = pd.concat(df_list, ignore_index=True)
    
    # Ensure standardized column names (adjust to match your actual CSV columns)
    logs['mmsi'] = logs['mmsi'].astype(str).str.zfill(9)
    if 'arrival_time' in logs.columns and 'departure_time' in logs.columns:
        logs['arrival_time'] = pd.to_datetime(logs['arrival_time'])
        logs['departure_time'] = pd.to_datetime(logs['departure_time'])
        logs['residence_hours'] = (logs['departure_time'] - logs['arrival_time']).dt.total_seconds() / 3600.0
    
    return logs
