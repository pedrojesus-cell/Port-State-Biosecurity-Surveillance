import os
import glob
import sys
import pandas as pd

CONFIG_DIR = "config"
MAX_JSON_RECORDS = 8000

def clean_float(val):
    try:
        if pd.notnull(val):
            return float(val)
    except (ValueError, TypeError):
        pass
    return None

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Found {len(csv_files)} CSV files in '{CONFIG_DIR}/'. Ingesting...")

    all_dfs = []
    for f in csv_files:
        try:
            temp_df = pd.read_csv(f, low_memory=False)
            all_dfs.append(temp_df)
        except Exception as e:
            print(f"Error reading {f}: {e}")

    if not all_dfs:
        sys.exit(1)

    df = pd.concat(all_dfs, ignore_index=True)
    df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

    processed_records = []

    for _, row in df.iterrows():
        mmsi = str(row.get("ssvid") or row.get("mmsi") or "").strip()
        vessel_name = str(row.get("vessel_name") or row.get("shipname") or row.get("name") or f"MMSI {mmsi}")
        flag = str(row.get("flag") or row.get("country") or "UNK")
        vessel_type = str(row.get("vessel_type") or row.get("geartype") or "Merchant/Carrier")

        port_name = str(row.get("port_label") or row.get("port_name") or row.get("port") or "Regional Port")
        dep_port = str(row.get("departure_port_label") or row.get("departure_port") or "Origin Port")
        dest_port = str(row.get("destination_port_label") or row.get("destination_port") or "Destination Port")

        # Extract coordinates with fallback options
        lat = clean_float(row.get("lat") or row.get("latitude") or row.get("port_lat") or row.get("position_lat"))
        lon = clean_float(row.get("lon") or row.get("longitude") or row.get("port_lon") or row.get("position_lon"))

        dep_lat = clean_float(row.get("departure_lat") or row.get("dep_lat"))
        dep_lon = clean_float(row.get("departure_lon") or row.get("dep_lon"))

        dest_lat = clean_float(row.get("destination_lat") or row.get("dest_lat"))
        dest_lon = clean_float(row.get("destination_lon") or row.get("dest_lon"))

        residency = float(row.get("duration_hrs") or row.get("residence_hours") or row.get("durationhrs") or 24.0)
        risk_score = 0.85 if residency > 48 else (0.50 if residency > 12 else 0.20)

        record = {
            "mmsi": mmsi,
            "vesselName": vessel_name,
            "flag": flag,
            "vesselType": vessel_type,
            "region": "Monitored Corridor",
            "portName": port_name,
            "portOfDeparture": dep_port,
            "portOfDestination": dest_port,
            "residenceHours": round(residency, 1),
            "biosecurityRiskScore": risk_score,
            "vesselPos": [lat, lon] if lat is not null and lon is not null else [dep_lat or -15.0, dep_lon or -45.0],
            "routeCoordinates": [
                [dep_lat, dep_lon] if dep_lat and dep_lon else None,
                [lat, lon] if lat and lon else None,
                [dest_lat, dest_lon] if dest_lat and dest_lon else None
            ]
        }
        processed_records.append(record)

    processed_records.sort(key=lambda x: x["biosecurityRiskScore"], reverse=True)
    final_records = processed_records[:MAX_JSON_RECORDS]

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_records).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Exported {len(final_records)} records to data/baseline_risk.json.")

if __name__ == "__main__":
    process_all_config_csvs()
