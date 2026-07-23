import os
import glob
import sys
import hashlib
import pandas as pd

CONFIG_DIR = "config"
MAX_JSON_RECORDS = 8000

# Realistic Maritime Sea Lane Anchors (Origin, Port Stop, Destination, Waypoints)
MARITIME_PORTS = [
    {
        "port": "Vladivostok Port", "dep": "Busan", "dest": "Niigata", "region": "Russian Far East EEZ",
        "lat": 43.1155, "lon": 131.8855,
        "dep_coords": [35.1796, 129.0756], "dest_coords": [37.9161, 139.0364]
    },
    {
        "port": "Murmansk Commercial Port", "dep": "Tromso", "dest": "Kirkenes", "region": "Arctic EEZ",
        "lat": 68.9706, "lon": 33.0749,
        "dep_coords": [69.6492, 18.9553], "dest_coords": [69.7269, 30.0450]
    },
    {
        "port": "St. Petersburg Port", "dep": "Tallinn", "dest": "Helsinki", "region": "Baltic Sea EEZ",
        "lat": 59.9311, "lon": 30.2309,
        "dep_coords": [59.4370, 24.7536], "dest_coords": [60.1699, 24.9384]
    },
    {
        "port": "Novorossiysk Port", "dep": "Samsun", "dest": "Istanbul", "region": "Black Sea EEZ",
        "lat": 44.7244, "lon": 37.7675,
        "dep_coords": [41.2928, 36.3313], "dest_coords": [41.0082, 28.9784]
    },
    {
        "port": "Santos Port Complex", "dep": "Buenos Aires", "dest": "Montevideo", "region": "South America EEZ",
        "lat": -23.9608, "lon": -46.3331,
        "dep_coords": [-34.6037, -58.3816], "dest_coords": [-34.9011, -56.1645]
    },
    {
        "port": "Rotterdam Gateway", "dep": "Hamburg Outer Elbe", "dest": "English Channel Approach", "region": "European EEZ",
        "lat": 51.9244, "lon": 4.4777,
        "dep_coords": [53.9000, 8.5000],  # Offshore North Sea approach
        "dest_coords": [51.0000, 1.5000]   # Offshore Straits of Dover
    }
]

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

    for idx, row in df.iterrows():
        vessel_name = str(row.get("name") or row.get("vessel_name") or f"Vessel_{idx}").strip()
        mmsi = str(row.get("mmsi") or row.get("ssvid") or f"273{idx:06d}").strip()
        flag = str(row.get("flag") or row.get("flag_translated") or "RUS").strip()
        vessel_type = str(row.get("gfw_vessel_type") or row.get("vessel_type") or "Merchant/Carrier").strip()

        try:
            total_visits = float(row.get("total_port_visit_events") or row.get("total_visits") or 10)
        except (ValueError, TypeError):
            total_visits = 10.0

        hash_val = int(hashlib.md5(mmsi.encode('utf-8')).hexdigest(), 16)
        port_info = MARITIME_PORTS[hash_val % len(MARITIME_PORTS)]

        residence_hrs = round(min(168.0, max(6.0, total_visits * 0.25)), 1)
        
        if total_visits >= 300:
            risk_score = 0.92
        elif total_visits >= 100:
            risk_score = 0.65
        else:
            risk_score = 0.35

        # Jitter applied to keep vessels in coastal/anchorage waters
        j_lat = ((hash_val % 100) - 50) * 0.0015
        j_lon = (((hash_val // 100) % 100) - 50) * 0.0015

        current_pos = [round(port_info["lat"] + j_lat, 4), round(port_info["lon"] + j_lon, 4)]
        dep_pos = [round(port_info["dep_coords"][0] + j_lat, 4), round(port_info["dep_coords"][1] + j_lon, 4)]
        dest_pos = [round(port_info["dest_coords"][0] + j_lat, 4), round(port_info["dest_coords"][1] + j_lon, 4)]

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
            "vesselPos": current_pos,
            "routeCoordinates": [dep_pos, current_pos, dest_pos]
        }
        processed_records.append(record)

    processed_records.sort(key=lambda x: x["biosecurityRiskScore"], reverse=True)
    final_records = processed_records[:MAX_JSON_RECORDS]

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_records).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Exported {len(final_records)} records with offshore sea lane routes.")

if __name__ == "__main__":
    process_all_config_csvs()
