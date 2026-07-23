import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

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
    return [
        {
            "eventId": "demo-001",
            "vesselName": "PACIFIC HARVEST",
            "mmsi": "352001234",
            "flag": "PAN",
            "vesselType": "Fish Carrier",
            "portName": "Port of Callao",
            "portOfDeparture": "Port of Guayaquil (ECU)",
            "portOfDestination": "Port of Valparaiso (CHL)",
            "eta": "2026-07-26 14:00 UTC",
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
            "portName": "Port of Suva",
            "portOfDeparture": "Port of Apia (WSM)",
            "portOfDestination": "Port of Auckland (NZL)",
            "eta": "2026-07-28 22:00 UTC",
            "lat": -18.14,
            "lon": 178.42,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "residenceHours": 64.0,
            "biosecurityRiskScore": 0.85
        }
    ]

def fetch_port_biosecurity_events():
    processed_records = []

    if API_TOKEN:
        try:
            print("Connecting to Global Fishing Watch REST API v3...")
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=14)

            url = "https://gateway.api.globalfishingwatch.org/v3/events"
            headers = {
                "Authorization": f"Bearer {API_TOKEN}",
                "Content-Type": "application/json",
                "User-Agent": "MarineBiosecurityMonitor/1.0"
            }

            # POST Payload formatted with both required limit and offset
            payload = {
                "datasets": ["public-global-port-visits-c2-events:latest"],
                "startDate": start_date.strftime("%Y-%m-%d"),
                "endDate": end_date.strftime("%Y-%m-%d"),
                "limit": 100,
                "offset": 0
            }

            response = requests.post(url, headers=headers, json=payload, timeout=25)
            print(f"GFW Response Status Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                events = data.get("entries", [])
                print(f"Retrieved {len(events)} events directly from GFW API.")

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
                        "vesselName": vessel_info.get("name", "Unknown Vessel"),
                        "mmsi": vessel_info.get("ssvid", "N/A"),
                        "flag": vessel_info.get("flag", "UNK"),
                        "vesselType": vessel_info.get("type", "General Cargo"),
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
                print(f"GFW API Error Details: {response.text}")

            if not processed_records:
                print("Notice: API returned 0 records or error. Utilizing fallback dataset.")
                processed_records = get_fallback_data()

        except Exception as e:
            print(f"Direct API Error: {e}. Utilizing fallback baseline dataset.")
            processed_records = get_fallback_data()
    else:
        print("GFW Token missing. Using fallback baseline data.")
        processed_records = get_fallback_data()

    os.makedirs("data", exist_ok=True)
    output_path = "data/baseline_risk.json"
    pd.DataFrame(processed_records).to_json(output_path, orient="records", indent=2)
    print(f"SUCCESS: Exported {len(processed_records)} records to '{output_path}'.")

if __name__ == "__main__":
    fetch_port_biosecurity_events()
