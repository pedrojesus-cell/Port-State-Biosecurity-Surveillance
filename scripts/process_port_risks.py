import os
import glob
import sys
import hashlib
import re
import pandas as pd

CONFIG_DIR = "config"

# Extensive geographic coordinate lookup dictionary for standard regional EEZs and Ports
PORT_GEO_DATABASE = {
    # Portugal & Islands
    "viana do castelo": [41.6932, -8.8329], "viana": [41.6932, -8.8329],
    "leixoes": [41.1850, -8.7000], "porto": [41.1500, -8.6100],
    "lisbon": [38.7100, -9.1300], "lisboa": [38.7100, -9.1300],
    "sines": [37.9500, -8.8700], "setubal": [38.5200, -8.8900],
    "faro": [37.0100, -7.9300], "portugal": [38.7100, -9.1300],
    "azores": [37.7400, -25.6600], "madeira": [32.6500, -16.9000],

    # Spain & Canaries
    "cadiz": [36.5300, -6.2900], "barcelona": [41.3800, 2.1700],
    "valencia": [39.4600, -0.3700], "bilbao": [43.3600, -3.0400],
    "vigo": [42.2400, -8.7200], "algeciras": [36.1300, -5.4400],
    "malaga": [36.7100, -4.4200], "las palmas": [28.1400, -15.4200],
    "tenerife": [28.4600, -16.2500], "canary": [28.1200, -15.4300],
    "spain": [36.5300, -6.2900], "spanish": [36.5300, -6.2900],

    # Europe, Baltic & Arctic
    "france": [48.3900, -4.4800], "french": [48.3900, -4.4800],
    "united kingdom": [50.8000, -1.0800], "uk": [50.8000, -1.0800], "british": [50.8000, -1.0800],
    "ireland": [51.8900, -8.4700], "irish": [51.8900, -8.4700],
    "germany": [53.5500, 9.9900], "german": [53.5500, 9.9900],
    "netherlands": [51.9800, 3.9000], "dutch": [51.9800, 3.9000], "rotterdam": [51.9800, 3.9000],
    "belgium": [51.3300, 3.2200], "belgian": [51.3300, 3.2200],
    "denmark": [55.6700, 12.5600], "danish": [55.6700, 12.5600],
    "sweden": [57.7000, 11.9600], "swedish": [57.7000, 11.9600],
    "norway": [60.3900, 5.3200], "norwegian": [60.3900, 5.3200],
    "finland": [60.1700, 24.9400], "finnish": [60.1700, 24.9400],
    "iceland": [64.1400, -21.9400], "icelandic": [64.1400, -21.9400],
    "poland": [54.3500, 18.6600], "polish": [54.3500, 18.6600],
    "estonia": [59.4400, 24.7500], "estonian": [59.4400, 24.7500],
    "latvia": [56.9500, 24.1000], "latvian": [56.9500, 24.1000],
    "lithuania": [55.7100, 21.1300], "lithuanian": [55.7100, 21.1300],

    # Mediterranean & Balkans
    "italy": [40.8500, 14.2600], "italian": [40.8500, 14.2600],
    "greece": [37.9400, 23.6400], "greek": [37.9400, 23.6400],
    "croatia": [43.5100, 16.4400], "croatian": [43.5100, 16.4400],
    "cyprus": [34.6700, 33.0400], "cypriot": [34.6700, 33.0400],
    "malta": [35.8900, 14.5100], "maltese": [35.8900, 14.5100],
    "albania": [41.3200, 19.4500], "albanian": [41.3200, 19.4500],
    "slovenia": [45.5400, 13.7200], "slovenian": [45.5400, 13.7200],
    "bulgaria": [43.2100, 27.9100], "bulgarian": [43.2100, 27.9100],
    "romania": [44.1800, 28.6300], "romanian": [44.1800, 28.6300],

    # Middle East & Africa
    "turkey": [41.0100, 28.9700], "turkish": [41.0100, 28.9700],
    "oman": [23.6100, 58.5900], "omani": [23.6100, 58.5900],
    "emirates": [25.2700, 55.2900], "uae": [25.2700, 55.2900],
    "eritrean": [15.1700, 39.7800], "eritrea": [15.1700, 39.7800],
    "egypt": [29.9600, 32.5500], "egyptian": [29.9600, 32.5500],
    "morocco": [35.7800, -5.8000], "moroccan": [35.7800, -5.8000],

    # Americas & Caribbean
    "uruguay": [-34.9000, -56.1600], "uruguayan": [-34.9000, -56.1600],
    "suriname": [5.8500, -55.2000], "surinamese": [5.8500, -55.2000],
    "belize": [17.5000, -88.1800], "belizean": [17.5000, -88.1800],
    "mexico": [19.2000, -96.1300], "mexican": [19.2000, -96.1300],
    "brazil": [-23.9608, -46.3331], "brazilian": [-23.9608, -46.3331],
    "argentina": [-34.6000, -58.3800], "argentinian": [-34.6000, -58.3800],
    "bermuda": [32.3000, -64.7800], "bermudian": [32.3000, -64.7800],
    "chile": [-33.0400, -71.6200], "chilean": [-33.0400, -71.6200],
    "peru": [-12.0400, -77.1400], "peruvian": [-12.0400, -77.1400],
    "panama": [8.9800, -79.5200], "panamanian": [8.9800, -79.5200]
}

def clean_file_title(filename):
    base = os.path.basename(filename).replace(".csv", "").replace("_", " ").replace("-", " ")
    clean = re.sub(r'port\s+visit\s+events?', '', base, flags=re.IGNORECASE)
    clean = re.sub(r'exclusive\s+economic\s+zone', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'eez', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'202\d.*', '', clean).strip()
    return clean.title() if clean else "Monitored Port"

def find_coordinates(row, title_str, file_str, unique_seed):
    # 1. First priority: Direct CSV row latitude and longitude columns
    lat_cols = ['lat', 'latitude', 'anchorage_lat', 'start_lat', 'mean_lat', 'lat_center']
    lon_cols = ['lon', 'lng', 'longitude', 'anchorage_lon', 'start_lon', 'mean_lon', 'lon_center']
    
    found_lat, found_lon = None, None
    for c in lat_cols:
        if c in row and pd.notnull(row[c]):
            try:
                found_lat = float(row[c])
                break
            except (ValueError, TypeError): pass

    for c in lon_cols:
        if c in row and pd.notnull(row[c]):
            try:
                found_lon = float(row[c])
                break
            except (ValueError, TypeError): pass

    if found_lat is not None and found_lon is not None and (-90 <= found_lat <= 90) and (-180 <= found_lon <= 180):
        return [round(found_lat, 4), round(found_lon, 4)]

    # 2. Second priority: Match database by port/file name keywords
    combined = f"{title_str} {file_str}".lower()
    for key, coords in PORT_GEO_DATABASE.items():
        if key in combined:
            hash_val = int(hashlib.md5(unique_seed.encode('utf-8')).hexdigest(), 16)
            j_lat = (((hash_val % 50) - 25) / 100.0) * 0.15
            j_lon = ((((hash_val // 50) % 50) - 25) / 100.0) * 0.15
            return [round(coords[0] + j_lat, 4), round(coords[1] + j_lon, 4)]

    # 3. Fallback: Regionally bucketed deterministic hash position (keeps unmapped files visible)
    hash_val = int(hashlib.md5(unique_seed.encode('utf-8')).hexdigest(), 16)
    proj_lat = round(20.0 + (((hash_val % 1000) / 1000.0) * 35.0), 4)
    proj_lon = round(-10.0 + ((((hash_val // 1000) % 1000) / 1000.0) * 40.0), 4)
    return [proj_lat, proj_lon]

def process_all_config_csvs():
    csv_files = glob.glob(os.path.join(CONFIG_DIR, "*.csv"))

    if not csv_files:
        print(f"NOTICE: No CSV files found inside '{CONFIG_DIR}/'.")
        os.makedirs("data", exist_ok=True)
        pd.DataFrame([]).to_json("data/baseline_risk.json", orient="records")
        return

    print(f"Processing all {len(csv_files)} CSV datasets with dual-coordinate resolution...")

    port_summary = {}

    for file_idx, f in enumerate(csv_files):
        file_base = os.path.basename(f)
        display_title = clean_file_title(file_base)

        try:
            df = pd.read_csv(f, low_memory=False)
            df.columns = [c.lower().strip().replace(" ", "_").replace("-", "_") for c in df.columns]

            # Detect port name column
            port_col = None
            for candidate in ['port_name', 'anchorage_name', 'label', 'event_start_port', 'event_end_port']:
                if candidate in df.columns:
                    port_col = candidate
                    break

            for idx, row in df.iterrows():
                raw_port = str(row.get(port_col) if port_col else "").strip()
                
                if raw_port and raw_port.lower() not in ['nan', 'none', 'null', '']:
                    sub_title = raw_port.replace("_", " ").replace("-", " ").title()
                    full_display_name = f"{display_title} ({sub_title})"
                else:
                    full_display_name = display_title

                # GUARANTEED UNIQUE KEY per file and sub-port
                unique_key = f"{file_base}::{full_display_name}"

                if unique_key not in port_summary:
                    coords = find_coordinates(row, full_display_name, file_base, unique_key)
                    port_summary[unique_key] = {
                        "portName": full_display_name,
                        "year": 2025,
                        "location": coords,
                        "totalPortVisits": 0,
                        "highRiskCount": 0,
                        "moderateRiskCount": 0,
                        "lowRiskCount": 0,
                        "vessels": []
                    }

                # Extract vessel info
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
                    risk_score = 0.92
                    risk_category = "High Fouling Risk"
                    port_summary[unique_key]["highRiskCount"] += 1
                elif total_visits >= 5:
                    risk_score = 0.65
                    risk_category = "Moderate Vector"
                    port_summary[unique_key]["moderateRiskCount"] += 1
                else:
                    risk_score = 0.35
                    risk_category = "Low Risk"
                    port_summary[unique_key]["lowRiskCount"] += 1

                port_summary[unique_key]["totalPortVisits"] += int(total_visits)

                port_summary[unique_key]["vessels"].append({
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
    print(f"SUCCESS: Exported {len(final_ports)} distinct port entries from {len(csv_files)} CSV files.")

if __name__ == "__main__":
    process_all_config_csvs()
