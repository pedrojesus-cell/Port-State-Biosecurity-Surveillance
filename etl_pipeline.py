# etl_pipeline.py
import os
import glob
import pandas as pd
from scripts.process_port_risks import generate_high_risk_summary  # import your logic

def process_all_config_csvs():
    # ... existing ETL logic ...
    
    # Call secondary processing script
    generate_high_risk_summary()

if __name__ == "__main__":
    process_all_config_csvs()
