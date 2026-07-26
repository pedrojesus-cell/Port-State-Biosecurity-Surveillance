import os
import glob
import re
import pandas as pd
import numpy as np

CONFIG_DIR = "config"
DATA_DIR = "data"
ANCHORAGE_CSV = "gfw_anchorages.csv"

# -------------------------------------------------------------------
# 1. BUILD PORT & ANCHORAGE REFERENCE LOOKUP TABLE
# -------------------------------------------------------------------
def load_anchorage_reference_db(filepath):
    """
    Parses gfw_anchorages.csv to build a fast, clean spatial lookup database.
    """
    if not os.path.exists(filepath):
        print(f"WARNING: Anchorage database file '{filepath}' not found.")
        return {}, None

    df_anc = pd.read_csv(filepath, low_memory=False)

    # 1. Clean invalid geographic coordinates (-180 <= lon <= 180, -90 <= lat <= 90)
    df_anc = df_anc[
        (df_anc['lon'] >= -180) & (df_anc['lon'] <= 180) &
        (df_anc['lat'] >= -90) & (df_anc['lat'] <= 90)
    ].copy()

    # 2. Group anchorages by ISO3 and Port Label to calculate precise centroids
    grouped = df_anc.groupby(['iso3', 'label']).agg(
        mean_lat=('lat', 'mean'),
        mean_lon=('lon', 'mean'),
        total_points=('s2id', 'count'),
        docks_count=('at_dock', lambda x: (x == True).sum())
    ).reset_index()

    # 3. Store in lookup dictionary
    lookup_db = {}
    for _, row in grouped.iterrows():
        key = f"{row['iso3']}_{row['label']}".lower()
        lookup_db[key] = {
            "iso3": row['iso3'],
            "portLabel": row['label'],
            "location": [round(row['mean_lat'], 4), round(row['mean_lon'], 4)],
            "totalAnchorages": int(row['total_points']),
            "dockRatio": round(row['docks_count'] / row['total_points'], 2) if row['total_points'] > 0 else 0
        }

    print(f"SUCCESS: Loaded {len(lookup_db)} unique port/anchorage reference locations from '{filepath}'.")
    return lookup_db, df_anc


# -------------------------------------------------------------------
# 2. MATCH VESSEL POSITIONS TO ANCHORAGE DATABASE
# -------------------------------------------------------------------
def resolve_port_location(row, filename, lookup_db):
    """
    Resolves exact lat/lon and port names using gfw_anchorages lookup or raw coordinates.
    """
    row_lat = row.get("lat") or row.get("latitude") or row.get("lat_mean")
    row_lon = row.get("lon") or row.get("longitude") or row.get("lon_mean")

    # Priority 1: Use exact Lat/Lon if available in vessel row
    if pd.notnull(row_lat) and pd.notnull(row_lon):
        lat = float(row_lat)
        lon = float(row_lon)
        if -180 <= lon <= 180 and -90 <= lat <= 90:
            return [round(lat, 4), round(lon, 4)], str(row.get("label") or "Monitored Zone")

    # Priority 2: Lookup by ISO3 and Label match
    iso3 = str(row.get("iso3") or "").strip().lower()
    label = str(row.get("label") or row.get("port_name") or "").strip().lower()
    lookup_key = f"{iso3}_{label}"

    if lookup_key in lookup_db:
        entry = lookup_db[lookup_key]
        return entry["location"], entry["portLabel"]

    # Fallback default (Persian Gulf)
    return [25.0000, 50.0000], "Monitored Port"


# -------------------------------------------------------------------
# 3. MAIN DATA PROCESSING & RISK PIPELINE
# -------------------------------------------------------------------
def process_all_config_csvs():
    # Load GFW Anchorage reference database
    lookup_db, _ = load_anchorage_reference_db(ANCHORAGE_CSV)

    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No input CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs(DATA_DIR, exist_ok=True)
        pd.DataFrame([]).to_json(os.path.join(DATA_DIR, "baseline_risk.json"), orient="records")
        return

    print(f"Processing {len(csv_files)} input datasets...")
    port_summary = {}

    for f in csv_files:
        file_base = os.path.basename(f)

        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

            for idx, row in df.iterrows():
                coords, port_name = resolve_port_location(row, file_base, lookup_db)
                iso3 = str(row.get("iso3") or "UNK").upper()
                display_key = f"{iso3} - {port_name}"

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

                # Risk Score Model
                if total_visits >= 15:
                    risk_score = 0.92
                    risk_category = "High Fouling Risk"
                    port_summary[display_key]["highRiskCount"] += 1
                elif total_visits >= 5:
                    risk_score = 0.65
                    risk_category = "Moderate Vector"
                    port_summary[display_key]["moderateRiskCount"] += 1
                else:
                    risk_score = 0.35
                    risk_category = "Low Risk"
                    port_summary[display_key]["lowRiskCount"] += 1

                port_summary[display_key]["totalPortVisits"] += int(total_visits)
                port_summary[display_key]["vessels"].append({
                    "mmsi": mmsi,
                    "vesselName": vessel_name,
                    "flag": flag,
                    "vesselType": vessel_type,
                    "residenceHours": residence_hrs,
                    "biosecurityRiskScore": risk_score,
                    "riskCategory": risk_category,
                    "totalEvents": int(total_visits)
                })

        except Exception as e:
            print(f"Error processing file {f}: {e}")

    final_ports = list(port_summary.values())
    os.makedirs(DATA_DIR, exist_ok=True)
    pd.DataFrame(final_ports).to_json(os.path.join(DATA_DIR, "baseline_risk.json"), orient="records")
    print(f"SUCCESS: Exported {len(final_ports)} port risk records to '{DATA_DIR}/baseline_risk.json'.")


if __name__ == "__main__":
    process_all_config_csvs()
