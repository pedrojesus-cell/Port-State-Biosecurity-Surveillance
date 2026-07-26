import os
import json
import glob
import pandas as pd
import geopandas as gpd
from pathlib import Path
from datetime import datetime, timezone

# Resolve base directories
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DOCS_DATA_DIR = BASE_DIR / "docs" / "data"

# Auto-detect gfw_anchorages with single or double extension
ANCHORAGE_FILE = CONFIG_DIR / "gfw_anchorages.csv.csv"
if not ANCHORAGE_FILE.exists():
    ANCHORAGE_FILE = CONFIG_DIR / "gfw_anchorages.csv"

EEZ_GEOJSON = CONFIG_DIR / "marine_regions_eez.geojson"
OUTPUT_JSON = DOCS_DATA_DIR / "baseline_risk.json"


def load_and_standardize_gfw_data():
    """Load and unify GFW port_visit-events files from /config."""
    port_pattern = str(CONFIG_DIR / "port_visit-events-*.csv")
    port_files = glob.glob(port_pattern)

    if not port_files:
        raise FileNotFoundError(f"No files matching 'port_visit-events-*.csv' found in {CONFIG_DIR}")

    print(f"[+] Found {len(port_files)} GFW port visit log files. Processing...")

    dfs = []
    for filepath in port_files:
        try:
            df = pd.read_csv(filepath)
            dfs.append(df)
        except Exception as e:
            print(f"[!] Warning: Could not read {filepath}: {e}")

    if not dfs:
        raise ValueError("No valid data frames were loaded.")

    merged = pd.concat(dfs, ignore_index=True)

    # Map GFW column aliases to standard schema
    col_map = {
        'ssvid': 'mmsi',
        'vessel_id': 'mmsi',
        'ship_name': 'vessel_name',
        'vessel_label': 'vessel_name',
        'lat': 'latitude',
        'start_lat': 'latitude',
        'anchorage_lat': 'latitude',
        'lon': 'longitude',
        'start_lon': 'longitude',
        'anchorage_lon': 'longitude',
        'duration_hours': 'residence_hours',
        'duration_hrs': 'residence_hours'
    }
    merged.rename(columns=col_map, inplace=True)

    # Standardize MMSI
    if 'mmsi' in merged.columns:
        merged['mmsi'] = merged['mmsi'].astype(str).str.split('.').str[0].str.zfill(9)
    else:
        merged['mmsi'] = "UNKNOWN"

    # Standardize Vessel Name
    if 'vessel_name' not in merged.columns:
        merged['vessel_name'] = "Unidentified Vessel"

    # Calculate residence time if start/end timestamps are present
    if 'residence_hours' not in merged.columns:
        if 'start_timestamp' in merged.columns and 'end_timestamp' in merged.columns:
            start = pd.to_datetime(merged['start_timestamp'], errors='coerce')
            end = pd.to_datetime(merged['end_timestamp'], errors='coerce')
            merged['residence_hours'] = (end - start).dt.total_seconds() / 3600.0
        else:
            merged['residence_hours'] = 48.0  # Default baseline assumption

    # Ensure coordinates exist and are numeric
    merged['latitude'] = pd.to_numeric(merged.get('latitude'), errors='coerce')
    merged['longitude'] = pd.to_numeric(merged.get('longitude'), errors='coerce')

    # Drop rows without valid coordinates
    clean_df = merged.dropna(subset=['latitude', 'longitude']).copy()
    print(f"[+] Successfully standardized {len(clean_df)} vessel event records.")
    return clean_df


def calculate_biosecurity_risk(row):
    """Calculate normalized hull fouling risk score [0.0 - 1.0]."""
    residence = float(row.get('residence_hours', 24.0))
    mgps_active = bool(row.get('mgps_installed', False))
    days_since_service = float(row.get('days_since_last_mgps_service', 180))

    # Residence risk factor (168h = 1 week baseline)
    base_score = min(1.0, max(0.05, residence / 168.0))

    # Maintenance modifier
    mgps_efficiency = 0.85 if (mgps_active and days_since_service < 180) else 0.20

    # Calculated biofouling risk R
    risk_score = round(min(1.0, max(0.0, base_score * (1.5 - mgps_efficiency))), 3)

    if risk_score >= 0.70:
        category = "High Fouling Risk"
    elif risk_score >= 0.35:
        category = "Moderate Vector"
    else:
        category = "Low Risk"

    return pd.Series([risk_score, category], index=['risk_score', 'risk_category'])


def main():
    print("[+] Starting GFW Biosecurity Processing Engine...")

    # 1. Ingest GFW data
    df = load_and_standardize_gfw_data()

    # 2. Compute Biosecurity Metrics
    risk_metrics = df.apply(calculate_biosecurity_risk, axis=1)
    df[['risk_score', 'risk_category']] = risk_metrics

    # 3. Build JSON Output
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_vessels_assessed": len(df),
        "vessels": []
    }

    for _, r in df.iterrows():
        output["vessels"].append({
            "mmsi": str(r["mmsi"]),
            "vessel_name": str(r["vessel_name"]),
            "flag": str(r.get("flag", "Unknown")),
            "latitude": float(r["latitude"]),
            "longitude": float(r["longitude"]),
            "port_name": str(r.get("anchorage_name", r.get("port_name", "EEZ Anchorage"))),
            "residence_hours": round(float(r.get("residence_hours", 0.0)), 1),
            "mgps_installed": bool(r.get("mgps_installed", False)),
            "risk_score": float(r["risk_score"]),
            "risk_category": str(r["risk_category"])
        })

    # Ensure docs/data/ exists for GitHub Pages
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2)

    print(f"[✓] Pipeline complete. Published dataset to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
