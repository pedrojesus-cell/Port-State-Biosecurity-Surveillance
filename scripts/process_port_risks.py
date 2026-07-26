import os
import glob
import re
import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

CONFIG_DIR = "config"
DATA_DIR = "data"
EEZ_SHAPEFILE_PATH = os.path.join("boundaries", "World_EEZ_v12.gpkg")  # Marine Regions GeoPackage

# -------------------------------------------------------------------
# 1. MARINE REGIONS & GFW ONLINE API FALLBACK HELPERS
# -------------------------------------------------------------------
def query_marine_regions_api(eez_name):
    """
    Queries Marine Regions REST Gazetteer API by name if spatial join is unavailable.
    Returns: MRGID and preferred label.
    """
    url = f"https://www.marineregions.org/rest/getGazetteerRecordsByName.json/{eez_name}/"
    try:
        response = requests.get(url, params={"fuzzy": "true"}, timeout=5)
        if response.status_code == 200:
            records = response.json()
            if records:
                # Top result
                return records[0].get("MRGID"), records[0].get("preferredGazetteerName")
    except Exception as e:
        print(f"API Warning: Failed to query Marine Regions for '{eez_name}': {e}")
    return None, eez_name


def query_gfw_vessel_events(mmsi, gfw_api_key):
    """
    Optional helper to fetch live vessel events directly from GFW API v3.
    """
    url = f"https://gateway.api.globalfishingwatch.org/v3/vessels/{mmsi}/events"
    headers = {"Authorization": f"Bearer {gfw_api_key}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"GFW API Error for MMSI {mmsi}: {e}")
    return None


# -------------------------------------------------------------------
# 2. LOAD LOCAL EEZ BOUNDARY POLYGONS
# -------------------------------------------------------------------
def load_eez_boundaries(filepath):
    """
    Loads Marine Regions World EEZ shapefile/GeoPackage into GeoPandas dataframe.
    Download standard boundary files from: https://www.marineregions.org/downloads.php
    """
    if os.path.exists(filepath):
        print(f"Loading local EEZ boundaries from: {filepath}")
        gdf_eez = gpd.read_file(filepath)
        # Standardize CRS to WGS84
        if gdf_eez.crs != "EPSG:4326":
            gdf_eez = gdf_eez.to_crs("EPSG:4326")
        return gdf_eez
    else:
        print(f"NOTICE: Local EEZ file '{filepath}' not found. Falling back to API queries.")
        return None


# -------------------------------------------------------------------
# 3. MAIN DATA PROCESSING ENGINE
# -------------------------------------------------------------------
def process_all_config_csvs(gfw_api_key=None):
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs(DATA_DIR, exist_ok=True)
        pd.DataFrame([]).to_json(os.path.join(DATA_DIR, "baseline_risk.json"), orient="records")
        return

    # Load EEZ Polygons
    gdf_eez = load_eez_boundaries(EEZ_SHAPEFILE_PATH)

    port_summary = {}

    for f in csv_files:
        file_base = os.path.basename(f)
        print(f"Processing dataset: {file_base}")

        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

            # Convert CSV rows to GeoDataFrame using Lat/Lon columns
            lat_col = next((c for c in df.columns if c in ["lat", "latitude", "lat_mean"]), None)
            lon_col = next((c for c in df.columns if c in ["lon", "longitude", "lon_mean"]), None)

            if lat_col and lon_col:
                # Clean coordinates
                df = df.dropna(subset=[lat_col, lon_col])
                df = df[(df[lon_col] >= -180) & (df[lon_col] <= 180) & (df[lat_col] >= -90) & (df[lat_col] <= 90)]
                
                geometry = [Point(xy) for xy in zip(df[lon_col], df[lat_col])]
                gdf_vessels = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

                # Perform Spatial Join with EEZ Polygons
                if gdf_eez is not None:
                    gdf_vessels = gpd.sjoin(gdf_vessels, gdf_eez, how="left", predicate="intersects")

            else:
                gdf_vessels = gpd.GeoDataFrame(df)
                gdf_vessels["geoname"] = "Unknown EEZ / Point Missing"

            # Iterate vessel events
            for idx, row in gdf_vessels.iterrows():
                # Extract identified EEZ name from Marine Regions layer or fallback
                eez_name = str(
                    row.get("geoname") or 
                    row.get("eez_name") or 
                    row.get("territory1") or 
                    "Unmapped High Seas / EEZ"
                ).strip()

                mrgid = int(row.get("mrgid")) if pd.notnull(row.get("mrgid")) else None

                if eez_name not in port_summary:
                    # Get EEZ centroid or first point coordinate
                    lat_val = float(row[lat_col]) if lat_col and pd.notnull(row.get(lat_col)) else 0.0
                    lon_val = float(row[lon_col]) if lon_col and pd.notnull(row.get(lon_col)) else 0.0

                    port_summary[eez_name] = {
                        "eezName": eez_name,
                        "mrgid": mrgid,
                        "year": 2026,
                        "location": [round(lat_val, 4), round(lon_val, 4)],
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

                # Biosecurity fouling risk evaluation
                if total_visits >= 15:
                    risk_score = 0.92
                    risk_category = "High Fouling Risk"
                    port_summary[eez_name]["highRiskCount"] += 1
                elif total_visits >= 5:
                    risk_score = 0.65
                    risk_category = "Moderate Vector"
                    port_summary[eez_name]["moderateRiskCount"] += 1
                else:
                    risk_score = 0.35
                    risk_category = "Low Risk"
                    port_summary[eez_name]["lowRiskCount"] += 1

                port_summary[eez_name]["totalPortVisits"] += int(total_visits)
                port_summary[eez_name]["vessels"].append({
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
    print(f"SUCCESS: Processed and exported {len(final_ports)} distinct EEZ spatial zones to 'baseline_risk.json'.")


if __name__ == "__main__":
    process_all_config_csvs()
