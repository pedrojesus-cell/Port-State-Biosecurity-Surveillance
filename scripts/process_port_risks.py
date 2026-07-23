import os
import glob
import sys
import hashlib
import re
import pandas as pd

CONFIG_DIR = "config"
MAX_JSON_RECORDS = 8000

# High-Precision Maritime Waterway Waypoints (Strictly follow marine channels)
NAVIGATION_FAIRWAYS = {
    "saint_petersburg": {
        "port": "St. Petersburg Port", "dep": "Tallinn", "dest": "Helsinki", "region": "Baltic Sea EEZ",
        "lat": 59.8800, "lon": 30.2000,
        # Neva Bay Fairway: Tallinn -> Open Gulf of Finland -> South of Kronstadt -> Harbor
        "waypoints": [
            [59.44, 24.75],  # Tallinn
            [59.60, 26.00],  # Central Gulf of Finland
            [59.75, 28.00],  # Open Gulf Fairway
            [59.90, 29.70],  # South of Kronstadt Island
            [59.88, 30.20],  # St. Petersburg Commercial Harbor
            [59.90, 29.70],  # Exit Fairway
            [60.05, 27.50],  # Open Baltic Waters
            [60.17, 24.94]   # Helsinki
        ]
    },
    "murmansk": {
        "port": "Murmansk Commercial Port", "dep": "Tromso", "dest": "Kirkenes", "region": "Arctic EEZ",
        "lat": 69.0200, "lon": 33.0500,
        # Kola Fjord Fairway
        "waypoints": [
            [69.65, 18.96],  # Tromso
            [71.10, 25.80],  # Barents Sea (Clears North Cape)
            [70.20, 31.80],  # Barents Sea Deep Water
            [69.45, 33.60],  # Kola Bay Fjord Entrance
            [69.15, 33.40],  # Mid-Fjord Channel
            [69.02, 33.05],  # Murmansk Port
            [69.15, 33.40],  # Exit Fjord
            [69.80, 30.50]   # Kirkenes Approach
        ]
    },
    "santos": {
        "port": "Santos Port Complex", "dep": "Buenos Aires", "dest": "Montevideo", "region": "South America EEZ",
        "lat": -23.9608, "lon": -46.3331,
        # Deep Atlantic Offshore Bulge Route
        "waypoints": [
            [-34.60, -58.38], # Buenos Aires
            [-35.20, -56.00], # Rio de la Plata Channel
            [-34.50, -52.50], # Deep Atlantic (Clears Uruguay)
            [-32.00, -50.00], # Deep Atlantic (Clears Southern Brazil)
            [-28.00, -47.50], # Deep Atlantic (Offshore Santa Catarina)
            [-24.20, -46.10], # Santos Offshore Approach
            [-23.96, -46.33]  # Santos Anchorage
        ]
    },
    "rotterdam": {
        "port": "Rotterdam Gateway", "dep": "Hamburg", "dest": "Straits of Dover", "region": "European EEZ",
        "lat": 51.9800, "lon": 3.9000,
        # North Sea Marine Corridor
        "waypoints": [
            [53.90, 8.50],   # Hamburg Outer Elbe
            [53.80, 6.00],   # North Sea Shipping Lane
            [52.80, 4.00],   # Dutch Offshore Coast
            [51.98, 3.90],   # Maasvlakte Anchorage
            [51.50, 2.50],   # Southern North Sea
            [51.00, 1.50]    # Straits of Dover
        ]
    },
    "novorossiysk": {
        "port": "Novorossiysk Port", "dep": "Samsun", "dest": "Istanbul", "region": "Black Sea EEZ",
        "lat": 44.6800, "lon": 37.8000,
        "waypoints": [
            [41.29, 36.33],  # Samsun
            [43.00, 36.80],  # Open Black Sea
            [44.68, 37.80],  # Novorossiysk Bay
            [43.50, 34.00],  # Open Black Sea
            [41.01, 28.98]   # Istanbul
        ]
    },
    "vladivostok": {
        "port": "Vladivostok Port", "dep": "Busan", "dest": "Niigata", "region": "Russian Far East EEZ",
        "lat": 43.0800, "lon": 131.8700,
        "waypoints": [
            [35.18, 129.08], # Busan
            [37.50, 130.50], # Sea of Japan
            [41.00, 131.20], # Offshore Approach
            [43.08, 131.87], # Vladivostok Anchorage
            [37.92, 139.04]  # Niigata
        ]
    }
}

def extract_port_from_filename(filename):
    """Extracts human-readable port/EEZ names directly from uploaded CSV filenames."""
    base = os.path.basename(filename).replace(".csv", "").replace("_", " ").replace("-", " ")
    clean = re.sub(r'202\d.*', '', base).strip() # Strip date ranges if present
    if not clean:
        clean = "Monitored Regional Port"
    return clean.title()

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Found {len(csv_files)} uploaded CSV files in '{CONFIG_DIR}/'. Ingesting all monitored port datasets...")

    all_dfs = []
    for f in csv_files:
        try:
            temp_df = pd.read_csv(f, low_memory=False)
            extracted_port = extract_port_from_filename(f)
            temp_df["extracted_source_port"] = extracted_port
            all_dfs.append(temp_df)
        except Exception as e:
            print(f"Error reading {f}: {e}")

    if not all_dfs:
        sys.exit(1)

    df = pd.concat(all_dfs, ignore_index=True)
    df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

    processed_records = []
    fairway_keys = list(NAVIGATION_FAIRWAYS.keys())

    for idx, row in df.iterrows():
        vessel_name = str(row.get("name") or row.get("vessel_name") or f"Vessel_{idx}").strip()
        mmsi = str(row.get("mmsi") or row.get("ssvid") or f"273{idx:06d}").strip()
        flag = str(row.get("flag") or row.get("flag_translated") or "RUS").strip()
        vessel_type = str(row.get("gfw_vessel_type") or row.get("vessel_type") or "Merchant/Carrier").strip()
        detected_port_name = str(row.get("extracted_source_port") or "Regional Monitored Port")

        try:
            total_visits = float(row.get("total_port_visit_events") or row.get("total_visits") or 10)
        except (ValueError, TypeError):
            total_visits = 10.0

        # Deterministic assignment to navigation fairway
        hash_val = int(hashlib.md5(mmsi.encode('utf-8')).hexdigest(), 16)
        fairway_key = fairway_keys[hash_val % len(fairway_keys)]
        nav_info = NAVIGATION_FAIRWAYS[fairway_key]

        residence_hrs = round(min(168.0, max(6.0, total_visits * 0.25)), 1)
        
        if total_visits >= 300:
            risk_score = 0.92
        elif total_visits >= 100:
            risk_score = 0.65
        else:
            risk_score = 0.35

        # Anchorage position near harbor entrance
        dist = ((hash_val % 100) / 100.0) * 0.008
        offshore_lat = round(nav_info["lat"] + (dist * 0.5 * (hash_val % 2 or -1)), 4)
        offshore_lon = round(nav_info["lon"] + (dist * (hash_val % 3 or -1)), 4)

        record = {
            "mmsi": mmsi,
            "vesselName": vessel_name,
            "flag": flag,
            "vesselType": vessel_type if vessel_type.lower() != "other" else "Carrier/Merchant",
            "region": nav_info["region"],
            "portName": f"{detected_port_name} ({nav_info['port']})",
            "portOfDeparture": nav_info["dep"],
            "portOfDestination": nav_info["dest"],
            "residenceHours": residence_hrs,
            "biosecurityRiskScore": risk_score,
            "totalEvents": int(total_visits),
            "vesselPos": [offshore_lat, offshore_lon],
            "routeCoordinates": nav_info["waypoints"]
        }
        processed_records.append(record)

    processed_records.sort(key=lambda x: x["biosecurityRiskScore"], reverse=True)
    final_records = processed_records[:MAX_JSON_RECORDS]

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_records).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Exported {len(final_records)} records from all {len(csv_files)} CSV files into data/baseline_risk.json.")

if __name__ == "__main__":
    process_all_config_csvs()
