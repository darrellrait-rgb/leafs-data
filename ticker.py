import datetime
import json
import os
import time
import urllib.request

CONFIG_FILE = "config.yml"


def load_simple_yaml():
  """Parses a basic flat config.yml without needing the PyYAML library."""
  config = {
      "esp32_url": "http://ticker.local/set_ticker",
      "lat": 43.6532,
      "lon": -79.3832,
      "nhl_team": "TOR",
      "nfl_keyword": "Bills",
  }
  if not os.path.exists(CONFIG_FILE):
    return config

  try:
    with open(CONFIG_FILE, "r") as f:
      for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
          continue
        if "url:" in line:
          config["esp32_url"] = line.split(":", 1)[1].strip().strip('"\'')
        elif "latitude:" in line:
          config["lat"] = float(line.split(":", 1)[1].strip())
        elif "longitude:" in line:
          config["lon"] = float(line.split(":", 1)[1].strip())
        elif "nhl:" in line:
          config["nhl_team"] = line.split(":", 1)[1].strip().strip('"\'')
        elif "nfl:" in line:
          config["nfl_keyword"] = line.split(":", 1)[1].strip().strip('"\'')
  except Exception as e:
    print(f"Error reading config.yml, using defaults: {e}")

  return config


config = load_simple_yaml()
ESP32_URL = config["esp32_url"]


def fetch_json(url):
  try:
    req = urllib.request.Request(
        url, headers={"User-Agent": "ESP32-Ticker-Script/1.0"}
    )
    with urllib.request.urlopen(req, timeout=5) as response:
      return json.loads(response.read().decode())
  except Exception as e:
    print(f"API fetch error for {url}: {e}")
    return None


def fetch_weather():
  lat = config["lat"]
  lon = config["lon"]
  url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
  res = fetch_json(url)

  if res and "current_weather" in res:
    current = res["current_weather"]
    temp = round(current.get("temperature", 0))
    code = current.get("weathercode", 0)

    condition = "Clear"
    if 1 <= code <= 3:
      condition = "Partly Cloudy"
    elif 45 <= code <= 48:
      condition = "Foggy"
    elif 51 <= code <= 65:
      condition = "Raining"
    elif 71 <= code <= 77:
      condition = "Snowing"
    elif 80 <= code <= 82:
      condition = "Showers"

    now = datetime.datetime.now()
    time_str = now.strftime("%I:%M %p").lstrip("0")
    return f"[ {time_str} | {temp}°C {condition} ]  |  "

  return "[ TORONTO ]  |  "


def fetch_nhl():
  team_abbr = config["nhl_team"]
  res = fetch_json("https://api-web.nhle.com/v1/score/now")
  if res and "games" in res:
    for game in res["games"]:
      home = game["homeTeam"]["abbrev"]
      away = game["awayTeam"]["abbrev"]
      if home == team_abbr or away == team_abbr:
        state = game["gameState"]
        h_score = game["homeTeam"]["score"]
        a_score = game["awayTeam"]["score"]
        if state in ["LIVE", "CRIT"]:
          period = game.get("periodDescriptor", {}).get("number", 1)
          return (
              f"LEAFS LIVE: {away} {a_score} @ {home} {h_score} (P{period})"
              "  |  "
          )
        elif state in ["OFF", "FINAL"]:
          return (
              f"LEAFS LAST: {away} {a_score} @ {home} {h_score} (FINAL)  |  "
          )
  return "LEAFS NEXT: SCHEDULE UPDATING...  |  "


def fetch_bills():
  keyword = config["nfl_keyword"]
  res = fetch_json(
      "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
  )
  if res and "events" in res:
    for event in res["events"]:
      if keyword in event.get("name", ""):
        comp = event["competitions"][0]
        state = comp["status"]["type"]["state"]
        competitors = comp["competitors"]

        away_team, home_team = "", ""
        away_score, home_score = 0, 0
        for c in competitors:
          if c["homeAway"] == "home":
            home_team = c["team"]["abbrev"]
            home_score = int(c["score"])
          else:
            away_team = c["team"]["abbrev"]
            away_score = int(c["score"])

        if state == "in":
          detail = comp["status"]["type"]["detail"]
          return (
              f"BILLS LIVE: {away_team} {away_score} @ {home_team}"
              f" {home_score} ({detail})  |  "
          )
        elif state == "post":
          return (
              f"BILLS FINAL: {away_team} {away_score} @ {home_team}"
              f" {home_score} (FINAL)  |  "
          )
        elif state == "pre":
          date_str = comp["date"][5:10]
          return (
              f"BILLS NEXT: {away_team} @ {home_team} ({date_str})  |  "
          )
  return "BILLS NEXT: BYE / OFFWEEK  |  "


def push_to_esp32():
  payload = json.dumps({
      "weather": fetch_weather(),
      "leafs": fetch_nhl(),
      "jays": "JAYS: OFFSEASON / BREAK  |  ",
      "bills": fetch_bills(),
      "raps": "RAPS NEXT: CHI @ TOR WED 10/21 7:30PM  |  ",
  }).encode("utf-8")

  try:
    req = urllib.request.Request(
        ESP32_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as response:
      print(f"Pushed update to ESP32: Status {response.status}")
  except Exception as e:
    print(f"Failed to push update to ESP32: {e}")


if __name__ == "__main__":
  while True:
    print("Fetching and pushing sports/weather update...")
    push_to_esp32()
    time.sleep(45)
