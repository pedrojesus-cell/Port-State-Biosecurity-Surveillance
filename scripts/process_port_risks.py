import os
import glob
import re
import json
import pandas as pd

CONFIG_DIR = "config"
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "baseline_risk.json")

# COMPLETE MARITIME EEZ & REGIONAL COORDINATES
COORDINATE_MAP = {
    # --- SOUTH AMERICA & CARIBBEAN ---
    "guyanese": [5.0000, -58.7000], "guyana": [5.0000, -58.7000],
    "surinamese": [5.8500, -55.2000], "suriname": [5.8500, -55.2000],
    "uruguayan": [-34.9000, -56.1600], "uruguay": [-34.9000, -56.1600],
    "brazilian": [-23.9608, -46.3331], "brazil": [-23.9608, -46.3331],
    "argentinian": [-34.6000, -58.3800], "argentina": [-34.6000, -58.3800],
    "chilean": [-33.0400, -71.6200], "chile": [-33.0400, -71.6200],
    "peruvian": [-12.0400, -77.1400], "peru": [-12.0400, -77.1400],
    "colombian": [10.3910, -75.4794], "colombia": [10.3910, -75.4794],
    "venezuelan": [10.5000, -66.9000], "venezuela": [10.5000, -66.9000],
    "belizean": [17.5000, -88.1800], "belize": [17.5000, -88.1800],
    "mexican": [19.2000, -96.1300], "mexico": [19.2000, -96.1300],
    "panamanian": [8.9800, -79.5200], "panama": [8.9800, -79.5200],

    # --- ATLANTIC ISLANDS & IBERIA ---
    "madeira": [32.6500, -16.9000],
    "azores": [37.7400, -25.6600],
    "canary": [28.1200, -15.4300],
    "portuguese": [38.7100, -9.1300], "portugal": [38.7100, -9.1300],
    "viana": [41.6932, -8.8329],
    "spanish": [36.5300, -6.2900], "spain": [36.5300, -6.2900],

    # --- MIDDLE EAST, RED SEA & PERSIAN GULF ---
    "bahraini": [26.0667, 50.5500], "bahrain": [26.0667, 50.5500],
    "yemeni": [15.5527, 48.5164], "yemen": [15.5527, 48.5164],
    "omani": [23.6100, 58.5900], "oman": [23.6100, 58.5900],
    "emirates": [25.2700, 55.2900], "uae": [25.2700, 55.2900], "emirati": [25.2700, 55.2900],
    "qatari": [25.3548, 51.1839], "qatar": [25.3548, 51.1839],
    "eritrean": [15.1700, 39.7800], "eritrea": [15.1700, 39.7800],
    "egyptian": [29.9600, 32.5500], "egypt": [29.9600, 32.5500],

    # --- MEDITERRANEAN & BLACK SEA ---
    "maltese": [35.8900, 14.5100], "malta": [35.8900, 14.5100],
    "italian": [40.8500, 14.2600], "italy": [40.8500, 14.2600],
    "greek": [37.9400, 23.6400], "greece": [37.9400, 23.6400],
    "croatian": [43.5100, 16.4400], "croatia": [43.5100, 16.4400],
    "cypriot": [34.6700, 33.0400], "cyprus": [34.6700, 33.0400],
    "turkish": [41.0100, 28.9700], "turkey": [41.0100, 28.9700],
    "bulgarian": [43.2100, 27.9100], "bulgaria": [43.2100, 27.9100],
    "romanian": [44.1800, 28.6300], "romania": [44.1800, 28.6300],
    "ukraine": [45.3000, 33.0000], "ukrainian": [45.3000, 33.0000],
    "overlapping claim": [45.3000, 33.0000],

    # --- NORTHERN & WESTERN EUROPE ---
    "french": [48.3900, -4.4800], "france": [48.3900, -4.4800],
    "british": [50.8000, -1.0800], "uk": [50.8000, -1.0800],
    "irish": [51.8900, -8.4700], "ireland": [51.8900, -8.4700],
    "dutch": [51.9800, 3.9000], "netherlands": [51.9800, 3.9000],
    "german": [53.5500, 9.9900], "germany": [53.5500, 9.9900],
    "belgian": [51.3300, 3.2200], "belgium": [51.3300, 3.2200],
    "danish": [55.6700, 12.5600], "denmark": [55.6700, 12.5600],
    "swedish": [57.7000, 11.9600], "sweden": [57.7000, 11.9600],
    "norwegian": [60.3900, 5.3200], "norway": [60.3900, 5.3200],
    "finnish": [60.1700, 24.9400], "finland": [60.1700, 24.9400],
    "polish": [54.3500, 18.6600], "poland": [54.3500, 18.6600],

    # --- AFRICA & ASIA ---
    "moroccan": [35.7800, -5.8000], "morocco": [35.7800, -5.8000],
    "algerian": [36.7500, 3.0500], "algeria": [36.7500, 3.0500],
    "tunisian": [36.8000, 10.1800], "tunisia": [36.8000, 10.1800],
    "senegalese": [14.6900, -17.4400], "senegal": [14.6900, -17.4400],
    "ghanaian": [5.5500, -0.2000], "ghana": [5.5500, -0.2000],
    "angolan": [-8.8300, 13.2300], "angola": [-8.8300, 13.2300],
    "japanese": [35.4400, 139.6300], "japan": [35.4400, 139.6300],
    "chinese": [31.2300, 121.4700], "china": [31.2300, 121.4700],
    "singaporean": [1.2900, 103.8500], "singapore": [1.2900, 103.8500]
}

def clean_title(filename):
    base = os.path.basename(filename).replace(".csv", "").replace("_", " ").replace("-", " ")
    clean = re.sub(r'port\s+visit\s+events?', '', base, flags=re.IGNORECASE)
    clean = re.sub(r'exclusive\s+economic\s+zone', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'eez', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'202\d.*', '', clean).strip()
    return clean.title() if clean else "Monitored Zone"

def get_coordinates(title, filename):
    lookup = f"{title} {filename}".lower()
    if "madeira" in lookup: return [32.6500, -16.9000]
    if "azores" in lookup: return [37.7400, -25.6600]
    if "canary" in lookup: return [28.1200, -15.4300]
    
    for key, coords in COORDINATE_MAP.items():
        if key in lookup:
            return coords
    return [38.7100, -9.1300]

def process_datasets():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))
    # Exclude reference anchorages files
    csv_files = [f for f in all_files if "anchorage" not in os.path.basename(f).lower()]

    if not csv_files:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
            json.dump([], out)
        return

    results = []

    for file_path in csv_files:
        fname = os.path.basename(file_path)
        title = clean_title(fname)
        coords = get_coordinates(title, fname)

        entry = {
            "portName": title,
            "year": 2026,
            "location": coords,
            "totalPortVisits": 0,
            "highRiskCount": 0,
            "moderateRiskCount": 0,
            "lowRiskCount": 0,
            "vessels": []
        }

        try:
            df = pd.read_csv(file_path, low_memory=False)
            df.columns = [str(c).lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

            for idx, row in df.iterrows():
                try:
                    vessel_name = str(row.get("name") or row.get("vessel_name") or f"Vessel_{idx}").strip()
                    mmsi = str(row.get("mmsi") or row.get("ssvid") or f"273{idx:06d}").strip()
                    flag = str(row.get("flag") or row.get("flag_translated") or "UNK").strip()
                    vessel_type = str(row.get("gfw_vessel_type") or row.get("vessel_type") or "Carrier/Merchant").strip()

                    try:
                        visits = float(row.get("total_port_visit_events") or row.get("total_visits") or 1)
                    except (ValueError, TypeError):
                        visits = 1.0

                    residence_hrs = float(round(min(168.0, max(6.0, visits * 0.25)), 1))

                    if visits >= 15:
                        risk_score, risk_cat = 0.92, "High Fouling Risk"
                        entry["highRiskCount"] += 1
                    elif visits >= 5:
                        risk_score, risk_cat = 0.65, "Moderate Vector"
                        entry["moderateRiskCount"] += 1
                    else:
                        risk_score, risk_cat = 0.35, "Low Risk"
                        entry["lowRiskCount"] += 1

                    entry["totalPortVisits"] += int(visits)
                    entry["vessels"].append({
                        "mmsi": mmsi,
                        "vesselName": vessel_name,
                        "flag": flag,
                        "vesselType": vessel_type if vessel_type.lower() != "other" else "Carrier/Merchant",
                        "residenceHours": residence_hrs,
                        "biosecurityRiskScore": risk_score,
                        "riskCategory": risk_cat,
                        "totalEvents": int(visits)
                    })
                except Exception:
                    continue

            results.append(entry)

        except Exception as err:
            print(f"Skipping unreadable file {fname}: {err}")

    # Output using native json library to prevent int64 serialization errors
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(results, out, indent=2)

if __name__ == "__main__":
    process_datasets()
