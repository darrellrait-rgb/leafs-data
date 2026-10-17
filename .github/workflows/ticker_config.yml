import datetime
import time
import requests

# Set your ESP32 IP address or mDNS hostname here
ESP32_URL = "http://ticker.local/set_ticker"  # or e.g., "http://192.168.1.150/set_ticker"


def fetch_weather():
  try:
    url = "https://api.open-meteo.com/v1/forecast?latitude=43.6532&longitude=-79.3832&current_weather=true"
    res = requests.get(url, timeout=5).json()
    current = res.get("current_weather", {})
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
  except Exception as e:
    print(f"Weather error: {e}")
    return "[ TORONTO ]  |  "


def fetch_nhl():
  try:
    url = "https://api-web.nhle.com/v1/score/now"
    res = requests.get(url, timeout=5).json()
    for game in res.get("games", []):
      home = game["homeTeam"]["abbrev"]
      away = game["awayTeam"]["abbrev"]
      if home == "TOR" or away == "TOR":
        state = game["gameState"]
        if state in ["LIVE", "CRIT"]:
          h_score = game["homeTeam"]["score"]
          a_score = game["awayTeam"]["score"]
          period = game.get("periodDescriptor", {}).get("number", 1)
          return (
              f"LEAFS LIVE: {away} {a_score} @ {home} {h_score} (P{period})"
              "  |  "
          )
        elif state in ["OFF", "FINAL"]:
          h_score = game["homeTeam"]["score"]
          a_score = game["awayTeam"]["score"]
          return (
              f"LEAFS LAST: {away} {a_score} @ {home} {h_score} (FINAL)  |  "
          )
    return "LEAFS NEXT: SCHEDULE UPDATING...  |  "
  except Exception as e:
    print(f"NHL error: {e}")
    return "LEAFS: REFRESH ERROR  |  "


def fetch_bills():
  try:
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
    res = requests.get(url, timeout=5).json()
    for event in res.get("events", []):
      if "Bills" in event.get("name", ""):
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
          date_str = comp["date"][5:10]  # MM-DD
          return (
              f"BILLS NEXT: {away_team} @ {home_team} ({date_str})  |  "
          )
    return "BILLS NEXT: BYE / OFFWEEK  |  "
  except Exception as e:
    print(f"NFL error: {e}")
    return "BILLS: REFRESH ERROR  |  "


def push_to_esp32():
  weather = fetch_weather()
  leafs = fetch_nhl()
  bills = fetch_bills()
  jays = "JAYS: OFFSEASON / BREAK  |  "
  raps = "RAPS NEXT: CHI @ TOR WED 10/21 7:30PM  |  "

  payload = {
      "weather": weather,
      "leafs": leafs,
      "jays": jays,
      "bills": bills,
      "raps": raps,
  }

  try:
    response = requests.post(ESP32_URL, json=payload, timeout=5)
    print(f"Successfully pushed ticker update to ESP32: {response.status_code}")
  except Exception as e:
    print(f"Failed to push update to ESP32: {e}")


if __name__ == "__main__":
  while True:
    print("Fetching and pushing sports/weather update...")
    push_to_esp32()
    time.sleep(45)  # Run every 45 seconds
