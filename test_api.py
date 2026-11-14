import os
import requests

API_KEY = os.environ.get("CFBD_API_KEY")  # keep the key out of your code
BASE_URL = "https://api.collegefootballdata.com"

headers = {"Authorization": f"Bearer {API_KEY}"}

response = requests.get(f"{BASE_URL}/teams/fbs", headers=headers, params={"year": 2026})
response.raise_for_status()

teams = response.json()
print(f"Found {len(teams)} FBS teams\n")

for team in sorted(teams, key=lambda t: t["school"]):
    print(f"{team['school']} ({team.get('conference')})")