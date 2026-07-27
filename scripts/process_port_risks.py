import os
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# Environment Variables from GitHub Secrets
API_TOKEN = os.environ.get("GFW_API_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

CSV_WATCHLIST_PATH = "config/mmsi_watchlist.csv"

# Monitored Corridor Bounding Boxes
TARGET_REGIONS = {
    "Strait of Hormuz": {
        "min_lat": 24.0, "max_lat": 27.5,
        "min_lon": 54.0, "max_lon": 58.0
    },
    "European EEZ": {
        "min_lat": 48.0, "max_lat": 60.0,
        "min_lon": -10.0, "max_lon": 12.0
    },
    "South America EEZ": {
        "min_lat": -55.0, "max_lat": 12.0,
        "min_lon": -82.0, "max_lon": -34.0
    }
}

def load_watchlist_mmsis():
    """
    Loads target vessel MMSIs from CSV. 
    If missing, queries GFW API dynamically for active vessels 
    instead of using hardcoded mock vessels.
    """
    # 1. Primary: Load from watchlist CSV if present
    if os.path.exists(CSV_WATCHLIST_PATH):
        try:
            df = pd.read_csv(CSV_WATCHLIST_PATH, dtype={"mmsi": str})
            df["mmsi"] = df["mmsi"].str.strip()
            vessels = df.to_dict(orient="records")
            print(f"SUCCESS: Loaded {len(vessels)} target vessels from '{CSV_WATCHLIST_PATH}'.")
            return vessels
        except Exception as e:
            print(f"WARNING: Could not parse '{CSV_WATCHLIST_PATH}': {e}.")

    # 2. Dynamic Fallback: Query GFW Search API directly for live active carriers
    print(f"NOTICE: '{CSV_WATCHLIST_PATH}' not found. Querying active vessels live from GFW API...")
    
    if not API_TOKEN:
        print("CRITICAL ERROR: No API token available. Returning empty watchlist.")
        return []

    url = "https://gateway.api.globalfishingwatch.org/v3/vessels/search"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityMonitor/1.0"
    }
    params = {
        "where": "vesselType IN ('CARRIER', 'FISHING')",
        "limit": 50
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            entries = response.json().get("entries", [])
            dynamic_vessels = []
            for item in entries:
                ssvid = item.get("ssvid") or item.get("mmsi")
                if ssvid:
                    dynamic_vessels.append({
                        "mmsi": str(ssvid),
                        "vessel_name": item.get("name", f"MMSI {ssvid}"),
                        "vessel_type": item.get("type", "Carrier"),
                        "flag": item.get("flag", "UNK")
                    })
            print(f"SUCCESS: Dynamically fetched {len(dynamic_vessels)} active MMSIs from GFW API.")
            return dynamic_vessels
        else:
            print(f"WARNING: GFW Search API returned status {response.status_code}")
    except Exception as err:
        print(f"ERROR querying GFW Search API: {err}")

    # 3. Clean Empty Fallback
    return []

def match_target_region(lat, lon):
    if lat is None or lon is None:
        return None
    for region_name, bounds in TARGET_REGIONS.items():
        if (bounds["min_lat"] <= lat <= bounds["max_lat"] and
            bounds["min_lon"] <= lon <= bounds["max_lon"]):
            return region_name
    return None

def calculate_fouling_risk(speed_knots, residence_hours):
    if residence_hours > 48 and speed_knots < 8:
        return 0.85
    elif residence_hours > 12:
        return 0.50
    return 0.20

def run_watchlist_pipeline(start_days_ago=30, end_days_ago=15):
    if not API_TOKEN:
        print("CRITICAL ERROR: 'GFW_API_TOKEN' secret is missing. Pipeline aborted.")
        sys.exit(1)

    watchlist = load_watchlist_mmsis()
    if not watchlist:
        print("WARNING: Watchlist is empty. Generating empty output file.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    processed_records = []
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=start_days_ago)).strftime("%Y-%m-%d")
    end_date = (now - timedelta(days=end_days_ago)).strftime("%Y-%m-%d")

    url = "https://gateway.api.globalfishingwatch.org/v3/events"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityMonitor/1.0"
    }

    print(f"Querying GFW API for {len(watchlist)} vessels between {start_date} and {end_date}...")

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
                    
                    dep_lat = dep_port.get("position", {}).get("lat")
                    dep_lon = dep_port.get("position", {}).get("lon")
                    
                    dest_lat = dest_port.get("position", {}).get("lat")
                    dest_lon = dest_port.get("position", {}).get("lon")

                    region_match = match_target_region(vessel_lat, vessel_lon)
                    residency = round(float(evt.get("port_visit", {}).get("durationHrs", 0)), 1)
                    risk_index = calculate_fouling_risk(evt.get("meanSpeed", 10), residency)

                    rec = {
                        "eventId": evt.get("id"),
                        "vesselName": target.get("vessel_name") or evt.get("vessel", {}).get("name", f"MMSI {mmsi}"),
                        "mmsi": mmsi,
                        "flag": target.get("flag") or evt.get("vessel", {}).get("flag", "UNK"),
                        "vesselType": target.get("vessel_type") or evt.get("vessel", {}).get("type", "Fish Carrier"),
                        "region": region_match or "Global / Other",
                        "portName": evt.get("port", {}).get("label", "Regional Port"),
                        "portOfDeparture": dep_port.get("label", "Origin Port"),
                        "portOfDestination": dest_port.get("label", "Destination Port"),
                        "residenceHours": residency,
                        "biosecurityRiskScore": risk_index,
                        "vesselPos": [vessel_lat, vessel_lon] if vessel_lat and vessel_lon else None,
                        "routeCoordinates": [
                            [dep_lat, dep_lon] if dep_lat and dep_lon else None,
                            [vessel_lat, vessel_lon] if vessel_lat and vessel_lon else None,
                            [dest_lat, dest_lon] if dest_lat and dest_lon else None
                        ]
                    }

                    if region_match or rec["biosecurityRiskScore"] >= 0.70:
                        processed_records.append(rec)
        except Exception as err:
            print(f"ERROR querying MMSI {mmsi}: {err}")

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(processed_records).to_json("data/baseline_risk.json", orient="records", indent=2)
    print(f"SUCCESS: Saved {len(processed_records)} route records to 'data/baseline_risk.json'.")

if __name__ == "__main__":
    run_watchlist_pipeline(start_days_ago=30, end_days_ago=15)
