import requests
from datetime import datetime

# Use a known date with games (e.g., NBA Finals 2024)
date = "20240606"
url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date}"

response = requests.get(url)
print("Status code:", response.status_code)
print("Raw response:", response.text)

data = response.json()
print("Events:", data.get('events', []))

# Print basic info about today's games
for event in data.get('events', []):
    matchup = event['name']
    status = event['status']['type']['description']
    print(f"{matchup} - {status}") 