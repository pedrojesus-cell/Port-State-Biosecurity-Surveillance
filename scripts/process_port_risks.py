import os
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# Environment Variables from GitHub Secrets
API_TOKEN = os.environ.get("GFW_API_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

CSV_WATCHLIST_PATH = "config/mmsi_watchlist.csv"

# Defined Geographic Bounding Boxes for Corridor Tracking
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
    Loads target vessel MMSIs from CSV. If the CSV file is missing,
    it automatically creates config/mmsi_watchlist.csv with baseline vessels
    to prevent pipeline crashes.
    """
    default_vessels = [
        {"mmsi": "370599000", "vessel_name": "IBUKI", "vessel_type": "Fish Carrier", "flag": "PAN"},
        {"mmsi": "352894000", "vessel_name": "TUNA QUEEN", "vessel_type": "Fish Carrier", "flag": "PAN"},
        {"mmsi": "636017396", "vessel_name": "TAIHO MARU", "vessel_type": "Fish Carrier", "flag": "LBR"},
        {"mmsi": "413378910", "vessel_name": "ZHONGHAI 1", "vessel_type": "Carrier", "flag": "CHN"},
        {"mmsi": "224188000", "vessel_name": "PLAYA DE AZOR", "vessel_type": "Fishing Vessel", "flag": "ESP"},
        {"mmsi": "211281810", "vessel_name": "SEVEN SEAS", "vessel_type": "Fish Carrier", "flag": "DEU"}
    ]

    if not os.path.exists(CSV_WATCHLIST_PATH):
        print(f"NOTICE: Watchlist file '{CSV_WATCHLIST_PATH}' not found.")
        print("Automatically creating baseline 'config/mmsi_watchlist.csv'...")
        try:
            os.makedirs("config", exist_ok=True)
            df_default = pd.DataFrame(default_vessels)
            df_default.to_csv(CSV_WATCHLIST_PATH, index=False)
            print(f"SUCCESS: Created baseline watchlist at '{CSV_WATCHLIST_PATH}'.")
            return default_vessels
        except Exception as e:
            print(f"WARNING: Could not write default file ({e}). Proceeding in-memory.")
            return default_vessels

    try:
        df = pd.read_csv(CSV_WATCHLIST_PATH, dtype={"mmsi": str})
        df["mmsi"] = df["mmsi"].str.strip()
        vessels = df.to_dict(orient="records")
        print(f"SUCCESS: Loaded {len(vessels)} target vessels from '{CSV_WATCHLIST_PATH}'.")
        return vessels
    except Exception as e:
        print(f"WARNING: Could not parse '{CSV_WATCHLIST_PATH}': {e}. Falling back to default list.")
        return default_vessels

def match_target_region(lat, lon):
    """Checks if coordinates fall inside any target corridor bounding box."""
    if lat is None or lon is None:
        return None
    for region_name, bounds in TARGET_REGIONS.items():
        if (bounds["min_lat"] <= lat <= bounds["max_lat"] and
            bounds["min_lon"] <= lon <= bounds["max_lon"]):
            return region_name
    return None

def calculate_fouling_risk(speed_knots, residence_hours):
    """Calculates biofouling risk index based on speed and residence time."""
    if residence_hours > 48 and speed_knots < 8:
        return 0.85
    elif residence_hours > 12:
        return 0.50
    return 0.20

def send_discord_alert(record):
    """Sends notification embed to Discord for high-risk targets."""
    if not DISCORD_WEBHOOK_URL:
        return

    payload = {
        "username": "Biosecurity Early Warning",
        "avatar_url": "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png",
        "embeds": [
            {
                "title": f"🚨 HIGH-RISK PORT ARRIVAL: {record['vesselName']}",
                "color": 15548997,
                "fields": [
                    {"name": "Vessel / Flag", "value": f"{record['vesselName']} ({record['flag']})", "inline": True},
                    {"name": "MMSI", "value": str(record['mmsi']), "inline": True},
                    {"name": "Risk Score", "value": f"**{(record['biosecurityRiskScore'] * 100):.0f}%**", "inline": True},
                    {"name": "Port / Region", "value": f"{record['portName']} ({record['region']})", "inline": True},
                    {"name": "Departure Port", "value": str(record['portOfDeparture']), "inline": True},
                    {"name": "In-Port Duration", "value": f"{record['residenceHours']:.1f} hrs", "inline": True}
                ],
                "footer": {"text": "GFW Biosecurity Surveillance Engine"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as err:
        print(f"Notice: Could not post Discord alert: {err}")

def run_watchlist_pipeline(start_days_ago=30, end_days_ago=15):
    if not API_TOKEN:
        print("CRITICAL ERROR: 'GFW_API_TOKEN' secret is missing. Pipeline aborted.")
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
                print(f"MMSI {mmsi} ({target.get('vessel_name', 'Unknown')}): {len(events)} events found.")

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
                    
                    port_info = evt.get("port_visit", {})
                    residency = round(float(port_info.get("durationHrs", 0)), 1)

                    risk_index = calculate_fouling_risk(
                        speed_knots=evt.get("meanSpeed", 10),
                        residence_hours=residency
                    )

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
                        "eta": evt.get("eta", "N/A"),
                        "lat": vessel_lat,
                        "lon": vessel_lon,
                        "timestamp": evt.get("start"),
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
                        if rec["biosecurityRiskScore"] >= 0.70:
                            send_discord_alert(rec)
                        processed_records.append(rec)

            else:
                print(f"WARNING: MMSI {mmsi} API returned status {response.status_code}")
        except Exception as err:
            print(f"ERROR querying MMSI {mmsi}: {err}")

    # Output Management
    os.makedirs("data", exist_ok=True)

    json_path = "data/baseline_risk.json"
    pd.DataFrame(processed_records).to_json(json_path, orient="records", indent=2)
    print(f"SUCCESS: Saved {len(processed_records)} route records to '{json_path}'.")

    csv_path = "data/high_risk_summary.csv"
    high_risk = [r for r in processed_records if r.get("biosecurityRiskScore", 0) >= 0.70]
    pd.DataFrame(high_risk).to_csv(csv_path, index=False)

if __name__ == "__main__":
    run_watchlist_pipeline(start_days_ago=30, end_days_ago=15)
