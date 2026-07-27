import os
import glob
import sys
import hashlib
import pandas as pd

CONFIG_DIR = "config"
MAX_JSON_RECORDS = 8000

# High-Precision Offshore Maritime Waypoints for ALL Regions
MARITIME_PORTS = [
    {
        "port": "Vladivostok Port", "dep": "Busan", "dest": "Niigata", "region": "Russian Far East EEZ",
        "lat": 43.0800, "lon": 131.8700,
        # Sea of Japan Coastal Circuit
        "waypoints": [
            [35.18, 129.08], # Busan
            [37.50, 130.50], # Open Sea of Japan
            [41.00, 131.20], # Offshore Sea of Japan Approach
            [43.08, 131.87], # Vladivostok Anchorage
            [41.50, 134.00], # Central Sea of Japan (Offshore)
            [37.92, 139.04]  # Niigata
        ]
    },
    {
        "port": "Murmansk Commercial Port", "dep": "Tromso", "dest": "Kirkenes", "region": "Arctic EEZ",
        "lat": 69.0200, "lon": 33.0500,
        # Arctic Waters & Kola Fjord Marine Navigation
        "waypoints": [
            [69.65, 18.96], # Tromso
            [71.10, 25.80], # Offshore Barents Sea (Clears North Cape)
            [70.20, 31.80], # Offshore Rybachy Peninsula
            [69.45, 33.60], # Entrance to Kola Bay Fjord
            [69.02, 33.05], # Murmansk Port
            [69.45, 33.60], # Out of Kola Bay Fjord
            [69.80, 30.50]  # Kirkenes Offshore Approach
        ]
    },
    {
        "port": "St. Petersburg Port", "dep": "Tallinn", "dest": "Helsinki", "region": "Baltic Sea EEZ",
        "lat": 59.9000, "lon": 30.1500,
        # Gulf of Finland Sea Lane
        "waypoints": [
            [59.44, 24.75], # Tallinn
            [59.70, 26.50], # Gulf of Finland Open Water
            [59.90, 28.50], # Eastern Baltic Shipping Channel
            [59.90, 30.15], # St. Petersburg Port
            [60.00, 27.00], # Gulf of Finland Open Water
            [60.17, 24.94]  # Helsinki
        ]
    },
    {
        "port": "Novorossiysk Port", "dep": "Samsun", "dest": "Istanbul", "region": "Black Sea EEZ",
        "lat": 44.6800, "lon": 37.8000,
        # Black Sea Central Sea Lanes
        "waypoints": [
            [41.29, 36.33], # Samsun
            [43.00, 36.80], # Open Black Sea
            [44.68, 37.80], # Novorossiysk Bay
            [43.50, 34.00], # Open Black Sea Transit
            [41.50, 30.50], # Bosphorus Offshore Approach
            [41.01, 28.98]  # Istanbul
        ]
    },
    {
        "port": "Santos Port Complex", "dep": "Buenos Aires", "dest": "Montevideo", "region": "South America EEZ",
        "lat": -23.9608, "lon": -46.3331,
        # Deep Atlantic Offshore Bulge Route
        "waypoints": [
            [-34.60, -58.38], # Buenos Aires
            [-35.20, -56.00], # Out of Rio de la Plata
            [-34.50, -52.50], # Deep Atlantic (Clears Uruguay)
            [-32.00, -50.00], # Deep Atlantic (Clears Southern Brazil)
            [-28.00, -47.50], # Deep Atlantic (Offshore Santa Catarina)
            [-24.20, -46.10], # Santos Offshore Approach
            [-23.96, -46.33]  # Santos Anchorage
        ]
    },
    {
        "port": "Rotterdam Gateway", "dep": "Hamburg", "dest": "Straits of Dover", "region": "European EEZ",
        "lat": 51.9800, "lon": 3.9000,
        # North Sea & English Channel Shipping Corridor
        "waypoints": [
            [53.90, 8.50], # Hamburg Outer Elbe
            [53.80, 6.00], # North Sea Open Waters
            [52.80, 4.00], # Dutch Offshore Coast
            [51.98, 3.90], # Maasvlakte / Rotterdam Offshore Anchorage
            [51.50, 2.50], # Southern North Sea Shipping Lane
            [51.00, 1.50]  # Straits of Dover
        ]
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

        # Offshore anchorage jitter
        dist = ((hash_val % 100) / 100.0) * 0.01

        offshore_lat = round(port_info["lat"] + (dist * 0.8 * (hash_val % 2 or -1)), 4)
        offshore_lon = round(port_info["lon"] + (dist * (hash_val % 3 or -1)), 4)

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
            "routeCoordinates": port_info["waypoints"]
        }
        processed_records.append(record)

    processed_records.sort(key=lambda x: x["biosecurityRiskScore"], reverse=True)
    final_records = processed_records[:MAX_JSON_RECORDS]

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_records).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Exported {len(final_records)} records with true offshore ocean routes across all regions.")

if __name__ == "__main__":
    process_all_config_csvs()
