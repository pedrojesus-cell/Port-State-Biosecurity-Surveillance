import os
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

API_TOKEN = os.environ.get("GFW_API_TOKEN")
CSV_WATCHLIST_PATH = "config/mmsi_watchlist.csv"

# Geographic Bounding Boxes for Monitored Regions
TARGET_REGIONS = {
    "Strait of Hormuz": {"min_lat": 24.0, "max_lat": 27.5, "min_lon": 54.0, "max_lon": 58.0},
    "European EEZ": {"min_lat": 48.0, "max_lat": 60.0, "min_lon": -10.0, "max_lon": 12.0},
    "South America EEZ": {"min_lat": -55.0, "max_lat": 12.0, "min_lon": -82.0, "max_lon": -34.0}
}

def load_watchlist_mmsis():
    """Reads MMSIs ONLY from config/mmsi_watchlist.csv if created. Otherwise returns empty list."""
    if os.path.exists(CSV_WATCHLIST_PATH):
        try:
            df = pd.read_csv(CSV_WATCHLIST_PATH, dtype={"mmsi": str})
            df["mmsi"] = df["mmsi"].str.strip()
            vessels = df.to_dict(orient="records")
            print(f"Loaded {len(vessels)} target vessels from {CSV_WATCHLIST_PATH}")
            return vessels
        except Exception as e:
            print(f"Error reading CSV: {e}")
    return []

def fetch_dynamic_regional_events(start_date, end_date):
    """
    Fetches live port visit events directly from the GFW API based on spatial bounding boxes.
    Does NOT rely on pre-defined vessel lists.
    """
    url = "https://gateway.api.globalfishingwatch.org/v3/events"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityMonitor/1.0"
    }

    events_found = []

    for region_name, bounds in TARGET_REGIONS.items():
        # Query GFW for all port visit events within this region's bounding box
        params = {
            "datasets": "public-global-port-visits-c2-events:latest",
            "start-date": start_date,
            "end-date": end_date,
            "limit": 100,
            "confining-box": f"{bounds['min_lon']},{bounds['min_lat']},{bounds['max_lon']},{bounds['max_lat']}"
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=20)
            if response.status_code == 200:
                entries = response.json().get("entries", [])
                print(f"Region '{region_name}': {len(entries)} live port events found.")
                
                for evt in entries:
                    pos = evt.get("position", {})
                    vessel_info = evt.get("vessel", {})
                    dep_port = evt.get("departurePort", {})
                    dest_port = evt.get("destinationPort", {})
                    
                    residency = round(float(evt.get("port_visit", {}).get("durationHrs", 0)), 1)
                    risk_score = 0.85 if residency > 48 else (0.50 if residency > 12 else 0.20)

                    events_found.append({
                        "eventId": evt.get("id"),
                        "vesselName": vessel_info.get("name", "Unknown Vessel"),
                        "mmsi": vessel_info.get("ssvid") or vessel_info.get("mmsi", "N/A"),
                        "flag": vessel_info.get("flag", "UNK"),
                        "vesselType": vessel_info.get("type", "Merchant/Carrier"),
                        "region": region_name,
                        "portName": evt.get("port", {}).get("label", "Regional Port"),
                        "portOfDeparture": dep_port.get("label", "Prior Port"),
                        "portOfDestination": dest_port.get("label", "En Route"),
                        "residenceHours": residency,
                        "biosecurityRiskScore": risk_score,
                        "vesselPos": [pos.get("lat"), pos.get("lon")] if pos.get("lat") else None,
                        "routeCoordinates": [
                            [dep_port.get("position", {}).get("lat"), dep_port.get("position", {}).get("lon")],
                            [pos.get("lat"), pos.get("lon")],
                            [dest_port.get("position", {}).get("lat"), dest_port.get("position", {}).get("lon")]
                        ]
                    })
            else:
                print(f"GFW API returned status {response.status_code} for region {region_name}")
        except Exception as err:
            print(f"Error querying region {region_name}: {err}")

    return events_found

def run_pipeline():
    if not API_TOKEN:
        print("CRITICAL ERROR: 'GFW_API_TOKEN' secret is missing. Pipeline aborted.")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=60)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")

    # 1. First check if user provided a watchlist CSV
    watchlist = load_watchlist_mmsis()
    processed_records = []

    if watchlist:
        # If CSV exists, query those specific MMSIs
        url = "https://gateway.api.globalfishingwatch.org/v3/events"
        headers = {"Authorization": f"Bearer {API_TOKEN}"}
        for item in watchlist:
            mmsi = item["mmsi"]
            params = {
                "datasets": "public-global-port-visits-c2-events:latest",
                "vessels[0]": mmsi,
                "start-date": start_date,
                "end-date": end_date,
                "limit": 50
            }
            try:
                res = requests.get(url, headers=headers, params=params, timeout=15)
                if res.status_code == 200:
                    for evt in res.json().get("entries", []):
                        pos = evt.get("position", {})
                        residency = round(float(evt.get("port_visit", {}).get("durationHrs", 0)), 1)
                        processed_records.append({
                            "eventId": evt.get("id"),
                            "vesselName": item.get("vessel_name", f"MMSI {mmsi}"),
                            "mmsi": mmsi,
                            "flag": item.get("flag", "UNK"),
                            "vesselType": item.get("vessel_type", "Carrier"),
                            "region": "Monitored Corridor",
                            "portName": evt.get("port", {}).get("label", "Port"),
                            "portOfDeparture": evt.get("departurePort", {}).get("label", "Origin"),
                            "portOfDestination": evt.get("destinationPort", {}).get("label", "Destination"),
                            "residenceHours": residency,
                            "biosecurityRiskScore": 0.85 if residency > 48 else 0.50,
                            "vesselPos": [pos.get("lat"), pos.get("lon")],
                            "routeCoordinates": [[pos.get("lat"), pos.get("lon")]]
                        })
            except Exception as e:
                print(f"Error querying MMSI {mmsi}: {e}")
    else:
        # 2. If NO CSV exists, query live spatial events dynamically by bounding boxes
        print("No CSV found. Fetching live regional events dynamically via spatial bounding boxes...")
        processed_records = fetch_dynamic_regional_events(start_date, end_date)

    # Save output
    os.makedirs("data", exist_ok=True)
    pd.DataFrame(processed_records).to_json("data/baseline_risk.json", orient="records", indent=2)
    print(f"Pipeline complete. Saved {len(processed_records)} live events to data/baseline_risk.json.")

if __name__ == "__main__":
    run_pipeline()
