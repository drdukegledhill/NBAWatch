import requests

RAPIDAPI_KEY = "YOUR_RAPIDAPI_KEY"  # Replace with your RapidAPI key
url = "https://api-nba-v1.p.rapidapi.com/teams"

headers = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "api-nba-v1.p.rapidapi.com"
}

response = requests.get(url, headers=headers)
if response.status_code == 200:
    data = response.json()
    for team in data.get("response", []):
        print(f"{team['name']} (ID: {team['id']})")
else:
    print("Error:", response.status_code, response.text) 