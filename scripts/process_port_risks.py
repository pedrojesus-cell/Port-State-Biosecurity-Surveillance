def fetch_port_biosecurity_events():
    processed_records = []

    if API_TOKEN:
        try:
            print(f"Connecting to Global Fishing Watch API for {len(TARGET_VESSEL_MMSIS)} target vessels...")
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=60)  # Querying 60 days to catch long transit port visits

            url = "https://gateway.api.globalfishingwatch.org/v3/events"
            headers = {
                "Authorization": f"Bearer {API_TOKEN}",
                "User-Agent": "MarineBiosecurityMonitor/1.0"
            }

            for mmsi in TARGET_VESSEL_MMSIS:
                params = {
                    "datasets": "public-global-port-visits-c2-events:latest",
                    "vessels[0]": mmsi,
                    "start-date": start_date.strftime("%Y-%m-%d"),
                    "end-date": end_date.strftime("%Y-%m-%d"),
                    "limit": 50,
                    "offset": 0
                }

                response = requests.get(url, headers=headers, params=params, timeout=15)
                
                if response.status_code == 200:
                    data = response.json()
                    events = data.get("entries", [])
                    print(f"MMSI {mmsi}: Retrieved {len(events)} events.")

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
                            "vesselName": vessel_info.get("name", f"Vessel {mmsi}"),
                            "mmsi": vessel_info.get("ssvid", mmsi),
                            "flag": vessel_info.get("flag", "UNK"),
                            "vesselType": vessel_info.get("type", "Fish Carrier"),
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
                    print(f"MMSI {mmsi} API Query Status: {response.status_code}")

            # Fallback ONLY if the API returns 0 records total across all vessels
            if not processed_records:
                print("Notice: No live events found in the selected range. Loading baseline fallback dataset.")
                processed_records = get_fallback_data()

        except Exception as e:
            print(f"API Exception: {e}. Loading baseline fallback dataset.")
            processed_records = get_fallback_data()
    else:
        print("GFW Token missing. Loading baseline fallback dataset.")
        processed_records = get_fallback_data()

    # Save Output Artifacts
    os.makedirs("data", exist_ok=True)
    pd.DataFrame(processed_records).to_json("data/baseline_risk.json", orient="records", indent=2)
    
    high_risk_records = [r for r in processed_records if r.get("biosecurityRiskScore", 0) >= 0.70]
    pd.DataFrame(high_risk_records).to_csv("data/high_risk_summary.csv", index=False)
