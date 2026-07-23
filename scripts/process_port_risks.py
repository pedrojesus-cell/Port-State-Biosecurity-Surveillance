import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# Environment Variables from GitHub Secrets
API_TOKEN = os.environ.get("GFW_API_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# Path to the vessel watchlist configuration file
CONFIG_PATH = "config/vessels.json"

def load_target_mmsis():
    """Loads target vessel MMSIs dynamically from the JSON configuration file."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                config_data = json.load(f)
                vessels = config_data.get("monitored_vessels", [])
                mmsis = [str(v["mmsi"]) for v in vessels if "mmsi" in v]
                if mmsis:
                    print(f"SUCCESS: Loaded {len(mmsis)} target MMSIs from '{CONFIG_PATH}'.")
                    return mmsis
        except Exception as e:
            print(f"Notice: Could not parse '{CONFIG_PATH}' ({e}). Using default baseline MMSI list.")
    else:
        print(f"Notice: Config file '{CONFIG_PATH}' not found. Using default baseline MMSI list.")
    
    # Fallback MMSI list if config file is missing or invalid
    return ["352001234", "636018912", "538004567"]

# Initialize target MMSI watchlist
TARGET_VESSEL_MMSIS = load_target_mmsis()

def calculate_fouling_risk(speed_knots, residence_hours):
    """Calculates biofouling risk index based on in-port residence time and transit speed."""
    if residence_hours > 48 and speed_knots < 8:
        return 0.85
    elif residence_hours > 12:
        return 0.50
    return 0.20

def send_discord_alert(record):
    """Sends a formatted notification embed to Discord for high-risk targets."""
    if not DISCORD_WEBHOOK_URL:
        return

    payload = {
        "username": "Biosecurity Early Warning",
        "avatar_url": "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png",
        "embeds": [
            {
                "title": f"🚨 HIGH-RISK PORT ENTRY DETECTED: {record['vesselName']}",
                "color": 15548997,
                "fields": [
                    {"name": "Vessel / Flag", "value": f"{record['vesselName']} ({record['flag']})", "inline": True},
                    {"name": "Current/Target Port", "value": str(record['portName']), "inline": True},
                    {"name": "Risk Score", "value": f"**{(record['biosecurityRiskScore'] * 100):.0f}%**", "inline": True},
                    {"name": "Port of Departure", "value": str(record['portOfDeparture']), "inline": True},
                    {"name": "In-Port Duration", "value": f"{record['residenceHours']:.1f} hrs", "inline": True},
                    {"name": "Port of Destination", "value": str(record['portOfDestination']), "inline": True},
                    {"name": "ETA", "value": str(record['eta']), "inline": True}
                ],
                "footer": {"text": "Global Fishing Watch | Biosecurity Surveillance Engine"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as err:
        print(f"Notice: Could not post Discord alert: {err}")

def get_fallback_data():
    """Provides sample baseline dataset if API queries return no live records."""
    return [
        {
            "eventId": "demo-001",
            "vesselName": "PACIFIC HARVEST",
            "mmsi": "352001234",
            "flag": "PAN",
            "vesselType": "Fish Carrier",
            "portName": "Port of Fujairah (Strait of Hormuz)",
            "portOfDeparture": "Port of Guayaquil (ECU)",
            "portOfDestination": "Port of Valparaiso (CHL)",
            "eta": "2026-07-26 14:00 UTC",
            "lat": 25.18,
            "lon": 56.36,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "residenceHours": 52.4,
            "biosecurityRiskScore": 0.85
        },
        {
            "eventId": "demo-002",
            "vesselName": "ATLANTIC CARRIER",
            "mmsi": "636018912",
            "flag": "LBR",
            "vesselType": "Refrigerated Cargo",
            "portName": "Las Palmas (European EEZ)",
            "portOfDeparture": "Port of Abidjan (CIV)",
            "portOfDestination": "Port of Rotterdam (NLD)",
            "eta": "2026-07-29 08:30 UTC",
            "lat": 28.14,
            "lon": -15.42,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "residenceHours": 18.2,
            "biosecurityRiskScore": 0.35
        },
        {
            "eventId": "demo-003",
            "vesselName": "SOUTHERN VENTURE",
            "mmsi": "538004567",
            "flag": "MHL",
            "vesselType": "Fishing Vessel",
            "portName": "Port of Rotterdam (European EEZ)",
            "portOfDeparture": "Port of Apia (WSM)",
            "portOfDestination": "Port of Auckland (NZL)",
            "eta": "2026-07-28 22:00 UTC",
            "lat": 51.92,
            "lon": 4.47,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "residenceHours": 64.0,
            "biosecurityRiskScore": 0.85
        }
    ]

def fetch_port_biosecurity_events():
    processed_records = []

    if API_TOKEN:
        try:
            print(f"Connecting to Global Fishing Watch API for {len(TARGET_VESSEL_MMSIS)} target vessels...")
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=30)

            url = "https://gateway.api.globalfishingwatch.org/v3/events"
            headers = {
                "Authorization": f"Bearer {API_TOKEN}",
                "User-Agent": "MarineBiosecurityMonitor/1.0"
            }

            for mmsi in TARGET_VESSEL_MMSIS:
                params = {
                    "datasets": "public-global-port-visits-c2-events:latest",
                    "vessels[0]": mmsi,
                    "start-date": start_date.strftime("%Y-%m-%d"),
                    "end-date": end_date.strftime("%Y-%m-%d"),
                    "limit": 50,
                    "offset": 0
                }

                response = requests.get(url, headers=headers, params=params, timeout=15)
                
                if response.status_code == 200:
                    data = response.json()
                    events = data.get("entries", [])
                    print(f"MMSI {mmsi}: Retrieved {len(events)} events.")

                    for evt in events:
                        vessel_info = evt.get("vessel", {})
                        port_info = evt.get("port_visit", {})
                        residency = round(float(port_info.get("durationHrs", 0)), 1)

                        risk_index = calculate_fouling_risk(
                            speed_knots=evt.get("meanSpeed", 10),
                            residence_hours=residency
                        )

                        rec = {
                            "eventId": evt.get("id"),
                            "vesselName": vessel_info.get("name", f"Vessel {mmsi}"),
                            "mmsi": vessel_info.get("ssvid", mmsi),
                            "flag": vessel_info.get("flag", "UNK"),
                            "vesselType": vessel_info.get("type", "Fish Carrier"),
                            "portName": evt.get("port", {}).get("label", "Coastal Port"),
                            "portOfDeparture": evt.get("departurePort", {}).get("label", "Prior Anchorage"),
                            "portOfDestination": evt.get("destinationPort", {}).get("label", "En Route"),
                            "eta": evt.get("eta", "N/A"),
                            "lat": evt.get("position", {}).get("lat"),
                            "lon": evt.get("position", {}).get("lon"),
                            "timestamp": evt.get("start"),
                            "residenceHours": residency,
                            "biosecurityRiskScore": risk_index
                        }

                        if rec["biosecurityRiskScore"] >= 0.70:
                            send_discord_alert(rec)

                        processed_records.append(rec)
                else:
                    print(f"MMSI {mmsi} API Query Status: {response.status_code}")

            if not processed_records:
                print("Notice: No live events returned for targeted MMSIs. Loading baseline fallback dataset.")
                processed_records = get_fallback_data()

        except Exception as e:
            print(f"API Exception: {e}. Loading baseline fallback dataset.")
            processed_records = get_fallback_data()
    else:
        print("GFW Token missing. Loading baseline fallback dataset.")
        processed_records = get_fallback_data()

    # Ensure output directory exists
    os.makedirs("data", exist_ok=True)

    # 1. Save Full JSON Output for Web UI
    json_path = "data/baseline_risk.json"
    full_df = pd.DataFrame(processed_records)
    full_df.to_json(json_path, orient="records", indent=2)
    print(f"SUCCESS: Saved {len(processed_records)} total records to '{json_path}'.")

    # 2. Save Filtered CSV Export for High-Risk Targets (>= 70%)
    csv_path = "data/high_risk_summary.csv"
    high_risk_records = [r for r in processed_records if r.get("biosecurityRiskScore", 0) >= 0.70]

    if high_risk_records:
        high_risk_df = pd.DataFrame(high_risk_records)
        export_cols = [
            "vesselName", "flag", "vesselType", "mmsi", 
            "portName", "portOfDeparture", "portOfDestination", 
            "residenceHours", "biosecurityRiskScore", "eta", "timestamp"
        ]
        available_cols = [c for c in export_cols if c in high_risk_df.columns]
        high_risk_df[available_cols].to_csv(csv_path, index=False)
        print(f"SUCCESS: Saved {len(high_risk_records)} high-risk records to '{csv_path}'.")
    else:
        # Create empty CSV template with headers if no high-risk targets exist
        pd.DataFrame(columns=[
            "vesselName", "flag", "vesselType", "mmsi", 
            "portName", "portOfDeparture", "portOfDestination", 
            "residenceHours", "biosecurityRiskScore", "eta", "timestamp"
        ]).to_csv(csv_path, index=False)
        print("Notice: Saved empty high-risk CSV template to 'data/high_risk_summary.csv'.")

if __name__ == "__main__":
    fetch_port_biosecurity_events()
