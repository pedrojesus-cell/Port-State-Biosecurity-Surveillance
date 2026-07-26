import os
import glob
import json
import math
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
from datetime import datetime

CONFIG_DIR = "config"
DATA_DIR = "data"
ANCHORAGE_FILE = os.path.join(CONFIG_DIR, "gfw_anchorages.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "baseline_risk.json")

def load_anchorages():
    """Loads GFW anchorage database and builds a spatial k-d tree for fast nearest-neighbor lookups."""
    if os.path.exists(ANCHORAGE_FILE):
        df_anc = pd.read_csv(ANCHORAGE_FILE)
        df_anc.columns = [c.lower().strip() for c in df_anc.columns]
        coords = df_anc[['lat', 'lon']].values
        tree = cKDTree(coords)
        return df_anc, tree
    return None, None

def calculate_hull_fouling_risk(total_visits, residence_hrs, mgps_active=True, last_docking_days=180):
    """
    Models biofouling risk R in [0.0, 1.0] based on Battini et al. (2026).
    R = base_sojourn_factor * visit_frequency_factor * mgps_multiplier
    """
    # Residence duration factor (sigmoidal saturation curve)
    f_residence = 1.0 / (1.0 + math.exp(-0.05 * (residence_hrs - 48.0)))
    
    # Visit frequency weight
    f_frequency = min(1.0, total_visits / 20.0)
    
    # Base unadjusted biofouling risk
    r_base = (0.6 * f_residence) + (0.4 * f_frequency)
    
    # MGPS (Marine Growth Prevention System) status modifier
    # Inactive or overdue MGPS maintenance significantly elevates fouling risk
    mgps_modifier = 0.75 if mgps_active else 1.35
    docking_penalty = 1.2 if last_docking_days > 365 else 1.0
    
    final_score = round(min(1.0, max(0.0, r_base * mgps_modifier * docking_penalty)), 3)
    
    # Classification
    if final_score >= 0.70:
        category = "High Fouling Risk"
    elif final_score >= 0.40:
        category = "Moderate Vector"
    else:
        category = "Low Risk"
        
    return final_score, category

def process_pipeline():
    os.makedirs(DATA_DIR, exist_ok=True)
    df_anc, anc_tree = load_anchorages()
    
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))
    csv_files = [f for f in csv_files if "gfw_anchorages" not in f]
    
    port_agg = {}

    for file_path in csv_files:
        try:
            df = pd.read_csv(file_path, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

            for idx, row in df.iterrows():
                # Step 1: Clean Identifiers
                mmsi = str(row.get("mmsi") or row.get("ssvid") or f"999{idx:06d}").strip()
                vessel_name = str(row.get("name") or row.get("vessel_name") or f"Vessel_{mmsi}").strip()
                flag = str(row.get("flag") or "UNK").upper()
                vessel_type = str(row.get("vessel_type") or "Carrier").strip()
                
                # Raw coordinates
                raw_lat = float(row.get("lat") or row.get("latitude") or 0.0)
                raw_lon = float(row.get("lon") or row.get("longitude") or 0.0)

                # Step 2: Geospatial Resolution against GFW Anchorage Reference
                resolved_port = str(row.get("port_name") or row.get("eez_name") or "Global EEZ Anchorage").strip().title()
                if anc_tree is not None and (raw_lat != 0.0 or raw_lon != 0.0):
                    distance, nearest_idx = anc_tree.query([raw_lat, raw_lon])
                    if distance < 0.5: # ~50km proximity threshold
                        matched_anc = df_anc.iloc[nearest_idx]
                        resolved_port = matched_anc.get("label", resolved_port)
                        raw_lat = float(matched_anc.get("lat", raw_lat))
                        raw_lon = float(matched_anc.get("lon", raw_lon))

                # Step 3: Biofouling Risk Calculation & MGPS Parsing
                visits = float(row.get("total_visits") or row.get("visit_count") or 1)
                residence = float(row.get("residence_hours") or row.get("dwell_time") or (visits * 5.5))
                mgps_status = str(row.get("mgps_status") or "ACTIVE").upper() == "ACTIVE"
                docking_days = int(row.get("days_since_drydock") or 120)

                risk_score, risk_cat = calculate_hull_fouling_risk(
                    total_visits=visits,
                    residence_hrs=residence,
                    mgps_active=mgps_status,
                    last_docking_days=docking_days
                )

                # Aggregate by Port Facility
                if resolved_port not in port_agg:
                    port_agg[resolved_port] = {
                        "portName": resolved_port,
                        "location": [round(raw_lat, 4), round(raw_lon, 4)],
                        "totalPortVisits": 0,
                        "highRiskCount": 0,
                        "moderateRiskCount": 0,
                        "lowRiskCount": 0,
                        "vessels": []
                    }

                port_agg[resolved_port]["totalPortVisits"] += int(visits)
                if risk_cat == "High Fouling Risk":
                    port_agg[resolved_port]["highRiskCount"] += 1
                elif risk_cat == "Moderate Vector":
                    port_agg[resolved_port]["moderateRiskCount"] += 1
                else:
                    port_agg[resolved_port]["lowRiskCount"] += 1

                port_agg[resolved_port]["vessels"].append({
                    "mmsi": mmsi,
                    "vesselName": vessel_name,
                    "flag": flag,
                    "vesselType": vessel_type,
                    "residenceHours": round(residence, 1),
                    "mgpsStatus": "Operational" if mgps_status else "Maintenance Required",
                    "daysSinceDrydock": docking_days,
                    "biosecurityRiskScore": risk_score,
                    "riskCategory": risk_cat
                })

        except Exception as e:
            print(f"Error parsing file {file_path}: {e}")

    output_payload = {
        "metadata": {
            "generatedAt": datetime.utcnow().isoformat() + "Z",
            "pipeline": "Shipsonic Port-State Biosecurity ETL Engine v2.4",
            "totalPortsMonitored": len(port_agg),
            "totalVesselsEvaluated": sum(len(p["vessels"]) for p in port_agg.values())
        },
        "ports": list(port_agg.values())
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output_payload, f, indent=2)

    print(f"Pipeline complete. Baseline saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    process_pipeline()
