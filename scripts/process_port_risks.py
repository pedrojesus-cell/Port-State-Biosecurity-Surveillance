import os
import glob
import sys
import hashlib
import pandas as pd

CONFIG_DIR = "config"
MAX_JSON_RECORDS = 8000

# Representative EEZ Coastal Port Anchors for Spatial Mapping
MARITIME_PORTS = [
    {"port": "Vladivostok Port", "dep": "Busan", "dest": "Niigata", "lat": 43.1155, "lon": 131.8855, "region": "Russian Far East EEZ"},
    {"port": "Murmansk Commercial Port", "dep": "Tromso", "dest": "Kirkenes", "lat": 68.9706, "lon": 33.0749, "region": "Arctic EEZ"},
    {"port": "St. Petersburg Port", "dep": "Tallinn", "dest": "Helsinki", "lat": 59.9311, "lon": 30.2309, "region": "Baltic Sea EEZ"},
    {"port": "Novorossiysk Port", "dep": "Samsun", "dest": "Istanbul", "lat": 44.7244, "lon": 37.7675, "region": "Black Sea EEZ"},
    {"port": "Santos Port Complex", "dep": "Buenos Aires", "dest": "Montevideo", "lat": -23.9608, "lon": -46.3331, "region": "South America EEZ"},
    {"port": "Rotterdam Gateway", "dep": "Hamburg", "dest": "Antwerp", "lat": 51.9244, "lon": 4.4777, "region": "European EEZ"}
]

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Found {len(csv_files)} CSV files in '{CONFIG_DIR}/'. Processing GFW summary data...")

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

    for idx, row in df.iterrows():
        # Parse Exact CSV Header Columns from GFW
        vessel_name = str(row.get("name") or row.get("vessel_name") or f"Vessel_{idx}").strip()
        mmsi = str(row.get("mmsi") or row.get("ssvid") or f"273{idx:06d}").strip()
        flag = str(row.get("flag") or row.get("flag_translated") or "RUS").strip()
        vessel_type = str(row.get("gfw_vessel_type") or row.get("vessel_type") or "Merchant/Carrier").strip()

        # Parse total visits count
        try:
            total_visits = float(row.get("total_port_visit_events") or row.get("total_visits") or 10)
        except (ValueError, TypeError):
            total_visits = 10.0

        # Deterministically assign coastal port cluster using MMSI hash
        hash_val = int(hashlib.md5(mmsi.encode('utf-8')).hexdigest(), 16)
        port_info = MARITIME_PORTS[hash_val % len(MARITIME_PORTS)]

        # Calculate Biofouling Risk Score & Accumulated Residence Duration
        # Higher event count = significantly increased biofouling exposure risk
        residence_hrs = round(min(168.0, max(6.0, total_visits * 0.25)), 1)
        
        if total_visits >= 300:
            risk_score = 0.92  # High Risk (Red)
        elif total_visits >= 100:
            risk_score = 0.65  # Moderate Risk (Amber)
        else:
            risk_score = 0.35  # Low Risk (Blue)

        # Generate slight geographic offset per vessel around the port anchor to avoid overlap
        offset_lat = port_info["lat"] + ((hash_val % 100) - 50) * 0.005
        offset_lon = port_info["lon"] + (((hash_val // 100) % 100) - 50) * 0.005

        record = {
            "mmsi": mmsi,
            "vesselName": vessel_name,
            "flag": flag,
            "vesselType": vessel_type if vessel_type.lower() != "other" else "Carrier/Merchant",
            "region": port_info["region"],
            "portName": port_info["port"],
            "portOfDeparture": port_info["dep"],
            "portOfDestination": port_info["dest"],
            "residenceHours": residence_hrs,
            "biosecurityRiskScore": risk_score,
            "totalEvents": int(total_visits),
            "vesselPos": [round(offset_lat, 4), round(offset_lon, 4)],
            "routeCoordinates": [
                [round(offset_lat + 1.2, 4), round(offset_lon - 2.1, 4)],
                [round(offset_lat, 4), round(offset_lon, 4)],
                [round(offset_lat - 1.5, 4), round(offset_lon + 2.5, 4)]
            ]
        }
        processed_records.append(record)

    processed_records.sort(key=lambda x: x["biosecurityRiskScore"], reverse=True)
    final_records = processed_records[:MAX_JSON_RECORDS]

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_records).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Ingested GFW summary records and exported {len(final_records)} mapped entries to data/baseline_risk.json.")

if __name__ == "__main__":
    process_all_config_csvs()
