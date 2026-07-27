import os
import json
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# Environment Variables from GitHub Secrets
API_TOKEN = os.environ.get("GFW_API_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

CONFIG_PATH = "config/vessels.json"

def load_target_mmsis():
    """Loads target vessel MMSIs dynamically from config/vessels.json."""
    if not os.path.exists(CONFIG_PATH):
        print(f"CRITICAL ERROR: Configuration file '{CONFIG_PATH}' not found.")
        sys.exit(1)

    try:
        with open(CONFIG_PATH, "r") as f:
            config_data = json.load(f)
            vessels = config_data.get("monitored_vessels", [])
            mmsis = [str(v["mmsi"]) for v in vessels if "mmsi" in v]
            if not mmsis:
                print(f"CRITICAL ERROR: No valid MMSIs found in '{CONFIG_PATH}'.")
                sys.exit(1)
            print(f"SUCCESS: Loaded {len(mmsis)} target MMSIs from '{CONFIG_PATH}'.")
            return mmsis
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to parse '{CONFIG_PATH}': {e}")
        sys.exit(1)

def calculate_fouling_risk(speed_knots, residence_hours):
    """Calculates biofouling risk index based on in-port residence time and transit speed."""
    if residence_hours > 48 and speed_knots < 8:
        return 0.85
    elif residence_hours > 12:
        return 0.50
    return 0.20

def send_discord_alert(record):
    """Sends a notification embed to Discord for high-risk targets."""
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

def fetch_port_biosecurity_events():
    if not API_TOKEN:
        print("CRITICAL ERROR: 'GFW_API_TOKEN' secret is missing. Real-time API query aborted.")
        sys.exit(1)

    target_mmsis = load_target_mmsis()
    processed_records = []

    print(f"Connecting to Global Fishing Watch API v3 for {len(target_mmsis)} target vessels...")
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=90)  # Extended timeframe to capture port visits

    url = "https://gateway.api.globalfishingwatch.org/v3/events"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityMonitor/1.0"
    }

    for mmsi in target_mmsis:
        params = {
            "datasets": "public-global-port-visits-c2-events:latest",
            "vessels[0]": mmsi,
            "start-date": start_date.strftime("%Y-%m-%d"),
            "end-date": end_date.strftime("%Y-%m-%d"),
            "limit": 50,
            "offset": 0
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                events = data.get("entries", [])
                print(f"MMSI {mmsi}: Retrieved {len(events)} live port events.")

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
                print(f"WARNING: MMSI {mmsi} API returned status {response.status_code}: {response.text}")
        except Exception as err:
            print(f"ERROR: Failed to query GFW API for MMSI {mmsi}: {err}")

    # Ensure output directory exists
    os.makedirs("data", exist_ok=True)

    # 1. Save Full JSON Output
    json_path = "data/baseline_risk.json"
    full_df = pd.DataFrame(processed_records)
    full_df.to_json(json_path, orient="records", indent=2)
    print(f"SUCCESS: Saved {len(processed_records)} real-time records to '{json_path}'.")

    # 2. Save High-Risk CSV Summary (>= 70%)
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
        pd.DataFrame(columns=[
            "vesselName", "flag", "vesselType", "mmsi", 
            "portName", "portOfDeparture", "portOfDestination", 
            "residenceHours", "biosecurityRiskScore", "eta", "timestamp"
        ]).to_csv(csv_path, index=False)
        print("Notice: No high-risk arrivals found. Saved empty high-risk CSV summary.")

if __name__ == "__main__":
    fetch_port_biosecurity_events()
