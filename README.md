# 🌊 Port State Biosecurity & Biofouling Surveillance Engine

An automated, open-source biosecurity monitoring platform designed for Port State Control (PSC) authorities to identify marine biological invasion risks (biofouling vectors) using Global Fishing Watch AIS events data.

---

## 🚀 Key Features

* **Targeted AIS Port Entry Sync:** Queries Global Fishing Watch (GFW) API v3 for targeted high-risk carrier and fishing vessels.
* **Fouling Risk Scoring Model:** Automatically flags vessels exceeding in-port residence thresholds (>48 hrs) combined with low transit speeds (<8 knots).
* **Early Warning Alerts:** Dispatches real-time webhooks via Discord when high-risk targets ($\ge 70\%$) enter monitored ports.
* **Dual Output Reporting:** Generates both `data/baseline_risk.json` for interactive web visualization and `data/high_risk_summary.csv` for official compliance auditing.
* **Interactive Web Dashboard:** Lightweight Leaflet JS dashboard featuring real-time vessel search, flag state filtering, and KPI stat tracking.

---

## 🛠️ System Architecture

```text
[ GFW API / Vessel AIS ] ──> [ Python Risk Engine ] ──> [ JSON & CSV Reports ] ──> [ Web Dashboard UI ]
                                        │
                                        └──> [ Discord Alert Webhooks ]
