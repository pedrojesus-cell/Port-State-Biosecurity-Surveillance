import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# Optional Import for GFW API Client
try:
    import gfwapiclient as gfw
    GFW_AVAILABLE = True
except ImportError:
    GFW_AVAILABLE = False

API_TOKEN = os.environ.get("GFW_API_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def calculate_fouling_risk(speed_knots, residence_hours):
    if residence_hours > 48 and speed_knots < 8:
        return 0.85
    elif residence_hours > 12:
        return 0.50
    return 0.20

def send_discord_alert(record):
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
                    {"name": "Target Port", "value": str(record['portName']), "inline": True},
                    {"name": "Risk Score", "value": f"**{(record['biosecurityRiskScore'] * 100):.0f}%**", "inline": True},
                    {"name": "In-Port Residence", "value": f"{record['residenceHours']:.1f} Hours", "inline": True},
                    {"name": "MMSI Identifier", "value": str(record['mmsi']), "inline": True},
                    {"name": "Vessel Type", "value": str(record['vesselType']), "inline": True}
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
    """Generates a default baseline dataset when GFW_API_TOKEN is missing or pending."""
    print("WARNING: GFW_API_TOKEN missing or invalid. Generating fallback biosecurity baseline...")
    return [
        {
            "eventId": "demo-001",
            "vesselName": "PACIFIC HARVEST",
            "mmsi": "352001234",
            "flag": "PAN",
            "vesselType": "Fish Carrier",
            "portName": "Port of Callao",
            "lat": -12.05,
            "lon": -77.15,
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
            "portName": "Las Palmas",
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
            "portName": "Port of Suva",
            "lat": -18.14,
            "lon": 178.42,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "residenceHours": 64.0,
            "biosecurityRiskScore": 0.85
        }
    ]

def fetch_port_biosecurity_events():
    processed_records = []

    if API_TOKEN and GFW_AVAILABLE:
        try:
            print("Connecting to Global Fishing Watch API...")
            client = gfw.Client(access_token=API_TOKEN)
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=14)

            events = client.events.get_events(
                event_type="PORT_VISIT",
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )

            for evt in events:
                vessel_info = evt.get("vessel", {})
                port_info = evt.get("port_visit", {})
                residency = port_info.get("durationHrs", 0)

                risk_index = calculate_fouling_risk(
                    speed_knots=evt.get("meanSpeed", 10),
                    residence_hours=residency
                )

                rec = {
                    "eventId": evt.get("id"),
                    "vesselName": vessel_info.get("name", "Unknown Vessel"),
                    "mmsi": vessel_info.get("ssvid", "N/A"),
                    "flag": vessel_info.get("flag", "UNK"),
                    "vesselType": vessel_info.get("type", "General Cargo"),
                    "portName": port_info.get("intermediateAnchorage", {}).get("label", "Coastal Anchor"),
                    "lat": evt.get("position", {}).get("lat"),
                    "lon": evt.get("position", {}).get("lon"),
                    "timestamp": evt.get("start"),
                    "residenceHours": residency,
                    "biosecurityRiskScore": risk_index
                }

                if rec["biosecurityRiskScore"] >= 0.70:
                    send_discord_alert(rec)

                processed_records.append(rec)
        except Exception as e:
            print(f"API Fetch Failed: {e}")
            processed_records = get_fallback_data()
    else:
        processed_records = get_fallback_data()

    # Save output to static JSON
    os.makedirs("data", exist_ok=True)
    output_path = "data/baseline_risk.json"
    
    # Send alert for high-risk fallback demo records if testing Discord
    for rec in processed_records:
        if rec["biosecurityRiskScore"] >= 0.70:
            send_discord_alert(rec)

    pd.DataFrame(processed_records).to_json(output_path, orient="records", indent=2)
    print(f"SUCCESS: Generated {len(processed_records)} records at '{output_path}'.")

if __name__ == "__main__":
    fetch_port_biosecurity_events()
