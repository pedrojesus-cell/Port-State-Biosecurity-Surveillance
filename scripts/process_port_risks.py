import os
import glob
import sys
import hashlib
import re
import pandas as pd

CONFIG_DIR = "config"

# Anchor coordinates for regional port clusters
PORT_ANCHORS = {
    "russian": {"name": "Russian Far East EEZ Ports", "lat": 43.0800, "lon": 131.8700},
    "arctic": {"name": "Arctic EEZ Ports (Murmansk/Tromso)", "lat": 69.0200, "lon": 33.0500},
    "baltic": {"name": "Baltic Sea EEZ Ports (St. Petersburg)", "lat": 59.8800, "lon": 30.2000},
    "black": {"name": "Black Sea EEZ Ports (Novorossiysk)", "lat": 44.6800, "lon": 37.8000},
    "south_america": {"name": "South America EEZ Ports (Santos)", "lat": -23.9608, "lon": -46.3331},
    "european": {"name": "European EEZ Ports (Rotterdam)", "lat": 51.9800, "lon": 3.9000},
    "hormuz": {"name": "Strait of Hormuz EEZ Ports", "lat": 26.5000, "lon": 56.2500},
    "mediterranean": {"name": "Mediterranean EEZ Ports", "lat": 31.2600, "lon": 32.3000}
}

def clean_filename_title(filename):
    base = os.path.basename(filename).replace(".csv", "").replace("_", " ").replace("-", " ")
    clean = re.sub(r'202\d.*', '', base).strip()
    return clean.title() if clean else "Monitored Regional Port"

def match_port_anchor(filename):
    lf = filename.lower()
    for key, data in PORT_ANCHORS.items():
        if key in lf:
            return data
    return PORT_ANCHORS["european"]

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Processing {len(csv_files)} CSV files into per-port biosecurity risk aggregates...")

    port_summary = {}

    for f in csv_files:
        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]
            
            source_port_name = clean_filename_title(f)
            anchor = match_port_anchor(f)

            if source_port_name not in port_summary:
                port_summary[source_port_name] = {
                    "portName": source_port_name,
                    "year": 2025,
                    "location": [anchor["lat"], anchor["lon"]],
                    "totalPortVisits": 0,
                    "highRiskCount": 0,       # High Fouling Risk (>= 70%)
                    "moderateRiskCount": 0,   # Moderate Vector (40% - 69%)
                    "lowRiskCount": 0,        # Low Risk (< 40%)
                    "vessels": []
                }

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

                # Risk Categorization
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

                port_summary[source_port_name]["totalPortVisits"] += 1

                # Record detailed vessel data under this port
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
    print(f"SUCCESS: Aggregated {len(final_ports)} port records into data/baseline_risk.json.")

if __name__ == "__main__":
    process_all_config_csvs()
