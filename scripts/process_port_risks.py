import os
import glob
import sys
import hashlib
import re
import pandas as pd

CONFIG_DIR = "config"

# Extensive global dictionary covering every region in GFW summary exports
PORT_COORDINATE_MAP = {
    # Portugal & Atlantic Ports
    "viana": [41.6932, -8.8329],          # Viana do Castelo
    "portugal": [38.7100, -9.1300],       # Lisbon / Portuguese EEZ
    "leixoes": [41.1850, -8.7000],        # Leixões / Porto
    "sines": [37.9500, -8.8700],          # Sines
    "azores": [37.7400, -25.6600],        # Azores
    "madeira": [32.6500, -16.9000],       # Madeira

    # Spain & Canaries
    "spain": [36.5300, -6.2900],          # Spanish EEZ / Cadiz
    "canary": [28.1200, -15.4300],        # Canary Islands
    "barcelona": [41.3800, 2.1700],
    "valencia": [39.4600, -0.3700],

    # South & Central America / Caribbean
    "uruguay": [-34.9000, -56.1600],
    "suriname": [5.8500, -55.2000],
    "belize": [17.5000, -88.1800],
    "mexico": [19.2000, -96.1300],
    "santos": [-23.9608, -46.3331],
    "brazil": [-23.9608, -46.3331],
    "argentina": [-34.6000, -58.3800],
    "bermuda": [32.3000, -64.7800],
    "chile": [-33.0400, -71.6200],
    "peru": [-12.0400, -77.1400],
    "panama": [8.9800, -79.5200],

    # Mediterranean & Middle East
    "turkey": [41.0100, 28.9700],
    "croatia": [43.5100, 16.4400],
    "cyprus": [34.6700, 33.0400],
    "malta": [35.8900, 14.5100],
    "oman": [23.6100, 58.5900],
    "greece": [37.9400, 23.6400],
    "italy": [40.8500, 14.2600],
    "emirates": [25.2700, 55.2900],
    "hormuz": [26.5000, 56.2500],

    # Europe, Baltic & Arctic
    "rotterdam": [51.9800, 3.9000],
    "dutch": [51.9800, 3.9000],
    "petersburg": [59.8800, 30.2000],
    "baltic": [59.8800, 30.2000],
    "murmansk": [69.0200, 33.0500],
    "arctic": [69.0200, 33.0500],
    "novorossiysk": [44.6800, 37.8000],
    "black": [44.6800, 37.8000],

    # Asia, Africa & Oceania
    "vladivostok": [43.0800, 131.8700],
    "japan": [35.4400, 139.6300],
    "korea": [35.1700, 129.0700],
    "china": [31.2300, 121.4700],
    "singapore": [1.2900, 103.8500],
    "australia": [-33.8600, 151.2000]
}

def clean_filename_title(filename):
    base = os.path.basename(filename).replace(".csv", "").replace("_", " ").replace("-", " ")
    clean = re.sub(r'202\d.*', '', base).strip()
    return clean.title() if clean else "Monitored Regional Port"

def extract_lat_lon(filename, file_idx):
    lf = filename.lower()
    
    # 1. Search dictionary for matching port keywords
    for key, coords in PORT_COORDINATE_MAP.items():
        if key in lf:
            # Deterministic offset so multiple files for the same EEZ don't overlap exactly
            hash_val = int(hashlib.md5(filename.encode('utf-8')).hexdigest(), 16)
            jitter_lat = (((hash_val % 30) - 15) / 100.0) * 0.1
            jitter_lon = ((((hash_val // 30) % 30) - 15) / 100.0) * 0.1
            return [round(coords[0] + jitter_lat, 4), round(coords[1] + jitter_lon, 4)]

    # 2. Mathematical Hash Projection fallback: GUARANTEES unique coordinate for every CSV
    hash_val = int(hashlib.md5(filename.encode('utf-8')).hexdigest(), 16)
    proj_lat = round(((hash_val % 1000) / 1000.0) * 120.0 - 50.0, 4)
    proj_lon = round((((hash_val // 1000) % 1000) / 1000.0) * 360.0 - 180.0, 4)
    return [proj_lat, proj_lon]

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Processing all {len(csv_files)} CSV files into individual 2025 port records...")

    port_summary = {}

    for file_idx, f in enumerate(csv_files):
        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]
            
            source_port_name = clean_filename_title(f)
            loc = extract_lat_lon(f, file_idx)

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
    print(f"SUCCESS: Aggregated {len(final_ports)} distinct port locations into data/baseline_risk.json.")

if __name__ == "__main__":
    process_all_config_csvs()
