import os
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

API_TOKEN = os.environ.get("GFW_API_TOKEN")
CSV_WATCHLIST_PATH = "config/mmsi_watchlist.csv"

TARGET_REGIONS = {
    "Strait of Hormuz": {"min_lat": 24.0, "max_lat": 27.5, "min_lon": 54.0, "max_lon": 58.0},
    "European EEZ": {"min_lat": 48.0, "max_lat": 60.0, "min_lon": -10.0, "max_lon": 12.0},
    "South America EEZ": {"min_lat": -55.0, "max_lat": 12.0, "min_lon": -82.0, "max_lon": -34.0}
}

def load_watchlist_mmsis():
    if not os.path.exists(CSV_WATCHLIST_PATH):
        print(f"Error: {CSV_WATCHLIST_PATH} not found.")
        sys.exit(1)
    df = pd.read_csv(CSV_WATCHLIST_PATH, dtype={"mmsi": str})
    return df.to_dict(orient="records")

def match_target_region(lat, lon):
    if lat is None or lon is None:
        return None
    for region_name, bounds in TARGET_REGIONS.items():
        if bounds["min_lat"] <= lat <= bounds["max_lat"] and bounds["min_lon"] <= lon <= bounds["max_lon"]:
            return region_name
    return None

def fetch_timeframe_routes(start_days_ago=30, end_days_ago=15):
    """
    Fetches port visit events within a specific window (e.g., between 15 and 30 days ago)
    and constructs inter-port route geometries.
    """
    if not API_TOKEN:
        print("CRITICAL ERROR: 'GFW_API_TOKEN' is missing.")
        sys.exit(1)

    watchlist = load_watchlist_mmsis()
    processed_records = []

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=start_days_ago)).strftime("%Y-%m-%d")
    end_date = (now - timedelta(days=end_days_ago)).strftime("%Y-%m-%d")

    print(f"Fetching routes between {start_date} and {end_date} (Time-frame: {end_days_ago}-{start_days_ago} days ago)...")

    url = "https://gateway.api.globalfishingwatch.org/v3/events"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityMonitor/1.0"
    }

    for target in watchlist:
        mmsi = target["mmsi"]
        params = {
            "datasets": "public-global-port-visits-c2-events:latest",
            "vessels[0]": mmsi,
            "start-date": start_date,
            "end-date": end_date,
            "limit": 50
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                events = response.json().get("entries", [])
                for evt in events:
                    pos = evt.get("position", {})
                    vessel_lat, vessel_lon = pos.get("lat"), pos.get("lon")
                    
                    dep_port = evt.get("departurePort", {})
                    dest_port = evt.get("destinationPort", {})
                    
                    # Extract origin port, current vessel location, and destination port coordinates
                    dep_lat = dep_port.get("position", {}).get("lat")
                    dep_lon = dep_port.get("position", {}).get("lon")
                    
                    dest_lat = dest_port.get("position", {}).get("lat")
                    dest_lon = dest_port.get("position", {}).get("lon")

                    region_match = match_target_region(vessel_lat, vessel_lon)
                    
                    residency = round(float(evt.get("port_visit", {}).get("durationHrs", 0)), 1)
                    risk_score = 0.85 if residency > 48 else (0.50 if residency > 12 else 0.20)

                    route_entry = {
                        "eventId": evt.get("id"),
                        "vesselName": target.get("vessel_name") or f"MMSI {mmsi}",
                        "mmsi": mmsi,
                        "flag": target.get("flag", "UNK"),
                        "region": region_match or "Global / Other",
                        "portName": evt.get("port", {}).get("label", "Regional Port"),
                        "portOfDeparture": dep_port.get("label", "Origin Port"),
                        "portOfDestination": dest_port.get("label", "Destination Port"),
                        "residenceHours": residency,
                        "biosecurityRiskScore": risk_score,
                        "timestamp": evt.get("start"),
                        # Vessel Coordinates
                        "vesselPos": [vessel_lat, vessel_lon] if vessel_lat and vessel_lon else None,
                        # Route Coordinates: [Departure, Vessel Current, Destination]
                        "routeCoordinates": [
                            [dep_lat, dep_lon] if dep_lat and dep_lon else None,
                            [vessel_lat, vessel_lon] if vessel_lat and vessel_lon else None,
                            [dest_lat, dest_lon] if dest_lat and dest_lon else None
                        ]
                    }

                    # Keep record if within monitored target regions
                    if region_match or risk_score >= 0.70:
                        processed_records.append(route_entry)

        except Exception as err:
            print(f"Error querying MMSI {mmsi}: {err}")

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(processed_records).to_json("data/baseline_risk.json", orient="records", indent=2)
    print(f"SUCCESS: Exported {len(processed_records)} route records to 'data/baseline_risk.json'.")

if __name__ == "__main__":
    fetch_timeframe_routes(start_days_ago=30, end_days_ago=15)
