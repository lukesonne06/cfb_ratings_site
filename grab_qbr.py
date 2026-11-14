import requests

url = ("https://sports.core.api.espn.com/v2/sports/football/"
       "leagues/college-football/seasons/2025/types/2/groups/80/qbr/0")
r = requests.get(url, timeout=30)
print(r.status_code)
data = r.json()
print(list(data.keys()))
print(str(data)[:1500])