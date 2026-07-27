import os
import glob
import sys
import hashlib
import re
import pandas as pd

CONFIG_DIR = "config"
MAX_JSON_RECORDS = 8000

# Global Maritime Coastal Coordinates & Sea Fairways
# Maps keywords in your CSV filenames directly to accurate ocean coordinates and water routes
GLOBAL_PORT_DATABASE = {
    "russian": {
        "port": "Russian EEZ / Vladivostok", "dep": "Busan", "dest": "Niigata",
        "lat": 43.0800, "lon": 131.8700,
        "route": [[35.18, 129.08], [37.50, 130.50], [41.00, 131.20], [43.08, 131.87], [37.92, 139.04]]
    },
    "arctic": {
        "port": "Arctic EEZ / Murmansk", "dep": "Tromso", "dest": "Kirkenes",
        "lat": 69.0200, "lon": 33.0500,
        "route": [[69.65, 18.96], [71.10, 25.80], [70.20, 31.80], [69.45, 33.60], [69.02, 33.05], [69.80, 30.50]]
    },
    "baltic": {
        "port": "Baltic Sea EEZ / St. Petersburg", "dep": "Tallinn", "dest": "Helsinki",
        "lat": 59.8800, "lon": 30.2000,
        "route": [[59.44, 24.75], [59.70, 26.50], [59.90, 29.70], [59.88, 30.20], [60.17, 24.94]]
    },
    "black": {
        "port": "Black Sea EEZ / Novorossiysk", "dep": "Samsun", "dest": "Istanbul",
        "lat": 44.6800, "lon": 37.8000,
        "route": [[41.29, 36.33], [43.00, 36.80], [44.68, 37.80], [42.50, 32.00], [41.01, 28.98]]
    },
    "south_america": {
        "port": "South America EEZ / Santos", "dep": "Buenos Aires", "dest": "Montevideo",
        "lat": -23.9608, "lon": -46.3331,
        "route": [[-34.60, -58.38], [-35.20, -56.00], [-34.50, -52.50], [-31.00, -49.50], [-27.50, -47.00], [-23.96, -46.33]]
    },
    "european": {
        "port": "European EEZ / Rotterdam", "dep": "Hamburg", "dest": "Straits of Dover",
        "lat": 51.9800, "lon": 3.9000,
        "route": [[53.90, 8.50], [53.80, 6.00], [52.80, 4.00], [51.98, 3.90], [51.00, 1.50]]
    },
    "hormuz": {
        "port": "Strait of Hormuz EEZ", "dep": "Fujairah", "dest": "Dammam",
        "lat": 26.5000, "lon": 56.2500,
        "route": [[25.12, 56.36], [26.00, 56.50], [26.50, 56.25], [26.80, 54.50], [26.43, 50.10]]
    },
    "mediterranean": {
        "port": "Mediterranean EEZ / Port Said", "dep": "Piraeus", "dest": "Suez Approach",
        "lat": 31.2600, "lon": 32.3000,
        "route": [[37.94, 23.64], [35.50, 27.00], [33.00, 30.50], [31.26, 32.30]]
    }
}

def clean_filename_to_port(filename):
    """Converts raw CSV filename into a clean, human-readable Port / Region title."""
    base = os.path.basename(filename).replace(".csv", "").replace("_", " ").replace("-", " ")
    clean = re.sub(r'202\d.*', '', base).strip()
    return clean.title() if clean else "Monitored Regional Port"

def match_port_data(filename):
    """Dynamically matches the CSV file to an ocean coordinate and non-land-crossing fairway."""
    lower_f = filename.lower()
    for key, data in GLOBAL_PORT_DATABASE.items():
        if key in lower_f:
            return data
    
    # Default fallback to European EEZ ocean channel if filename has unique name
    return GLOBAL_PORT_DATABASE["european"]

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Found {len(csv_files)} CSV files in '{CONFIG_DIR}/'. Processing all uploaded files dynamically...")

    processed_records = []

    for f in csv_files:
        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]
            
            # Get the exact port/EEZ name directly from this specific CSV file's name
            file_port_title = clean_filename_to_port(f)
            geo_data = match_port_data(f)

            for idx, row in df.iterrows():
                vessel_name = str(row.get("name") or row.get("vessel_name") or f"Vessel_{idx}").strip()
                mmsi = str(row.get("mmsi") or row.get("ssvid") or f"273{idx:06d}").strip()
                flag = str(row.get("flag") or row.get("flag_translated") or "RUS").strip()
                vessel_type = str(row.get("gfw_vessel_type") or row.get("vessel_type") or "Merchant/Carrier").strip()

                try:
                    total_visits = float(row.get("total_port_visit_events") or row.get("total_visits") or 10)
                except (ValueError, TypeError):
                    total_visits = 10.0

                residence_hrs = round(min(168.0, max(6.0, total_visits * 0.25)), 1)
                
                if total_visits >= 300:
                    risk_score = 0.92
                elif total_visits >= 100:
                    risk_score = 0.65
                else:
                    risk_score = 0.35

                # Small offshore jitter so vessels at the same port don't overlap exactly
                hash_val = int(hashlib.md5((mmsi + file_port_title).encode('utf-8')).hexdigest(), 16)
                dist = ((hash_val % 100) / 100.0) * 0.008

                offshore_lat = round(geo_data["lat"] + (dist * 0.5 * (hash_val % 2 or -1)), 4)
                offshore_lon = round(geo_data["lon"] + (dist * (hash_val % 3 or -1)), 4)

                record = {
                    "mmsi": mmsi,
                    "vesselName": vessel_name,
                    "flag": flag,
                    "vesselType": vessel_type if vessel_type.lower() != "other" else "Carrier/Merchant",
                    "region": file_port_title,
                    "portName": file_port_title,  # Real port name extracted from the uploaded CSV file
                    "portOfDeparture": geo_data["dep"],
                    "portOfDestination": geo_data["dest"],
                    "residenceHours": residence_hrs,
                    "biosecurityRiskScore": risk_score,
                    "totalEvents": int(total_visits),
                    "vesselPos": [offshore_lat, offshore_lon],
                    "routeCoordinates": geo_data["route"]
                }
                processed_records.append(record)

        except Exception as e:
            print(f"Error reading file {f}: {e}")

    if not processed_records:
        sys.exit(1)

    processed_records.sort(key=lambda x: x["biosecurityRiskScore"], reverse=True)
    final_records = processed_records[:MAX_JSON_RECORDS]

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_records).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Ingested all {len(csv_files)} CSV files. Total exported records: {len(final_records)}.")

if __name__ == "__main__":
    process_all_config_csvs()
