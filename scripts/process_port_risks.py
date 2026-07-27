import os
import glob
import sys
import hashlib
import re
import pandas as pd

CONFIG_DIR = "config"

# Extensive global coordinate map covering all major EEZ regions
GLOBAL_PORT_COORDINATES = [
    # South & Central America / Caribbean
    {"keywords": ["uruguay", "uruguayan"], "lat": -34.9000, "lon": -56.1600},
    {"keywords": ["suriname", "surinamese"], "lat": 5.8500, "lon": -55.2000},
    {"keywords": ["belize", "belizean"], "lat": 17.5000, "lon": -88.1800},
    {"keywords": ["mexico", "mexican"], "lat": 19.2000, "lon": -96.1300},
    {"keywords": ["south_america", "santos", "brazil", "brazilian"], "lat": -23.9608, "lon": -46.3331},
    {"keywords": ["argentina", "buenos"], "lat": -34.6000, "lon": -58.3800},
    {"keywords": ["bermuda"], "lat": 32.3000, "lon": -64.7800},
    {"keywords": ["chile", "chilean"], "lat": -33.0400, "lon": -71.6200},
    {"keywords": ["peru", "peruvian"], "lat": -12.0400, "lon": -77.1400},
    {"keywords": ["panama"], "lat": 8.9800, "lon": -79.5200},

    # Mediterranean, Middle East & Europe
    {"keywords": ["turkey", "turkish"], "lat": 41.0100, "lon": 28.9700},
    {"keywords": ["croatia", "croatian"], "lat": 43.5100, "lon": 16.4400},
    {"keywords": ["spain", "spanish", "canary"], "lat": 28.1200, "lon": -15.4300},
    {"keywords": ["cyprus", "cypriot"], "lat": 34.6700, "lon": 33.0400},
    {"keywords": ["malta", "maltese"], "lat": 35.8900, "lon": 14.5100},
    {"keywords": ["oman", "omani"], "lat": 23.6100, "lon": 58.5900},
    {"keywords": ["greece", "greek"], "lat": 37.9400, "lon": 23.6400},
    {"keywords": ["italy", "italian"], "lat": 40.8500, "lon": 14.2600},
    {"keywords": ["rotterdam", "dutch", "european"], "lat": 51.9800, "lon": 3.9000},

    # Baltic, Arctic & Black Sea
    {"keywords": ["baltic", "petersburg"], "lat": 59.8800, "lon": 30.2000},
    {"keywords": ["arctic", "murmansk"], "lat": 69.0200, "lon": 33.0500},
    {"keywords": ["black", "novorossiysk"], "lat": 44.6800, "lon": 37.8000},

    # Asia & Far East
    {"keywords": ["russian", "vladivostok"], "lat": 43.0800, "lon": 131.8700},
    {"keywords": ["japan", "japanese"], "lat": 35.4400, "lon": 139.6300},
    {"keywords": ["korea", "korean"], "lat": 35.1700, "lon": 129.0700},
    {"keywords": ["china", "chinese"], "lat": 31.2300, "lon": 121.4700}
]

def clean_filename_title(filename):
    base = os.path.basename(filename).replace(".csv", "").replace("_", " ").replace("-", " ")
    clean = re.sub(r'202\d.*', '', base).strip()
    return clean.title() if clean else "Monitored Regional Port"

def get_unique_port_location(filename, idx):
    lf = filename.lower()
    base_lat, base_lon = 20.0, 0.0
    matched = False

    for entry in GLOBAL_PORT_COORDINATES:
        for kw in entry["keywords"]:
            if kw in lf:
                base_lat, base_lon = entry["lat"], entry["lon"]
                matched = True
                break
        if matched:
            break

    if not matched:
        # Global regional hubs fallback based on file index
        fallback_hubs = [
            [51.98, 3.90],   # North Sea
            [35.89, 14.51],  # Mediterranean
            [25.27, 55.29],  # Persian Gulf
            [1.29, 103.85],  # Southeast Asia
            [19.20, -96.13], # Gulf of Mexico
            [-23.96, -46.33] # South Atlantic
        ]
        base_lat, base_lon = fallback_hubs[idx % len(fallback_hubs)]

    # Add a unique offset per file so markers never overlap perfectly
    hash_val = int(hashlib.md5(filename.encode('utf-8')).hexdigest(), 16)
    offset_lat = ((hash_val % 100) - 50) / 100.0 * 1.5
    offset_lon = (((hash_val // 100) % 100) - 50) / 100.0 * 1.5

    return [round(base_lat + offset_lat, 4), round(base_lon + offset_lon, 4)]

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Processing {len(csv_files)} CSV files into unique port markers...")

    port_summary = {}

    for file_idx, f in enumerate(csv_files):
        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]
            
            source_port_name = clean_filename_title(f)
            loc = get_unique_port_location(f, file_idx)

            if source_port_name not in port_summary:
                port_summary[source_port_name] = {
                    "portName": source_port_name,
                    "year": 2025,
                    "location": loc,
                    "totalPortVisits": 0,
                    "highRiskCount": 0,
                    "moderateRiskCount": 0,
                    "lowRiskCount": 0,
                    "vessels": []
                }

            for idx, row in df.iterrows():
                vessel_name = str(row.get("name") or row.get("vessel_name") or f"Vessel_{idx}").strip()
                mmsi = str(row.get("mmsi") or row.get("ssvid") or f"273{idx:06d}").strip()
                flag = str(row.get("flag") or row.get("flag_translated") or "UNK").strip()
                vessel_type = str(row.get("gfw_vessel_type") or row.get("vessel_type") or "Merchant/Carrier").strip()

                try:
                    total_visits = float(row.get("total_port_visit_events") or row.get("total_visits") or 10)
                except (ValueError, TypeError):
                    total_visits = 10.0

                residence_hrs = round(min(168.0, max(6.0, total_visits * 0.25)), 1)

                if total_visits >= 300:
                    risk_score = 0.92
                    risk_category = "High Fouling Risk"
                    port_summary[source_port_name]["highRiskCount"] += 1
                elif total_visits >= 100:
                    risk_score = 0.65
                    risk_category = "Moderate Vector"
                    port_summary[source_port_name]["moderateRiskCount"] += 1
                else:
                    risk_score = 0.35
                    risk_category = "Low Risk"
                    port_summary[source_port_name]["lowRiskCount"] += 1

                port_summary[source_port_name]["totalPortVisits"] += int(total_visits)

                port_summary[source_port_name]["vessels"].append({
                    "mmsi": mmsi,
                    "vesselName": vessel_name,
                    "flag": flag,
                    "vesselType": vessel_type if vessel_type.lower() != "other" else "Carrier/Merchant",
                    "residenceHours": residence_hrs,
                    "biosecurityRiskScore": risk_score,
                    "riskCategory": risk_category,
                    "totalEvents": int(total_visits)
                })

        except Exception as e:
            print(f"Error processing file {f}: {e}")

    final_ports = list(port_summary.values())

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_ports).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Exported {len(final_ports)} distinct port locations to data/baseline_risk.json.")

if __name__ == "__main__":
    process_all_config_csvs()
