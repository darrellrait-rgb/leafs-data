from datetime import datetime
import time
import requests

# --- SETTINGS (Replaces the YAML file) ---
REFRESH_INTERVAL_SEC = 300
LATITUDE = 43.65
LONGITUDE = -79.38
# ----------------------------------------


def get_live_weather():
  try:
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}&current=temperature_2m,weather_code"
    res = requests.get(url, timeout=5).json()
    temp = round(res["current"]["temperature_2m"])
    current_time = datetime.now().strftime("%I:%M %p")
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
          date_str = event.get("date")
          if date_str:
            # Handle potential timezone 'Z' format cleanly
            clean_date = date_str.replace("Z", "")
            dt = datetime.fromisoformat(clean_date)
            formatted_time = dt.strftime("%a %b %d at %I:%M %p")
            return f"{short_name} | {formatted_time}"
        return f"{short_name} | {status}"
  except Exception:
    pass
  return f"{team_keyword.upper()}: SCHEDULE UPDATING..."


def main():
  print("Starting LED Ticker with live data streams...")

  while True:
    weather_stream = get_live_weather()
    leafs_stream = get_espn_game("hockey", "nhl", "Maple Leafs")
    jays_stream = get_espn_game("baseball", "mlb", "Blue Jays")
    bills_stream = get_espn_game("football", "nfl", "Bills")
    raptors_stream = get_espn_game("basketball", "nba", "Raptors")

    print("\n--- TICKER UPDATE ---")
    print(weather_stream)
    print(leafs_stream)
    print(jays_stream)
    print(bills_stream)
    print(raptors_stream)

    time.sleep(REFRESH_INTERVAL_SEC)


if __name__ == "__main__":
  main()
