import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import gfwapiclient as gfw

# Environment Secrets
API_TOKEN = os.environ.get("GFW_API_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

client = gfw.Client(access_token=API_TOKEN)

def calculate_fouling_risk(speed_knots, residence_hours):
    if residence_hours > 48 and speed_knots < 8:
        return 0.85
    elif residence_hours > 12:
        return 0.50
    return 0.20

def send_discord_alert(record):
    if not DISCORD_WEBHOOK_URL:
        print("INFO: No DISCORD_WEBHOOK_URL found. Skipping notification.")
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
        print(f"SUCCESS: Alert sent for vessel '{record['vesselName']}'.")
    except Exception as err:
        print(f"ERROR: Could not post Discord notification: {err}")

def fetch_port_biosecurity_events():
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=14)
    
    events = client.events.get_events(
        event_type="PORT_VISIT",
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d")
    )
    
    processed_records = []
    
    for evt in events:
        vessel_info = evt.get("vessel", {})
        port_info = evt.get("port_visit", {})
        residency = port_info.get("durationHrs", 0)
        
        risk_index = calculate_fouling_risk(
            speed_knots=evt.get("meanSpeed", 10),
            residence_hours=residency
        )
        
        record = {
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

        if record["biosecurityRiskScore"] >= 0.70:
            send_discord_alert(record)

        processed_records.append(record)
        
    os.makedirs("data", exist_ok=True)
    output_path = "data/baseline_risk.json"
    pd.DataFrame(processed_records).to_json(output_path, orient="records", indent=2)

if __name__ == "__main__":
    fetch_port_biosecurity_events()
