# 1. Save Full JSON for Web UI
    json_path = "data/baseline_risk.json"
    pd.DataFrame(processed_records).to_json(json_path, orient="records", indent=2)
    print(f"SUCCESS: Saved {len(processed_records)} total records to '{json_path}'.")

    # 2. Save Filtered CSV Summary for High-Risk Targets (>= 70%)
    csv_path = "data/high_risk_summary.csv"
    high_risk_records = [r for r in processed_records if r.get("biosecurityRiskScore", 0) >= 0.70]

    if high_risk_records:
        high_risk_df = pd.DataFrame(high_risk_records)
        export_cols = [
            "vesselName", "flag", "vesselType", "mmsi", 
            "portName", "portOfDeparture", "portOfDestination", 
            "residenceHours", "biosecurityRiskScore", "eta", "timestamp"
        ]
        available_cols = [c for c in export_cols if c in high_risk_df.columns]
        high_risk_df[available_cols].to_csv(csv_path, index=False)
        print(f"SUCCESS: Saved {len(high_risk_records)} high-risk records to '{csv_path}'.")
    else:
        pd.DataFrame(columns=[
            "vesselName", "flag", "vesselType", "mmsi", 
            "portName", "residenceHours", "biosecurityRiskScore"
        ]).to_csv(csv_path, index=False)
        print("Notice: Saved empty high-risk CSV template.")
