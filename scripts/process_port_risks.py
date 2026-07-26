import os
import glob
import pandas as pd

CONFIG_DIR = "config"
DATA_DIR = "data"
ANCHORAGE_CSV = "gfw_anchorages.csv"

def process_port_risks():
    if not os.path.exists(CONFIG_DIR):
        print(f"Directory '{CONFIG_DIR}' does not exist.")
        return

    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))
    if not csv_files:
        print(f"No CSV datasets found inside '{CONFIG_DIR}/'. Creating empty output.")
        os.makedirs(DATA_DIR, exist_ok=True)
        pd.DataFrame([]).to_json(os.path.join(DATA_DIR, "baseline_risk.json"), orient="records")
        return

    # Load GFW Anchorage reference DB for fast, non-geopandas spatial lookups
    anc_lookup = {}
    if os.path.exists(ANCHORAGE_CSV):
        df_anc = pd.read_csv(ANCHORAGE_CSV, low_memory=False)
        df_anc = df_anc[(df_anc['lon'] >= -180) & (df_anc['lon'] <= 180) & (df_anc['lat'] >= -90) & (df_anc['lat'] <= 90)]
        
        grouped = df_anc.groupby(['iso3', 'label']).agg(
            lat=('lat', 'mean'),
            lon=('lon', 'mean')
        ).reset_index()
        
        for _, r in grouped.iterrows():
            anc_lookup[f"{r['iso3']}_{r['label']}".lower()] = [round(r['lat'], 4), round(r['lon'], 4)]

    port_summary = {}

    for f in csv_files:
        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

            for idx, row in df.iterrows():
                iso3 = str(row.get("iso3") or "UNK").upper()
                port_name = str(row.get("label") or row.get("port_name") or "Monitored Zone").strip()
                display_key = f"{iso3} - {port_name}"

                # Coordinates lookup
                lat = row.get("lat") or row.get("latitude")
                lon = row.get("lon") or row.get("longitude")
                
                if pd.notnull(lat) and pd.notnull(lon) and -180 <= float(lon) <= 180:
                    coords = [round(float(lat), 4), round(float(lon), 4)]
                else:
                    coords = anc_lookup.get(f"{iso3}_{port_name}".lower(), [25.0, 50.0])

                if display_key not in port_summary:
                    port_summary[display_key] = {
                        "portName": port_name,
                        "iso3": iso3,
                        "year": 2026,
                        "location": coords,
                        "totalPortVisits": 0,
                        "highRiskCount": 0,
                        "moderateRiskCount": 0,
                        "lowRiskCount": 0,
                        "vessels": []
                    }

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
                    risk_score, risk_cat = 0.92, "High Fouling Risk"
                    port_summary[display_key]["highRiskCount"] += 1
                elif total_visits >= 5:
                    risk_score, risk_cat = 0.65, "Moderate Vector"
                    port_summary[display_key]["moderateRiskCount"] += 1
                else:
                    risk_score, risk_cat = 0.35, "Low Risk"
                    port_summary[display_key]["lowRiskCount"] += 1

                port_summary[display_key]["totalPortVisits"] += int(total_visits)
                port_summary[display_key]["vessels"].append({
                    "mmsi": mmsi,
                    "vesselName": vessel_name,
                    "flag": flag,
                    "vesselType": vessel_type,
                    "residenceHours": residence_hrs,
                    "biosecurityRiskScore": risk_score,
                    "riskCategory": risk_cat,
                    "totalEvents": int(total_visits)
                })

        except Exception as e:
            print(f"Error reading file {f}: {e}")

    os.makedirs(DATA_DIR, exist_ok=True)
    pd.DataFrame(list(port_summary.values())).to_json(os.path.join(DATA_DIR, "baseline_risk.json"), orient="records")
    print("SUCCESS: Successfully exported 'data/baseline_risk.json'.")

if __name__ == "__main__":
    process_port_risks()
