name: Update Ticker Data

on:
  schedule:
    - cron: '*/10 * * * *'  # Runs every 10 minutes
  workflow_dispatch:        # Allows manual trigger from GitHub Actions tab

jobs:
  update-data:
    runs-on: ubuntu-latest
    permissions:
      contents: write       # Grants workflow permission to commit and push changes back to repo
      
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip

      - name: Run scraper script
        run: python update_ticker.py

      - name: Commit and push changes if any
        run: |
          git config --global user.name 'github-actions[bot]'
          git config --global user.email 'github-actions[bot]@users.noreply.github.com'
          git add leafs.json sports_headlines.json
          git diff --quiet && git diff --staged --quiet || (git commit -m "Auto-update ticker data [skip ci]" && git push)
