import os
import requests
import pandas as pd

API_TOKEN = os.environ.get("GFW_API_TOKEN")
OUTPUT_CSV = "config/mmsi_watchlist.csv"

def generate_gfw_watchlist():
    if not API_TOKEN:
        print("Error: GFW_API_TOKEN is missing.")
        return

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityWatchlistGenerator/1.0"
    }

    url = "https://gateway.api.globalfishingwatch.org/v3/vessels/search"
    
    # Query active fish carriers, fishing vessels, and cargo/reefers
    params = {
        "where": "vesselType IN ('CARRIER', 'FISHING', 'CARGO')",
        "limit": 100
    }

    print("Fetching active vessel identity list from GFW API...")
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        if response.status_code == 200:
            entries = response.json().get("entries", [])
            
            watchlist_data = []
            for item in entries:
                ssvid = item.get("ssvid") or item.get("mmsi")
                if ssvid and str(ssvid).isdigit():
                    watchlist_data.append({
                        "mmsi": str(ssvid),
                        "vessel_name": item.get("name", f"Vessel_{ssvid}"),
                        "vessel_type": item.get("type", "Fish Carrier"),
                        "flag": item.get("flag", "UNK")
                    })

            # Create DataFrame and Save to CSV
            df = pd.DataFrame(watchlist_data).drop_duplicates(subset=["mmsi"])
            os.makedirs("config", exist_ok=True)
            df.to_csv(OUTPUT_CSV, index=False)
            print(f"SUCCESS: Generated '{OUTPUT_CSV}' with {len(df)} active MMSIs.")

        else:
            print(f"Failed to fetch vessels from GFW API: Status {response.status_code}")
    except Exception as err:
        print(f"Error querying GFW API: {err}")

if __name__ == "__main__":
    generate_gfw_watchlist()
