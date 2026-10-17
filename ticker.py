from datetime import datetime
import time
import requests
import yaml

# Load the dedicated ticker config file
CONFIG_FILE = "ticker_config.yml"


def load_config():
  try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
      return yaml.safe_load(f) or {}
  except FileNotFoundError:
    print(f"Warning: {CONFIG_FILE} not found. Using default settings.")
    return {}


def get_live_weather():
  try:
    # Open-Meteo free API for Toronto coordinates (43.65, -79.38)
    url = "https://api.open-meteo.com/v1/forecast?latitude=43.65&longitude=-79.38&current=temperature_2m,weather_code"
    res = requests.get(url, timeout=5).json()
    temp = round(res["current"]["temperature_2m"])
    current_time = datetime.now().strftime("%I:%M %p")
    # Clean format without brackets and using standard Unicode degree symbol
    return f"{current_time} | {temp}\u00B0C Partly Cloudy"
  except Exception:
    current_time = datetime.now().strftime("%I:%M %p")
    return f"{current_time} | --\u00B0C Weather Updating..."


def get_espn_game(sport_path, league_path, team_keyword):
  try:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/{league_path}/scoreboard"
    data = requests.get(url, timeout=5).json()

    for event in data.get("events", []):
      name = event.get("name", "")
      if team_keyword.lower() in name.lower():
        status = event["status"]["type"]["description"]
        short_name = event.get("shortName", name)
        if "Final" in status:
          return f"{short_name} | FINAL"
        elif "InProgress" in status or "Live" in status:
          return f"{short_name} | LIVE"
        else:
          # Upcoming game date/time formatting
          date_str = event.get("date")
          if date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%MZ")
            formatted_time = dt.strftime("%a %b %d at %I:%M %p")
            return f"{short_name} | {formatted_time}"
        return f"{short_name} | {status}"
  except Exception:
    pass
  return f"{team_keyword.upper()}: SCHEDULE UPDATING..."


def main():
  config = load_config()
  print("Starting LED Ticker with live data streams...")

  while True:
    weather_stream = get_live_weather()
    leafs_stream = get_espn_game("hockey", "nhl", "Maple Leafs")
    jays_stream = get_espn_game("baseball", "mlb", "Blue Jays")
    bills_stream = get_espn_game("football", "nfl", "Bills")
    raptors_stream = get_espn_game("basketball", "nba", "Raptors")

    # Print or send to LED matrix framework
    print("--- TICKER UPDATE ---")
    print(weather_stream)
    print(leafs_stream)
    print(jays_stream)
    print(bills_stream)
    print(raptors_stream)

    # Refresh interval from config or default to 300 seconds (5 mins)
    interval = config.get("ticker", {}).get("refresh_interval_sec", 300)
    time.sleep(interval)


if __name__ == "__main__":
  main()
