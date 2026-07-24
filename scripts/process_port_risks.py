import os
import glob
import re
import pandas as pd

CONFIG_DIR = "config"

# EXACT MARITIME EEZ & PORT COORDINATES
EXACT_EEZ_COORDINATES = {
    # South America & Caribbean
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

    # Atlantic Islands & Iberia
    "madeira": [32.6500, -16.9000],
    "azores": [37.7400, -25.6600],
    "canary": [28.1200, -15.4300],
    "portuguese": [38.7100, -9.1300], "portugal": [38.7100, -9.1300],
    "viana": [41.6932, -8.8329],
    "spanish": [36.5300, -6.2900], "spain": [36.5300, -6.2900],

    # Middle East, Red Sea & Persian Gulf
    "bahraini": [26.0667, 50.5500], "bahrain": [26.0667, 50.5500],
    "yemeni": [15.5527, 48.5164], "yemen": [15.5527, 48.5164],
    "omani": [23.6100, 58.5900], "oman": [23.6100, 58.5900],
    "emirates": [25.2700, 55.2900], "uae": [25.2700, 55.2900],
    "qatari": [25.3548, 51.1839], "qatar": [25.3548, 51.1839],
    "eritrean": [15.1700, 39.7800], "eritrea": [15.1700, 39.7800],
    "egyptian": [29.9600, 32.5500], "egypt": [29.9600, 32.5500],

    # Mediterranean & Black Sea
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

    # Northern & Western Europe
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
    "estonian": [59.4400, 24.7500], "latvian": [56.9500, 24.1000],
    "lithuanian": [55.7100, 21.1300], "icelandic": [64.1400, -21.9400],

    # Africa & Asia
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
    return clean.title() if clean else "Monitored Port"

def get_coords(title_str, filename_str):
    lookup = f"{title_str} {filename_str}".lower()
    if "madeira" in lookup: return [32.6500, -16.9000]
    if "azores" in lookup: return [37.7400, -25.6600]
    if "canary" in lookup: return [28.1200, -15.4300]
    for k, v in EXACT_EEZ_COORDINATES.items():
        if k in lookup: return v
    return [38.7100, -9.1300]

def process_all_config_csvs():
    all_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))
    csv_files = [
        f for f in all_files 
        if "anchorage" not in os.path.basename(f).lower() 
        and "anchorages" not in os.path.basename(f).lower()
    ]

    if not csv_files:
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    port_summary = {}

    for f in csv_files:
        display_title = clean_title(f)
        coords = get_coords(display_title, os.path.basename(f))

        if display_title not in port_summary:
            port_summary[display_title] = {
                "portName": display_title,
                "year": 2026,
                "location": coords,
                "totalPortVisits": 0,
                "highRiskCount": 0,
                "moderateRiskCount": 0,
                "lowRiskCount": 0,
                "vessels": []
            }

        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

            for idx, row in df.iterrows():
                vessel_name = str(row.get("name") or row.get("vessel_name") or f"Vessel_{idx}").strip()
                mmsi = str(row.get("mmsi") or row.get("ssvid") or f"273{idx:06d}").strip()
                flag = str(row.get("flag") or row.get("flag_translated") or "UNK").strip()
                vessel_type = str(row.get("gfw_vessel_type") or row.get("vessel_type") or "Merchant/Carrier").strip()

                try:
                    total_visits = float(row.get("total_port_visit_events") or row.get("total_visits") or 1)
                except (ValueError, TypeError):
                    total_visits = 1.0

                residence_hrs = round(min(168.0, max(6.0, total_visits * 0.25)), 1)

                if total_visits >= 15:
                    risk_score, risk_category = 0.92, "High Fouling Risk"
                    port_summary[display_title]["highRiskCount"] += 1
                elif total_visits >= 5:
                    risk_score, risk_category = 0.65, "Moderate Vector"
                    port_summary[display_title]["moderateRiskCount"] += 1
                else:
                    risk_score, risk_category = 0.35, "Low Risk"
                    port_summary[display_title]["lowRiskCount"] += 1

                port_summary[display_title]["totalPortVisits"] += int(total_visits)
                port_summary[display_title]["vessels"].append({
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
            print(f"Error reading {f}: {e}")

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(list(port_summary.values())).to_json("data/baseline_risk.json", orient="records")

if __name__ == "__main__":
    process_all_config_csvs()
