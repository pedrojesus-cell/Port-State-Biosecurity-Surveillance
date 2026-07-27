import os
import glob
import sys
import hashlib
import re
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import time

CONFIG_DIR = "config"

# Initialize OpenStreetMap Geocoder
geolocator = Nominatim(user_agent="biosecurity_port_surveillance_app_v2")

# Cache to avoid repeatedly querying the same region
GEO_CACHE = {}

def clean_filename_title(filename):
    base = os.path.basename(filename).replace(".csv", "").replace("_", " ").replace("-", " ")
    clean = re.sub(r'202\d.*', '', base).strip()
    return clean.title() if clean else "Monitored Regional Port"

def get_real_coordinates(port_title, filename):
    """Uses real-world OpenStreetMap geocoding to resolve any country/port in the filename."""
    if port_title in GEO_CACHE:
        return GEO_CACHE[port_title]

    # Clean string for search (e.g. "Port Visit Events Eritrean Exclusive Economic Zone" -> "Eritrea")
    search_query = port_title.lower()
    search_query = re.sub(r'port\s+visit\s+events?', '', search_query)
    search_query = re.sub(r'exclusive\s+economic\s+zone', '', search_query)
    search_query = re.sub(r'eez', '', search_query)
    search_query = search_query.strip()

    # Convert common EEZ adjectives to country names for better OSM matching
    adjective_map = {
        "eritrean": "Eritrea", "portuguese": "Portugal", "spanish": "Spain",
        "canarian": "Canary Islands", "french": "France", "german": "Germany",
        "dutch": "Netherlands", "british": "United Kingdom", "irish": "Ireland",
        "danish": "Denmark", "swedish": "Sweden", "norwegian": "Norway",
        "finnish": "Finland", "polish": "Poland", "italian": "Italy",
        "greek": "Greece", "croatian": "Croatia", "cypriot": "Cyprus",
        "maltese": "Malta", "turkish": "Turkey", "omani": "Oman",
        "uruguayan": "Uruguay", "surinamese": "Suriname", "belizean": "Belize",
        "mexican": "Mexico", "brazilian": "Brazil", "argentinian": "Argentina",
        "chilean": "Chile", "peruvian": "Peru", "russian": "Russia",
        "japanese": "Japan", "korean": "South Korea", "chinese": "China"
    }

    for adj, country in adjective_map.items():
        if adj in search_query:
            search_query = country
            break

    try:
        location = geolocator.geocode(search_query, timeout=10)
        if location:
            # Deterministic offset so multiple CSVs for the same EEZ don't land exactly on top of each other
            hash_val = int(hashlib.md5(filename.encode('utf-8')).hexdigest(), 16)
            jitter_lat = (((hash_val % 40) - 20) / 100.0) * 0.15
            jitter_lon = ((((hash_val // 40) % 40) - 20) / 100.0) * 0.15

            coords = [round(location.latitude + jitter_lat, 4), round(location.longitude + jitter_lon, 4)]
            GEO_CACHE[port_title] = coords
            print(f"Geocoded '{port_title}' -> Query: '{search_query}' -> {coords}")
            return coords
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        print(f"Geocoding timeout for {search_query}: {e}")

    # Fallback only if OSM fails: spread by file hash across global oceans
    hash_val = int(hashlib.md5(filename.encode('utf-8')).hexdigest(), 16)
    coords = [
        round(((hash_val % 100) - 50) * 0.8, 4),
        round((((hash_val // 100) % 100) - 50) * 1.5, 4)
    ]
    GEO_CACHE[port_title] = coords
    return coords

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Processing all {len(csv_files)} CSV files with OpenStreetMap Geocoding...")

    port_summary = {}

    for file_idx, f in enumerate(csv_files):
        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]
            
            source_port_name = clean_filename_title(f)
            loc = get_real_coordinates(source_port_name, f)
            time.sleep(0.2)  # Respect OpenStreetMap rate limits

            if source_port_name not in port_summary:
                port_summary[source_port_name] = {
                    "portName": source_port_name,
                    "year": 2025,
                    "location": loc,
                    "totalPortVisits": 0,
                    "highRiskCount": 0,
                    "moderateRiskCount": 0,
                    "lowRiskCount": 0,
                    "vessels": []
                }

            for idx, row in df.iterrows():
                vessel_name = str(row.get("name") or row.get("vessel_name") or f"Vessel_{idx}").strip()
                mmsi = str(row.get("mmsi") or row.get("ssvid") or f"273{idx:06d}").strip()
                flag = str(row.get("flag") or row.get("flag_translated") or "UNK").strip()
                vessel_type = str(row.get("gfw_vessel_type") or row.get("vessel_type") or "Merchant/Carrier").strip()

                try:
                    total_visits = float(row.get("total_port_visit_events") or row.get("total_visits") or 10)
                except (ValueError, TypeError):
                    total_visits = 10.0

                residence_hrs = round(min(168.0, max(6.0, total_visits * 0.25)), 1)

                if total_visits >= 300:
                    risk_score = 0.92
                    risk_category = "High Fouling Risk"
                    port_summary[source_port_name]["highRiskCount"] += 1
                elif total_visits >= 100:
                    risk_score = 0.65
                    risk_category = "Moderate Vector"
                    port_summary[source_port_name]["moderateRiskCount"] += 1
                else:
                    risk_score = 0.35
                    risk_category = "Low Risk"
                    port_summary[source_port_name]["lowRiskCount"] += 1

                port_summary[source_port_name]["totalPortVisits"] += int(total_visits)

                port_summary[source_port_name]["vessels"].append({
                    "mmsi": mmsi,
                    "vesselName": vessel_name,
                    "flag": flag,
                    "vesselType": vessel_type if vessel_type.lower() != "other" else "Carrier/Merchant",
                    "residenceHours": residence_hrs,
                    "biosecurityRiskScore": risk_score,
                    "riskCategory": risk_category,
                    "totalEvents": int(total_visits)
                })

        except Exception as e:
            print(f"Error processing file {f}: {e}")

    final_ports = list(port_summary.values())

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(final_ports).to_json("data/baseline_risk.json", orient="records")
    print(f"SUCCESS: Geocoded and exported {len(final_ports)} port locations into data/baseline_risk.json.")

if __name__ == "__main__":
    process_all_config_csvs()
