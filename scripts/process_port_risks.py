def load_watchlist_mmsis():
    """
    Loads target vessel MMSIs from CSV. 
    If missing, queries GFW API dynamically for active carriers/fishing vessels 
    instead of using hardcoded mock vessels.
    """
    csv_path = "config/mmsi_watchlist.csv"

    # 1. Primary: Load from watchlist CSV if present
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, dtype={"mmsi": str})
            df["mmsi"] = df["mmsi"].str.strip()
            vessels = df.to_dict(orient="records")
            print(f"SUCCESS: Loaded {len(vessels)} target vessels from '{csv_path}'.")
            return vessels
        except Exception as e:
            print(f"WARNING: Could not parse '{csv_path}': {e}.")

    # 2. Dynamic Fallback: Query GFW Search API directly for live active carriers
    print(f"NOTICE: '{csv_path}' not found. Fetching live active vessels dynamically from GFW API...")
    
    if not API_TOKEN:
        print("CRITICAL ERROR: No API token available. Returning empty watchlist.")
        return []

    url = "https://gateway.api.globalfishingwatch.org/v3/vessels/search"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": "MarineBiosecurityMonitor/1.0"
    }
    params = {
        "where": "vesselType IN ('CARRIER', 'FISHING')",
        "limit": 50
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            entries = response.json().get("entries", [])
            dynamic_vessels = []
            for item in entries:
                ssvid = item.get("ssvid") or item.get("mmsi")
                if ssvid:
                    dynamic_vessels.append({
                        "mmsi": str(ssvid),
                        "vessel_name": item.get("name", f"MMSI {ssvid}"),
                        "vessel_type": item.get("type", "Carrier"),
                        "flag": item.get("flag", "UNK")
                    })
            print(f"SUCCESS: Dynamically fetched {len(dynamic_vessels)} active MMSIs from GFW.")
            return dynamic_vessels
        else:
            print(f"WARNING: GFW Search API returned status {response.status_code}")
    except Exception as err:
        print(f"ERROR querying GFW Search API: {err}")

    # 3. Clean Empty Fallback (No hardcoded ships!)
    return []
