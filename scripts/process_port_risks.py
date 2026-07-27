import os
import glob
import sys
import pandas as pd

CONFIG_DIR = "config"
MAX_JSON_RECORDS = 8000  # Caps record count to keep baseline_risk.json under ~10-15 MB

TARGET_REGIONS = {
    "Strait of Hormuz": {"min_lat": 24.0, "max_lat": 27.5, "min_lon": 54.0, "max_lon": 58.0},
    "European EEZ": {"min_lat": 48.0, "max_lat": 60.0, "min_lon": -10.0, "max_lon": 12.0},
    "South America EEZ": {"min_lat": -55.0, "max_lat": 12.0, "min_lon": -82.0, "max_lon": -34.0}
}

def match_target_region(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
        for region_name, bounds in TARGET_REGIONS.items():
            if bounds["min_lat"] <= lat <= bounds["max_lat"] and bounds["min_lon"] <= lon <= bounds["max_lon"]:
                return region_name
    except (TypeError, ValueError):
        pass
    return None

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Found {len(csv_files)} GFW EEZ CSV files in '{CONFIG_DIR}/'. Merging...")

    all_dfs = []
    for f in csv_files:
        try:
            temp_df = pd.read_csv(f, low_memory=False)
            all_dfs.append(temp_df)
            print(f" -> Loaded: {os.path.basename(f)} ({len(temp_df)} records)")
        except Exception as e:
            print(f" -> Error reading {f}: {e}")

    if not all_dfs:
        print("ERROR: Could not load data from CSV files.")
        sys.exit(1)

    df = pd.concat(all_dfs, ignore_index=True)
    df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

    processed_records = []

    print("Filtering and calculating biosecurity risks...")
    for _, row in df.iterrows():
        mmsi = str(row.get("ssvid") or row.get("mmsi") or "").strip()
        vessel_name = str(row.get("vessel_name") or row.get("shipname") or row.get("name") or f"MMSI {mmsi}")
        flag = str(row.get("flag") or row.get("country") or "UNK")
        vessel_type = str(row.get("vessel_type") or row.get("geartype") or "Merchant/Carrier")

        port_name = str(row.get("port_label") or row.get("port_name") or row.get("port") or "Regional Port")
        dep_port = str(row.get("departure_port_label") or row.get("departure_port") or "Origin Port")
        dest_port = str(row.get("destination_port_label") or row.get("destination_port") or "Destination Port")

        lat = row.get("lat") or row.get("latitude") or row.get("port_lat")
        lon = row.get("lon") or row.get("longitude") or row.get("port_lon")

        dep_lat = row.get("departure_lat") or row.get("dep_lat")
        dep_lon = row.get("departure_lon") or row.get("dep_lon")

        dest_lat = row.get("destination_lat") or row.get("dest_lat")
        dest_lon = row.get("destination_lon") or row.get("dest_lon")

        residency = float(row.get("duration_hrs") or row.get("residence_hours") or row.get("durationhrs") or 24.0)
        risk_score = 0.85 if residency > 48 else (0.50 if residency > 12 else 0.20)

        matched_region = (
            match_target_region(lat, lon) or 
            match_target_region(dep_lat, dep_lon) or 
            match_target_region(dest_lat, dest_lon) or
            "South America / European Corridor"
        )

        # Filter out extremely low-risk short stays to control output file size
        if residency >= 6.0 or risk_score >= 0.50:
            record = {
                "mmsi": mmsi,
                "vesselName": vessel_name,
                "flag": flag,
                "vesselType": vessel_type,
                "region": matched_region,
                "portName": port_name,
                "portOfDeparture": dep_port,
                "portOfDestination": dest_port,
                "residenceHours": round(residency, 1),
                "biosecurityRiskScore": risk_score,
                "vesselPos": [float(lat), float(lon)] if pd.notnull(lat) and pd.notnull(lon) else None,
                "routeCoordinates": [
                    [float(dep_lat), float(dep_lon)] if pd.notnull(dep_lat) and pd.notnull(dep_lon) else None,
                    [float(lat), float(lon)] if pd.notnull(lat) and pd.notnull(lon) else None,
                    [float(dest_lat), float(dest_lon)] if pd.notnull(dest_lat) and pd.notnull(dest_lon) else None
                ]
            }
            processed_records.append(record)

    # Sort by risk score (highest risk first) and cap to MAX_JSON_RECORDS
    processed_records.sort(key=lambda x: x["biosecurityRiskScore"], reverse=True)
    final_records = processed_records[:MAX_JSON_RECORDS]

    os.makedirs("data", exist_ok=True)
    out_path = "data/baseline_risk.json"
    
    # Save compact JSON without extra whitespace to minimize file size
    pd.DataFrame(final_records).to_json(out_path, orient="records")
    
    file_size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"\nSUCCESS: Exported {len(final_records)} records to '{out_path}' ({file_size_mb:.2f} MB).")

if __name__ == "__main__":
    process_all_config_csvs()
