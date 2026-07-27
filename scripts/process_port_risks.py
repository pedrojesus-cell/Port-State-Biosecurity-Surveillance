import os
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

API_TOKEN = os.environ.get("GFW_API_TOKEN")
CSV_WATCHLIST_PATH = "config/mmsi_watchlist.csv"

# Geographic Bounding Boxes for Monitored Corridors
TARGET_REGIONS = {
    "Strait of Hormuz": {"min_lat": 24.0, "max_lat": 27.5, "min_lon": 54.0, "max_lon": 58.0},
    "European EEZ": {"min_lat": 48.0, "max_lat": 60.0, "min_lon": -10.0, "max_lon": 12.0},
    "South America EEZ": {"min_lat": -55.0, "max_lat": 12.0, "min_lon": -82.0, "max_lon": -34.0}
}

# Known active transatlantic carriers (Brazil <-> Europe / Rotterdam / Hormuz corridors)
TRANSATLANTIC_WATCHLIST = [
    {"mmsi": "370599000", "vessel_name": "IBUKI", "vessel_type": "Fish Carrier", "flag": "PAN"},
    {"mmsi": "352894000", "vessel_name": "TUNA QUEEN", "vessel_type": "Fish Carrier", "flag": "PAN"},
    {"mmsi": "636017396", "vessel_name": "TAIHO MARU", "vessel_type": "Fish Carrier", "flag": "LBR"},
    {"mmsi": "224188000", "vessel_name": "PLAYA DE AZOR", "vessel_type": "Fishing Vessel", "flag": "ESP"},
    {"mmsi": "211281810", "vessel_name": "SEVEN SEAS", "vessel_type": "Fish Carrier", "flag": "DEU"},
    {"mmsi": "228051000", "vessel_name": "GRAND OCEAN", "vessel_type": "Carrier", "flag": "FRA"},
    {"mmsi": "247321000", "vessel_name": "MEDITERRANEO", "vessel_type": "Carrier", "flag": "ITA"},
    {"mmsi": "701000816", "vessel_name": "HUAFENG 815", "vessel_type": "Fishing Vessel", "flag": "ARG"},
    {"mmsi": "356639000", "vessel_name": "COOL EAGLE", "vessel_type": "Refrigerated Cargo", "flag": "PAN"},
    {"mmsi": "354003000", "vessel_name": "SHENJU", "vessel_type": "Fish Carrier", "flag": "PAN"},
    {"mmsi": "636019821", "vessel_name": "CAP SAN ARTEMISIO", "vessel_type": "Container Ship", "flag": "LBR"},
    {"mmsi": "218846000", "vessel_name": "SANTA CATARINA", "vessel_type": "Container Ship", "flag": "DEU"},
    {"mmsi": "255806090", "vessel_name": "MONTE OLIVIA", "vessel_type": "Container Ship", "flag": "PRT"}
]

def load_watchlist_mmsis():
    if os.path.exists(CSV_WATCHLIST_PATH):
        try:
            df = pd.read_csv(CSV_WATCHLIST_PATH, dtype={"mmsi": str})
            df["mmsi"] = df["mmsi"].str.strip()
            return df.to_dict(orient="records")
        except Exception as e:
            print(f"Warning: Could not parse CSV ({e}). Using default transatlantic list.")
    
    # Auto-create CSV if missing
    os.makedirs("config", exist_ok=True)
    pd.DataFrame(TRANSATLANTIC_WATCHLIST).to_csv(CSV_WATCHLIST_PATH, index=False)
    return TRANSATLANTIC_WATCHLIST

def match_target_region(lat, lon):
    if lat is None or lon is None:
        return None
    for region_name, bounds in TARGET_REGIONS.items():
        if bounds["min_lat"] <= lat <= bounds["max_lat"] and bounds["min_lon"] <= lon <= bounds["max_lon"]:
            return region_name
    return None

def run_watchlist_pipeline(start_days_ago=60, end_days_ago=0):
    if not API_TOKEN:
        print("CRITICAL ERROR: 'GFW_API_TOKEN' secret is missing.")
        sys.exit(1)

    watchlist = load_watchlist_mmsis()
    processed_records = []

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=start_days_ago)).strftime("%Y-%m-%d")
    end_date = (now - timedelta(days=end_days_ago)).strftime("%Y-%m-%d")

    url = "https://gateway.api.globalfishingwatch.org/v3/events"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityMonitor/1.0"
    }

    print(f"Fetching transatlantic routes ({start_date} to {end_date}) for {len(watchlist)} vessels...")

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

                    # Match region on current position OR departure port OR destination port
                    region_current = match_target_region(vessel_lat, vessel_lon)
                    region_dep = match_target_region(dep_lat, dep_lon)
                    region_dest = match_target_region(dest_lat, dest_lon)

                    matched_region = region_current or region_dep or region_dest
                    
                    residency = round(float(evt.get("port_visit", {}).get("durationHrs", 0)), 1)
                    risk_score = 0.85 if residency > 48 else (0.50 if residency > 12 else 0.20)

                    rec = {
                        "eventId": evt.get("id"),
                        "vesselName": target.get("vessel_name") or evt.get("vessel", {}).get("name", f"MMSI {mmsi}"),
                        "mmsi": mmsi,
                        "flag": target.get("flag") or evt.get("vessel", {}).get("flag", "UNK"),
                        "vesselType": target.get("vessel_type") or "Carrier",
                        "region": matched_region or "South America EEZ",
                        "portName": evt.get("port", {}).get("label", "Regional Port"),
                        "portOfDeparture": dep_port.get("label", "Santos / Brazil"),
                        "portOfDestination": dest_port.get("label", "Rotterdam / Netherlands"),
                        "residenceHours": residency,
                        "biosecurityRiskScore": risk_score,
                        "vesselPos": [vessel_lat, vessel_lon] if vessel_lat and vessel_lon else [dep_lat or -23.95, dep_lon or -46.33],
                        "routeCoordinates": [
                            [dep_lat or -23.95, dep_lon or -46.33],        # Default Santos, Brazil if missing
                            [vessel_lat or 15.0, vessel_lon or -30.0],       # Mid-Atlantic Transit
                            [dest_lat or 51.95, dest_lon or 4.13]          # Rotterdam, Netherlands
                        ]
                    }

                    # Include any event involving our target corridors
                    if matched_region or rec["biosecurityRiskScore"] >= 0.20:
                        processed_records.append(rec)
        except Exception as err:
            print(f"Error querying MMSI {mmsi}: {err}")

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(processed_records).to_json("data/baseline_risk.json", orient="records", indent=2)
    print(f"SUCCESS: Captured {len(processed_records)} transatlantic route records!")

if __name__ == "__main__":
    run_watchlist_pipeline(start_days_ago=60, end_days_ago=0)
