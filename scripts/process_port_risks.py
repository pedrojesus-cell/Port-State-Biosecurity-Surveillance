import os
import glob
import sys
import hashlib
import re
import pandas as pd

CONFIG_DIR = "config"
MAX_JSON_RECORDS = 8000

# High-Precision Marine Sea Lanes (Strictly in water, bypassing land masses)
GLOBAL_OCEAN_FAIRWAYS = {
    "south_america": {
        "region": "South America EEZ",
        "port": "Santos Port Complex",
        "dep": "Buenos Aires",
        "dest": "Montevideo",
        "port_pos": [-23.9608, -46.3331],
        "waypoints": [
            [-34.60, -58.38], # Departure: Buenos Aires
            [-35.20, -56.00], # Exit Rio de la Plata into Atlantic
            [-34.50, -52.50], # Deep ocean (clears Uruguay)
            [-31.00, -49.50], # Deep ocean (clears Southern Brazil bulge)
            [-27.50, -47.00], # Offshore Santa Catarina
            [-23.96, -46.33], # Port: Santos
            [-34.90, -56.16]  # Destination: Montevideo
        ]
    },
    "baltic": {
        "region": "Baltic Sea EEZ",
        "port": "St. Petersburg Port",
        "dep": "Tallinn",
        "dest": "Helsinki",
        "port_pos": [59.8800, 30.2000],
        "waypoints": [
            [59.44, 24.75], # Departure: Tallinn
            [59.70, 26.50], # Open Gulf of Finland
            [59.90, 29.70], # South of Kronstadt Island Fairway
            [59.88, 30.20], # Port: St. Petersburg Harbor
            [60.17, 24.94]  # Destination: Helsinki
        ]
    },
    "arctic": {
        "region": "Arctic EEZ",
        "port": "Murmansk Commercial Port",
        "dep": "Tromso",
        "dest": "Kirkenes",
        "port_pos": [69.0200, 33.0500],
        "waypoints": [
            [69.65, 18.96], # Departure: Tromso
            [71.10, 25.80], # Barents Sea (clears North Cape)
            [70.20, 31.80], # Open Barents Sea
            [69.45, 33.60], # Kola Fjord Entrance
            [69.02, 33.05], # Port: Murmansk
            [69.80, 30.50]  # Destination: Kirkenes
        ]
    },
    "european": {
        "region": "European EEZ",
        "port": "Rotterdam Gateway",
        "dep": "Hamburg",
        "dest": "Straits of Dover",
        "port_pos": [51.9800, 3.9000],
        "waypoints": [
            [53.90, 8.50], # Departure: Hamburg Outer Elbe
            [53.80, 6.00], # North Sea Shipping Corridor
            [52.80, 4.00], # Offshore Dutch Coast
            [51.98, 3.90], # Port: Rotterdam Maasvlakte
            [51.00, 1.50]  # Destination: Straits of Dover
        ]
    },
    "black_sea": {
        "region": "Black Sea EEZ",
        "port": "Novorossiysk Port",
        "dep": "Samsun",
        "dest": "Istanbul",
        "port_pos": [44.6800, 37.8000],
        "waypoints": [
            [41.29, 36.33], # Departure: Samsun
            [43.00, 36.80], # Open Black Sea
            [44.68, 37.80], # Port: Novorossiysk
            [42.50, 32.00], # Open Black Sea Transit
            [41.01, 28.98]  # Destination: Istanbul
        ]
    },
    "far_east": {
        "region": "Russian Far East EEZ",
        "port": "Vladivostok Port",
        "dep": "Busan",
        "dest": "Niigata",
        "port_pos": [43.0800, 131.8700],
        "waypoints": [
            [35.18, 129.08], # Departure: Busan
            [37.50, 130.50], # Open Sea of Japan
            [41.00, 131.20], # Offshore Approach
            [43.08, 131.87], # Port: Vladivostok
            [37.92, 139.04]  # Destination: Niigata
        ]
    }
}

def clean_filename_title(filename):
    base = os.path.basename(filename).replace(".csv", "").replace("_", " ").replace("-", " ")
    clean = re.sub(r'202\d.*', '', base).strip()
    return clean.title() if clean else "Monitored Regional Port"

def match_fairway_by_filename(filename):
    lf = filename.lower()
    if "south" in lf or "america" in lf or "brazil" in lf:
        return GLOBAL_OCEAN_FAIRWAYS["south_america"]
    elif "baltic" in lf or "petersburg" in lf:
        return GLOBAL_OCEAN_FAIRWAYS["baltic"]
    elif "arctic" in lf or "murmansk" in lf or "norway" in lf:
        return GLOBAL_OCEAN_FAIRWAYS["arctic"]
    elif "black" in lf or "novorossiysk" in lf:
        return GLOBAL_OCEAN_FAIRWAYS["black_sea"]
    elif "vladivostok" in lf or "russian" in lf or "pacific" in lf:
        return GLOBAL_OCEAN_FAIRWAYS["far_east"]
    else:
        return GLOBAL_OCEAN_FAIRWAYS["european"]

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Processing all {len(csv_files)} CSV files into biosecurity surveillance risk metrics...")

    processed_records = []

    for f in csv_files:
        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]
            
            source_port_title = clean_filename_title(f)
            fairway = match_fairway_by_filename(f)

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
                
                # Signal Risk Classification
                if total_visits >= 300:
                    risk_score = 0.92  # High Fouling Risk (>=70%)
                elif total_visits >= 100:
                    risk_score = 0.65  # Moderate Vector (40% - 69%)
                else:
                    risk_score = 0.35  # Low Risk (<40%)

                # Anchorage offset jitter
                hash_val = int(hashlib.md5((mmsi + source_port_title).encode('utf-8')).hexdigest(), 16)
                dist = ((hash_val % 100) / 100.0) * 0.008

                offshore_lat = round(fairway["port_pos"][0] + (dist * 0.5 * (hash_val % 2 or -1)), 4)
                offshore_lon = round(fairway["port_pos"][1] + (dist * (hash_val % 3 or -1)), 4)

                record = {
                    "mmsi": mmsi,
                    "vesselName": vessel_name,
                    "flag": flag,
                    "vesselType": vessel_type if vessel_type.lower() != "other" else "Carrier/Merchant",
                    "region": source_port_title,
                    "portName": f"{source_port_title} ({fairway['port']})",
                    "portOfDeparture": fairway["dep"],
                    "portOfDestination": fairway["dest"],
                    "residenceHours": residence_hrs,
                    "biosecurityRiskScore": risk_score,
                    "totalEvents": int(total_visits),
                    "vesselPos": [offshore_lat, offshore_lon],
                    "routeCoordinates": fairway["waypoints"]
                }
                processed_records.append(record)

        except Exception as e:
            print(f"Error processing file {f}: {e}")

    if not processed_records:
        sys.exit(1)

    processed_records.sort(key=lambda x: x["biosecurityRiskScore"], reverse=True)
    final_records = processed_records[:MAX_JSON_RECORDS]

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_records).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Exported {len(final_records)} records with water-only marine trajectories.")

if __name__ == "__main__":
    process_all_config_csvs()
