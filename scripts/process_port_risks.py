import os
import glob
import sys
import hashlib
import re
import pandas as pd

CONFIG_DIR = "config"

# Extensive geographic coordinate lookup dictionary
PORT_GEO_DATABASE = {
    # Portugal Ports & Regions
    "viana do castelo": [41.6932, -8.8329],
    "viana": [41.6932, -8.8329],
    "leixoes": [41.1850, -8.7000],
    "porto": [41.1500, -8.6100],
    "lisbon": [38.7100, -9.1300],
    "lisboa": [38.7100, -9.1300],
    "sines": [37.9500, -8.8700],
    "setubal": [38.5200, -8.8900],
    "faro": [37.0100, -7.9300],
    "portugal": [38.7100, -9.1300],
    "azores": [37.7400, -25.6600],
    "madeira": [32.6500, -16.9000],

    # Spain Ports & Regions
    "cadiz": [36.5300, -6.2900],
    "barcelona": [41.3800, 2.1700],
    "valencia": [39.4600, -0.3700],
    "bilbao": [43.3600, -3.0400],
    "vigo": [42.2400, -8.7200],
    "algeciras": [36.1300, -5.4400],
    "malaga": [36.7100, -4.4200],
    "las palmas": [28.1400, -15.4200],
    "tenerife": [28.4600, -16.2500],
    "canary": [28.1200, -15.4300],
    "spain": [36.5300, -6.2900],

    # Europe & Mediterranean
    "rotterdam": [51.9800, 3.9000],
    "antwerp": [51.2200, 4.4000],
    "hamburg": [53.5500, 9.9900],
    "marseille": [43.2900, 5.3600],
    "le havre": [49.4900, 0.1000],
    "genoa": [44.4000, 8.9300],
    "trieste": [45.6400, 13.7700],
    "piraeus": [37.9400, 23.6400],
    "istanbul": [41.0100, 28.9700],
    "dubrovnik": [42.6500, 18.0900],
    "rijeka": [45.3200, 14.4400],
    "limassol": [34.6700, 33.0400],
    "valletta": [35.8900, 14.5100],

    # Global Regions
    "montevideo": [-34.9000, -56.1600],
    "paramaribo": [5.8500, -55.2000],
    "belize city": [17.5000, -88.1800],
    "veracruz": [19.2000, -96.1300],
    "santos": [-23.9608, -46.3331],
    "buenos aires": [-34.6000, -58.3800],
    "valparaiso": [-33.0400, -71.6200],
    "callao": [-12.0400, -77.1400],
    "panama city": [8.9800, -79.5200],
    "muscat": [23.6100, 58.5900],
    "fujairah": [25.1200, 56.3200],
    "dubai": [25.2700, 55.2900],
    "vladivostok": [43.0800, 131.8700],
    "yokohama": [35.4400, 139.6300],
    "busan": [35.1700, 129.0700],
    "shanghai": [31.2300, 121.4700],
    "singapore": [1.2900, 103.8500]
}

def resolve_location(title_str, file_str, unique_seed):
    combined = f"{title_str} {file_str}".lower()

    # Match database
    for key, coords in PORT_GEO_DATABASE.items():
        if key in combined:
            hash_val = int(hashlib.md5(unique_seed.encode('utf-8')).hexdigest(), 16)
            j_lat = (((hash_val % 50) - 25) / 100.0) * 0.12
            j_lon = ((((hash_val // 50) % 50) - 25) / 100.0) * 0.12
            return [round(coords[0] + j_lat, 4), round(coords[1] + j_lon, 4)]

    # Hash scatter for unmapped ports so every single CSV file gets a unique location
    hash_val = int(hashlib.md5(unique_seed.encode('utf-8')).hexdigest(), 16)
    proj_lat = round(10.0 + (((hash_val % 1000) / 1000.0) * 55.0), 4)
    proj_lon = round(-100.0 + ((((hash_val // 1000) % 1000) / 1000.0) * 160.0), 4)
    return [proj_lat, proj_lon]

def clean_file_title(filename):
    base = os.path.basename(filename).replace(".csv", "").replace("_", " ").replace("-", " ")
    clean = re.sub(r'port\s+visit\s+events?', '', base, flags=re.IGNORECASE)
    clean = re.sub(r'exclusive\s+economic\s+zone', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'eez', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'202\d.*', '', clean).strip()
    return clean.title() if clean else "Monitored Port"

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Processing all {len(csv_files)} CSV files with strict isolated key tracking...")

    port_summary = {}

    for file_idx, f in enumerate(csv_files):
        file_base = os.path.basename(f)
        display_title = clean_file_title(file_base)

        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

            # Detect specific port/anchorage column if present
            port_col = None
            for candidate in ['port_name', 'anchorage_name', 'label', 'event_start_port', 'event_end_port']:
                if candidate in df.columns:
                    port_col = candidate
                    break

            for idx, row in df.iterrows():
                raw_port = str(row.get(port_col) if port_col else "").strip()
                
                if raw_port and raw_port.lower() not in ['nan', 'none', 'null', '']:
                    sub_title = raw_port.replace("_", " ").replace("-", " ").title()
                    full_display_name = f"{display_title} ({sub_title})"
                else:
                    full_display_name = display_title

                # GUARANTEED UNIQUE KEY: Combines filename AND port title so no file is EVER overwritten
                unique_key = f"{file_base}::{full_display_name}"

                if unique_key not in port_summary:
                    coords = resolve_location(full_display_name, file_base, unique_key)
                    port_summary[unique_key] = {
                        "portName": full_display_name,
                        "year": 2025,
                        "location": coords,
                        "totalPortVisits": 0,
                        "highRiskCount": 0,
                        "moderateRiskCount": 0,
                        "lowRiskCount": 0,
                        "vessels": []
                    }

                # Extract vessel fields
                vessel_name = str(row.get("name") or row.get("vessel_name") or f"Vessel_{idx}").strip()
                mmsi = str(row.get("mmsi") or row.get("ssvid") or f"273{idx:06d}").strip()
                flag = str(row.get("flag") or row.get("flag_translated") or "UNK").strip()
                vessel_type = str(row.get("gfw_vessel_type") or row.get("vessel_type") or "Merchant/Carrier").strip()

                try:
                    total_visits = float(row.get("total_port_visit_events") or row.get("total_visits") or 1)
                except (ValueError, TypeError):
                    total_visits = 1.0

                residence_hrs = round(min(168.0, max(6.0, total_visits * 0.25)), 1)

                if total_visits >= 15:
                    risk_score = 0.92
                    risk_category = "High Fouling Risk"
                    port_summary[unique_key]["highRiskCount"] += 1
                elif total_visits >= 5:
                    risk_score = 0.65
                    risk_category = "Moderate Vector"
                    port_summary[unique_key]["moderateRiskCount"] += 1
                else:
                    risk_score = 0.35
                    risk_category = "Low Risk"
                    port_summary[unique_key]["lowRiskCount"] += 1

                port_summary[unique_key]["totalPortVisits"] += int(total_visits)

                port_summary[unique_key]["vessels"].append({
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
    print(f"SUCCESS: Exported {len(final_ports)} distinct port entries from {len(csv_files)} CSV files.")

if __name__ == "__main__":
    process_all_config_csvs()
