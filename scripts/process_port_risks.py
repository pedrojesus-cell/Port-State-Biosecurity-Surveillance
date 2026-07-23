import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# Environment Variables
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
                    print(f"Successfully loaded {len(mmsis)} MMSIs from '{CONFIG_PATH}'.")
                    return mmsis
        except Exception as e:
            print(f"Notice: Could not parse '{CONFIG_PATH}' ({e}). Using default MMSI list.")
    else:
        print(f"Notice: Config file '{CONFIG_PATH}' not found. Using default MMSI list.")
    
    # Fallback MMSI list if config file is missing or invalid
    return ["352001234", "636018912", "538004567"]

# Initialize target MMSI watchlist
TARGET_VESSEL_MMSIS = load_target_mmsis()
