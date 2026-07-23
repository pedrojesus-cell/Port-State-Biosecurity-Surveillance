name: GFW Biosecurity Data Sync

on:
  schedule:
    # Runs daily at 02:00 UTC
    - cron: "0 2 * * *"
  workflow_dispatch: # Allows manual trigger from GitHub Actions UI

jobs:
  build-and-sync:
    runs-on: ubuntu-latest

    # Explicitly grant write access to commit generated dataset artifacts back to the repository
    permissions:
      contents: write

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests pandas

      - name: Fetch and Process Port Entries
        env:
          GFW_API_TOKEN: ${{ secrets.GFW_API_TOKEN }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: |
          python scripts/process_port_risks.py

      - name: Commit and Push Updated Baseline Data
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          
          # Ensure target directory exists before staging
          mkdir -p data
          git add -A data/
          
          # Commit and push only if changes exist
          if ! git diff --staged --quiet; then
            git commit -m "auto: update biosecurity baseline data [skip ci]"
            git push
          else
            echo "No data changes detected. Skipping commit."
          fi
