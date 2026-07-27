import os
import sys
import pandas as pd
from datetime import datetime, timedelta, timezone

CSV_DATA_PATH = "config/gfw_port_visits_12m.csv"

# Target Geographic Corridors
TARGET_REGIONS = {
    "Strait of Hormuz": {"min_lat": 24.0, "max_lat": 27.5, "min_lon": 54.0, "max_lon": 58.0},
    "European EEZ": {"min_lat": 48.0, "max_lat": 60.0, "min_lon": -10.0, "max_lon": 12.0},
    "South America EEZ": {"min_lat": -55.0, "max_lat": 12.0, "min_lon": -82.0, "max_lon": -34.0}
}

def match_target_region(lat, lon):
    """Checks if coordinates fall inside target bounding boxes."""
    try:
        lat, lon = float(lat), float(lon)
        for region_name, bounds in TARGET_REGIONS.items():
            if bounds["min_lat"] <= lat <= bounds["max_lat"] and bounds["min_lon"] <= lon <= bounds["max_lon"]:
                return region_name
    except (TypeError, ValueError):
        pass
    return None

def process_gfw_csv(timeframe_days_start=30, timeframe_days_end=0):
    if not os.path.exists(CSV_DATA_PATH):
        print(f"NOTICE: '{CSV_DATA_PATH}' not found.")
        print("Please upload your 12-month GFW CSV file to 'config/gfw_port_visits_12m.csv'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Loading and processing GFW historical port entries from '{CSV_DATA_PATH}'...")

    try:
        # Flexible CSV loading (handles flexible column naming from GFW exports)
        df = pd.read_csv(CSV_DATA_PATH, low_memory=False)
        df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

        processed_records = []

        for _, row in df.iterrows():
            mmsi = str(row.get("mmsi") or row.get("ssvid") or "").strip()
            vessel_name = str(row.get("vessel_name") or row.get("shipname") or f"MMSI {mmsi}")
            flag = str(row.get("flag") or row.get("country") or "UNK")
            vessel_type = str(row.get("vessel_type") or row.get("geartype") or "Merchant/Carrier")

            port_name = str(row.get("port_label") or row.get("port_name") or row.get("port") or "Regional Port")
            dep_port = str(row.get("departure_port") or row.get("departure_port_label") or "Origin Port")
            dest_port = str(row.get("destination_port") or row.get("destination_port_label") or "Destination Port")

            # Extract Coordinates
            lat = row.get("lat") or row.get("latitude") or row.get("port_lat")
            lon = row.get("lon") or row.get("longitude") or row.get("port_lon")

            dep_lat = row.get("departure_lat") or row.get("dep_lat")
            dep_lon = row.get("departure_lon") or row.get("dep_lon")

            dest_lat = row.get("destination_lat") or row.get("dest_lat")
            dest_lon = row.get("destination_lon") or row.get("dest_lon")

            residency = float(row.get("duration_hrs") or row.get("residence_hours") or row.get("durationhrs") or 24.0)
            risk_score = 0.85 if residency > 48 else (0.50 if residency > 12 else 0.20)

            # Evaluate regional corridor matches
            matched_region = (
                match_target_region(lat, lon) or 
                match_target_region(dep_lat, dep_lon) or 
                match_target_region(dest_lat, dest_lon)
            )

            # Keep records matching target corridors or showing high risk
            if matched_region or risk_score >= 0.70:
                record = {
                    "mmsi": mmsi,
                    "vesselName": vessel_name,
                    "flag": flag,
                    "vesselType": vessel_type,
                    "region": matched_region or "Transatlantic Corridor",
                    "portName": port_name,
                    "portOfDeparture": dep_port,
                    "portOfDestination": dest_port,
                    "residenceHours": round(residency, 1),
                    "biosecurityRiskScore": risk_score,
                    "vesselPos": [float(lat), float(lon)] if lat and lon else None,
                    "routeCoordinates": [
                        [float(dep_lat), float(dep_lon)] if dep_lat and dep_lon else None,
                        [float(lat), float(lon)] if lat and lon else None,
                        [float(dest_lat), float(dest_lon)] if dest_lat and dest_lon else None
                    ]
                }
                processed_records.append(record)

        os.makedirs("data", exist_ok=True)
        pd.DataFrame(processed_records).to_json("data/baseline_risk.json", orient="records", indent=2)
        print(f"SUCCESS: Processed {len(processed_records)} corridor records into 'data/baseline_risk.json'.")

    except Exception as err:
        print(f"ERROR parsing GFW CSV file: {err}")
        sys.exit(1)

if __name__ == "__main__":
    process_gfw_csv()
