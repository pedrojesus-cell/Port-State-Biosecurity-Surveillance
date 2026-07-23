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
    }
}

def is_within_region(lat, lon, region_coords):
    """Checks if coordinates fall within a region bounding box."""
    if lat is None or lon is None:
        return False
    return (
        region_coords["min_lat"] <= lat <= region_coords["max_lat"] and
        region_coords["min_lon"] <= lon <= region_coords["max_lon"]
    )

def calculate_fouling_risk(speed_knots, residence_hours):
    """Calculates biofouling risk index based on residence duration and speed."""
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
                "title": f"🚨 REGIONAL HIGH-RISK ENTRY: {record['vesselName']}",
                "color": 15548997,
                "fields": [
                    {"name": "Vessel / Flag", "value": f"{record['vesselName']} ({record['flag']})", "inline": True},
                    {"name": "Port / Region", "value": f"{record['portName']} ({record['region']})", "inline": True},
                    {"name": "Risk Score", "value": f"**{(record['biosecurityRiskScore'] * 100):.0f}%**", "inline": True},
                    {"name": "Port of Departure", "value": str(record['portOfDeparture']), "inline": True},
                    {"name": "In-Port Duration", "value": f"{record['residenceHours']:.1f} hrs", "inline": True},
                    {"name": "Port of Destination", "value": str(record['portOfDestination']), "inline": True}
                ],
                "footer": {"text": "Global Fishing Watch | Regional Biosecurity Engine"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as err:
        print(f"Notice: Could not post Discord alert: {err}")

def fetch_regional_port_events():
    if not API_TOKEN:
        print("CRITICAL ERROR: 'GFW_API_TOKEN' secret is missing. API query aborted.")
        sys.exit(1)

    processed_records = []
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=90)

    url = "https://gateway.api.globalfishingwatch.org/v3/events"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityMonitor/1.0"
    }

    print("Fetching regional port events from Global Fishing Watch API...")

    params = {
        "datasets": "public-global-port-visits-c2-events:latest",
        "start-date": start_date.strftime("%Y-%m-%d"),
        "end-date": end_date.strftime("%Y-%m-%d"),
        "limit": 100,
        "offset": 0
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        if response.status_code == 200:
            data = response.json()
            events = data.get("entries", [])
            print(f"Retrieved {len(events)} total global events. Filtering by region...")

            for evt in events:
                pos = evt.get("position", {})
                lat, lon = pos.get("lat"), pos.get("lon")

                matched_region = None
                for region_name, coords in TARGET_REGIONS.items():
                    if is_within_region(lat, lon, coords):
                        matched_region = region_name
                        break

                # Keep only vessels located inside the target regions
                if matched_region:
                    vessel_info = evt.get("vessel", {})
                    port_info = evt.get("port_visit", {})
                    residency = round(float(port_info.get("durationHrs", 0)), 1)

                    risk_index = calculate_fouling_risk(
                        speed_knots=evt.get("meanSpeed", 10),
                        residence_hours=residency
                    )

                    rec = {
                        "eventId": evt.get("id"),
                        "vesselName": vessel_info.get("name", f"MMSI {vessel_info.get('ssvid', 'UNK')}"),
                        "mmsi": vessel_info.get("ssvid", "N/A"),
                        "flag": vessel_info.get("flag", "UNK"),
                        "vesselType": vessel_info.get("type", "Fish Carrier"),
                        "region": matched_region,
                        "portName": evt.get("port", {}).get("label", "Regional Port"),
                        "portOfDeparture": evt.get("departurePort", {}).get("label", "Prior Anchorage"),
                        "portOfDestination": evt.get("destinationPort", {}).get("label", "En Route"),
                        "eta": evt.get("eta", "N/A"),
                        "lat": lat,
                        "lon": lon,
                        "timestamp": evt.get("start"),
                        "residenceHours": residency,
                        "biosecurityRiskScore": risk_index
                    }

                    if rec["biosecurityRiskScore"] >= 0.70:
                        send_discord_alert(rec)

                    processed_records.append(rec)

            print(f"SUCCESS: Filtered {len(processed_records)} vessels inside target regions.")

        else:
            print(f"API Error {response.status_code}: {response.text}")
    except Exception as err:
        print(f"ERROR querying GFW API: {err}")

    # Ensure output directory exists
    os.makedirs("data", exist_ok=True)

    # 1. Save Full JSON Output for Web UI
    json_path = "data/baseline_risk.json"
    pd.DataFrame(processed_records).to_json(json_path, orient="records", indent=2)

    # 2. Save Filtered CSV Export for High-Risk Targets (>= 70%)
    csv_path = "data/high_risk_summary.csv"
    high_risk_records = [r for r in processed_records if r.get("biosecurityRiskScore", 0) >= 0.70]
    pd.DataFrame(high_risk_records).to_csv(csv_path, index=False)

if __name__ == "__main__":
    fetch_regional_port_events()
