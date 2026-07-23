import os
import glob
import sys
import pandas as pd

CONFIG_DIR = "config"
MAX_JSON_RECORDS = 8000

def clean_float(val):
    try:
        if pd.notnull(val):
            v = float(val)
            if -90.0 <= v <= 90.0:
                return v
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

    print(f"Found {len(csv_files)} CSV files in '{CONFIG_DIR}/'. Processing...")

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

    # Dynamic column mapping to support various GFW export schemas
    for idx, row in df.iterrows():
        mmsi = str(row.get("ssvid") or row.get("mmsi") or row.get("vessel_id") or f"999{idx}").strip()
        vessel_name = str(row.get("vessel_name") or row.get("shipname") or row.get("name") or row.get("vessel_label") or f"Vessel {mmsi}")
        flag = str(row.get("flag") or row.get("country") or row.get("flag_state") or "UNK")
        vessel_type = str(row.get("vessel_type") or row.get("geartype") or row.get("ship_type") or "Carrier/Merchant")

        port_name = str(row.get("port_label") or row.get("port_name") or row.get("port") or row.get("end_port_label") or "Regional Port")
        dep_port = str(row.get("departure_port_label") or row.get("departure_port") or row.get("start_port_label") or "Origin Port")
        dest_port = str(row.get("destination_port_label") or row.get("destination_port") or "Destination Port")

        # Exhaustive coordinate search
        lat = clean_float(row.get("lat") or row.get("latitude") or row.get("port_lat") or row.get("position_lat") or row.get("lat_mean") or row.get("end_lat"))
        lon = clean_float(row.get("lon") or row.get("longitude") or row.get("port_lon") or row.get("position_lon") or row.get("lon_mean") or row.get("end_lon"))

        dep_lat = clean_float(row.get("departure_lat") or row.get("dep_lat") or row.get("start_lat"))
        dep_lon = clean_float(row.get("departure_lon") or row.get("dep_lon") or row.get("start_lon"))

        dest_lat = clean_float(row.get("destination_lat") or row.get("dest_lat"))
        dest_lon = clean_float(row.get("destination_lon") or row.get("dest_lon"))

        final_lat = lat if lat is not None else (dep_lat if dep_lat is not None else -15.0)
        final_lon = lon if lon is not None else (dep_lon if dep_lon is not None else -45.0)

        residency = float(row.get("duration_hrs") or row.get("residence_hours") or row.get("durationhrs") or row.get("hours") or 24.0)
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
            "vesselPos": [final_lat, final_lon],
            "routeCoordinates": [
                [dep_lat, dep_lon] if (dep_lat is not None and dep_lon is not None) else None,
                [final_lat, final_lon],
                [dest_lat, dest_lon] if (dest_lat is not None and dest_lon is not None) else None
            ]
        }
        processed_records.append(record)

    processed_records.sort(key=lambda x: x["biosecurityRiskScore"], reverse=True)
    final_records = processed_records[:MAX_JSON_RECORDS]

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_records).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Exported {len(final_records)} records into data/baseline_risk.json.")

if __name__ == "__main__":
    process_all_config_csvs()
