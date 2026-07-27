import os
import glob
import sys
import hashlib
import pandas as pd

CONFIG_DIR = "config"
MAX_JSON_RECORDS = 8000

# Realistic Maritime Anchors & Waterway Waypoints (Origin -> Port Entry -> Port -> Destination)
MARITIME_PORTS = [
    {
        "port": "Vladivostok Port", "dep": "Busan", "dest": "Niigata", "region": "Russian Far East EEZ",
        "lat": 43.0800, "lon": 131.8700, # Offshore Bay Anchorage
        "waypoints": [[35.18, 129.08], [42.80, 131.50], [43.08, 131.87], [40.00, 135.00], [37.92, 139.04]]
    },
    {
        "port": "Murmansk Commercial Port", "dep": "Tromso", "dest": "Kirkenes", "region": "Arctic EEZ",
        "lat": 69.0200, "lon": 33.0500, # Kola Bay Waterway Anchorage
        "waypoints": [[69.65, 18.96], [70.50, 31.00], [69.25, 33.40], [69.02, 33.05], [69.25, 33.40], [69.73, 30.05]]
    },
    {
        "port": "St. Petersburg Port", "dep": "Tallinn", "dest": "Helsinki", "region": "Baltic Sea EEZ",
        "lat": 59.9000, "lon": 30.1500, # Neva Bay Offshore Anchorage
        "waypoints": [[59.44, 24.75], [59.80, 28.50], [59.90, 30.15], [60.00, 26.00], [60.17, 24.94]]
    },
    {
        "port": "Novorossiysk Port", "dep": "Samsun", "dest": "Istanbul", "region": "Black Sea EEZ",
        "lat": 44.6800, "lon": 37.8000, # Tsemes Bay Marine Area
        "waypoints": [[41.29, 36.33], [43.50, 37.00], [44.68, 37.80], [42.50, 32.00], [41.01, 28.98]]
    },
    {
        "port": "Santos Port Complex", "dep": "Buenos Aires", "dest": "Montevideo", "region": "South America EEZ",
        "lat": -24.0000, "lon": -46.3000, # Santos Offshore Roads
        "waypoints": [[-34.60, -58.38], [-35.00, -54.00], [-24.00, -46.30], [-34.90, -56.16]]
    },
    {
        "port": "Rotterdam Gateway", "dep": "Hamburg", "dest": "Straits of Dover", "region": "European EEZ",
        "lat": 51.9800, "lon": 3.9000, # Maasvlakte Offshore Anchorage
        "waypoints": [[53.90, 8.50], [53.50, 5.00], [52.10, 3.50], [51.98, 3.90], [51.50, 2.50], [51.00, 1.50]]
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

        # Small circular offshore anchorage jitter (prevents artificial square grids)
        angle = (hash_val % 360) * (3.14159 / 180.0)
        dist = ((hash_val % 100) / 100.0) * 0.012

        offshore_lat = round(port_info["lat"] + (dist * 0.8 * (hash_val % 2 or -1)), 4)
        offshore_lon = round(port_info["lon"] + (dist * (hash_val % 3 or -1)), 4)

        # Build trajectory route following water channels
        base_waypoints = port_info["waypoints"]
        route_coords = []
        for wp in base_waypoints:
            route_coords.append([wp[0], wp[1]])

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
            "vesselPos": [offshore_lat, offshore_lon],
            "routeCoordinates": route_coords
        }
        processed_records.append(record)

    processed_records.sort(key=lambda x: x["biosecurityRiskScore"], reverse=True)
    final_records = processed_records[:MAX_JSON_RECORDS]

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_records).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Exported {len(final_records)} records with water channel trajectories.")

if __name__ == "__main__":
    process_all_config_csvs()
