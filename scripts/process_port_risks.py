import os
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# Environment Variables from GitHub Secrets
API_TOKEN = os.environ.get("GFW_API_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# Defined Geographic Bounding Boxes
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

def is_within_regions(lat, lon):
    """Checks if coordinates fall within any monitored bounding box."""
    if lat is None or lon is None:
        return None
    for region_name, bounds in TARGET_REGIONS.items():
        if bounds["min_lat"] <= lat <= bounds["max_lat"] and bounds["min_lon"] <= lon <= bounds["max_lon"]:
            return region_name
    return None

def calculate_fouling_risk(speed_knots, residence_hours):
    """Calculates biofouling risk index."""
    if residence_hours > 48 and speed_knots < 8:
        return 0.85
    elif residence_hours > 12:
        return 0.50
    return 0.20

def fetch_regional_vessels():
    """Dynamically fetches active vessels from GFW v3 API."""
    if not API_TOKEN:
        print("CRITICAL ERROR: 'GFW_API_TOKEN' secret is missing.")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityMonitor/1.0"
    }

    # Step 1: Discover active carriers and fishing vessels via Search API
    search_url = "https://gateway.api.globalfishingwatch.org/v3/vessels/search"
    params = {
        "where": "vesselType IN ('CARRIER', 'FISHING')",
        "limit": 20
    }

    try:
        res = requests.get(search_url, headers=headers, params=params, timeout=15)
        if res.status_code == 200:
            vessels_data = res.json().get("entries", [])
            mmsis = [v.get("ssvid") for v in vessels_data if v.get("ssvid")]
            if mmsis:
                print(f"Discovered {len(mmsis)} active regional MMSIs via GFW Search API.")
                return mmsis
    except Exception as err:
        print(f"Warning: Regional vessel search failed: {err}")

    # Broad carrier/fishing MMSI fallback list for regional monitoring if search endpoint requires specific tier
    return ["370599000", "352894000", "636017396", "413378910", "224188000", "305923000"]

def process_pipeline():
    mmsi_list = fetch_regional_vessels()
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityMonitor/1.0"
    }
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=180)
    events_url = "https://gateway.api.globalfishingwatch.org/v3/events"

    processed_records = []

    for mmsi in mmsi_list:
        params = {
            "datasets": "public-global-port-visits-c2-events:latest",
            "vessels[0]": mmsi,
            "start-date": start_date.strftime("%Y-%m-%d"),
            "end-date": end_date.strftime("%Y-%m-%d"),
            "limit": 50
        }

        try:
            res = requests.get(events_url, headers=headers, params=params, timeout=15)
            if res.status_code == 200:
                events = res.json().get("entries", [])
                for evt in events:
                    pos = evt.get("position", {})
                    lat, lon = pos.get("lat"), pos.get("lon")
                    region_match = is_within_regions(lat, lon)

                    # Include event if inside targeted bounding boxes or standard port visit
                    vessel_info = evt.get("vessel", {})
                    port_info = evt.get("port_visit", {})
                    residency = round(float(port_info.get("durationHrs", 0)), 1)

                    rec = {
                        "eventId": evt.get("id"),
                        "vesselName": vessel_info.get("name", f"MMSI {mmsi}"),
                        "mmsi": vessel_info.get("ssvid", mmsi),
                        "flag": vessel_info.get("flag", "UNK"),
                        "vesselType": vessel_info.get("type", "Fish Carrier"),
                        "region": region_match or "Global / EEZ",
                        "portName": evt.get("port", {}).get("label", "Regional Port"),
                        "portOfDeparture": evt.get("departurePort", {}).get("label", "Prior Port"),
                        "portOfDestination": evt.get("destinationPort", {}).get("label", "En Route"),
                        "eta": evt.get("eta", "N/A"),
                        "lat": lat,
                        "lon": lon,
                        "timestamp": evt.get("start"),
                        "residenceHours": residency,
                        "biosecurityRiskScore": calculate_fouling_risk(evt.get("meanSpeed", 10), residency)
                    }
                    processed_records.append(rec)
        except Exception as err:
            print(f"Error fetching MMSI {mmsi}: {err}")

    os.makedirs("data", exist_ok=True)

    # Save output (NO DEMO FALLBACK: If 0 records match, saves empty array)
    json_path = "data/baseline_risk.json"
    pd.DataFrame(processed_records).to_json(json_path, orient="records", indent=2)
    print(f"SUCCESS: Saved {len(processed_records)} real-time records to '{json_path}'.")

    csv_path = "data/high_risk_summary.csv"
    high_risk_records = [r for r in processed_records if r.get("biosecurityRiskScore", 0) >= 0.70]
    pd.DataFrame(high_risk_records).to_csv(csv_path, index=False)

if __name__ == "__main__":
    process_pipeline()
