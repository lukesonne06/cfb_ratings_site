import json
import pandas as pd

with open("data/raw/plays_2025_regular_wk05.json") as f:
    plays = pd.DataFrame(json.load(f))

print(plays.columns.tolist())
print(plays.head())
print(plays["ppa"].describe())