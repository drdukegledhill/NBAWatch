from nba_api.stats.endpoints import leaguedashplayerstats
import pandas as pd

# Fetch player stats for the 2023-24 season
player_stats = leaguedashplayerstats.LeagueDashPlayerStats(season='2023-24')

# Get the data as a pandas DataFrame
df = player_stats.get_data_frames()[0]

# Display the first 5 rows
print(df.head())
