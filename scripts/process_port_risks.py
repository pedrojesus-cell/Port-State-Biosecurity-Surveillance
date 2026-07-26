import os
import json
import numpy as np
import pandas as pd
import geopandas as gpd
from datetime import datetime, timezone
from shapely.geometry import Point

# Mathematical Formulation for Hull Fouling Risk Score R:
# R = min(1.0, (Residence_Hours / 168.0) * (1.0 + Biofilm_Factor) * (1.0 - MGPS_Efficiency))

def load_and_clean_data(vessel_csv, port_logs_csv):
    """Clean and standardize vessel identifiers and logs."""
    vessels = pd.read_csv(vessel_csv)
    vessels['mmsi'] = vessels['mmsi'].astype(str).str.zfill(9)
    vessels['vessel_name'] = vessels['vessel_name'].str.strip().str.upper()
    
    port_logs = pd.read_csv(port_logs_csv)
    port_logs['mmsi'] = port_logs['mmsi'].astype(str).str.zfill(9)
    port_logs['arrival_time'] = pd.to_datetime(port_logs['arrival_time'])
    port_logs['departure_time'] = pd.to_datetime(port_logs['departure_time'])
    port_logs['residence_hours'] = (port_logs['departure_time'] - port_logs['arrival_time']).dt.total_seconds() / 3600.0
    
    return vessels, port_logs

def resolve_geospatial_locations(vessel_df, anchorages_csv, eez_geojson):
    """Geospatially resolve coordinates to Anchorages and EEZs."""
    gdf_vessels = gpd.GeoDataFrame(
        vessel_df,
        geometry=gpd.points_from_xy(vessel_df.longitude, vessel_df.latitude),
        crs="EPSG:4326"
    )
    
    # Load GFW Anchorages & EEZ Geometries
    anchorages = pd.read_csv(anchorages_csv)
    gdf_anchorages = gpd.GeoDataFrame(
        anchorages,
        geometry=gpd.points_from_xy(anchorages.subsegment_lon, anchorages.subsegment_lat),
        crs="EPSG:4326"
    )
    
    # Spatial Join with Anchorages (Nearest Point with Threshold)
    resolved = gpd.sjoin_nearest(gdf_vessels, gdf_anchorages, max_distance=0.05, how="left")
    
    # Spatial Join with EEZs
    if os.path.exists(eez_geojson):
        eez_gdf = gpd.read_file(eez_geojson)
        resolved = gpd.sjoin(resolved, eez_gdf[['GEONAME', 'geometry']], how='left', predicate='within')
    else:
        resolved['GEONAME'] = "High Seas / Unresolved"
        
    return resolved

def calculate_biosecurity_risk(row):
    """Calculate normalized risk score [0.0 - 1.0] and risk classification."""
    residence = row.get('residence_hours', 24.0)
    mgps_active = row.get('mgps_installed', False)
    days_since_mgps_service = row.get('days_since_last_mgps_service', 180)
    
    # Base residence risk scalar (168 hrs / 1 week = max base score)
    base_score = min(1.0, residence / 168.0)
    
    # MGPS Maintenance Factor Penalty
    mgps_efficiency = 0.85 if (mgps_active and days_since_mgps_service < 180) else 0.20
    
    # Biofouling Risk Score R
    risk_score = round(min(1.0, max(0.0, base_score * (1.5 - mgps_efficiency))), 3)
    
    if risk_score >= 0.70:
        category = "High Fouling Risk"
    elif risk_score >= 0.35:
        category = "Moderate Vector"
    else:
        category = "Low Risk"
        
    return pd.Series([risk_score, category], index=['risk_score', 'risk_category'])

def main():
    print("[+] Starting Port-State Biosecurity Risk Pipeline...")
    
    # Input File Paths
    VESSEL_CSV = "data/raw_vessel_traffic.csv"
    PORT_LOGS = "data/port_event_logs.csv"
    ANCHORAGES = "data/gfw_anchorages.csv"
    EEZ_GEOJSON = "data/marine_regions_eez.geojson"
    OUTPUT_JSON = "data/baseline_risk.json"

    # Execute Data Pipeline
    vessels, logs = load_and_clean_data(VESSEL_CSV, PORT_LOGS)
    merged_data = pd.merge(vessels, logs, on="mmsi", how="inner")
    
    resolved_gdf = resolve_geospatial_locations(merged_data, ANCHORAGES, EEZ_GEOJSON)
    
    risk_results = resolved_gdf.apply(calculate_biosecurity_risk, axis=1)
    resolved_gdf[['risk_score', 'risk_category']] = risk_results
    
    # Output JSON Transformation
    output_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_vessels_assessed": len(resolved_gdf),
        "vessels": []
    }
    
    for _, r in resolved_gdf.iterrows():
        output_payload["vessels"].append({
            "mmsi": r["mmsi"],
            "vessel_name": r["vessel_name"],
            "flag": r.get("flag", "Unknown"),
            "latitude": float(r["latitude"]),
            "longitude": float(r["longitude"]),
            "port_name": r.get("subsegment_name", r.get("GEONAME", "Unknown Port")),
            "eez_region": r.get("GEONAME", "International Waters"),
            "residence_hours": float(r.get("residence_hours", 0.0)),
            "mgps_installed": bool(r.get("mgps_installed", False)),
            "risk_score": float(r["risk_score"]),
            "risk_category": r["risk_category"]
        })
        
    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(output_payload, f, indent=2)
        
    print(f"[✓] Pipeline complete. JSON baseline written to {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
