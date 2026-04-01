# MLB Prediction Run

- Generated at: 2026-03-31T15:12:47.068977+00:00
- Training file: .\outputs_full_20260331\mlb_game_features.csv
- Prediction file: .\outputs_today_20260331\mlb_game_features.csv
- Validation fraction: 0.2
- Prediction start date: 2026-03-31
- Learning rate: 0.05
- Epochs: 2000
- L2 penalty: 0.001

## Validation Metrics

- Accuracy: 0.7739
- Log loss: 0.4563
- Brier score: 0.1498
- Training games: 1961
- Validation games: 491

## Strongest Weighted Features

- away_pitcher_last_appearance_earned_runs: 1.4517
- home_pitcher_last_appearance_earned_runs: -1.4211
- home_pitcher_last_appearance_innings_pitched: 0.6190
- away_pitcher_last_appearance_innings_pitched: -0.3950
- away_pitcher_season_appearances: 0.2189
- home_pitcher_season_whip: 0.2124
- away_pitcher_recent_hits_allowed: -0.1671
- home_pitcher_recent_strikeouts: -0.1602
- home_pitcher_recent_era: -0.1454
- away_pitcher_season_innings_pitched: -0.1380
- home_boxscore_batting_doubles_avg: 0.1380
- away_pitcher_season_era: 0.1350
- home_pitcher_recent_walks: -0.1329
- home_team_recent5_runs_allowed_avg: 0.1263
- away_team_last_game_was_home: -0.1230

## Upcoming Predictions

- 2026-03-31T22:35:00+00:00 | Texas Rangers at Baltimore Orioles | home_win_prob=0.5898 | pick=Baltimore Orioles
- 2026-03-31T22:40:00+00:00 | Pittsburgh Pirates at Cincinnati Reds | home_win_prob=0.6149 | pick=Cincinnati Reds
- 2026-03-31T22:40:00+00:00 | Washington Nationals at Philadelphia Phillies | home_win_prob=0.1703 | pick=Washington Nationals
- 2026-03-31T22:40:00+00:00 | Chicago White Sox at Miami Marlins | home_win_prob=0.6688 | pick=Miami Marlins
- 2026-03-31T23:07:00+00:00 | Colorado Rockies at Toronto Blue Jays | home_win_prob=0.7475 | pick=Toronto Blue Jays
- 2026-03-31T23:15:00+00:00 | Athletics at Atlanta Braves | home_win_prob=0.525 | pick=Atlanta Braves
- 2026-03-31T23:40:00+00:00 | Los Angeles Angels at Chicago Cubs | home_win_prob=0.0248 | pick=Los Angeles Angels
- 2026-03-31T23:40:00+00:00 | Tampa Bay Rays at Milwaukee Brewers | home_win_prob=0.6403 | pick=Milwaukee Brewers
- 2026-03-31T23:45:00+00:00 | New York Mets at St. Louis Cardinals | home_win_prob=0.6923 | pick=St. Louis Cardinals
- 2026-04-01T00:10:00+00:00 | Boston Red Sox at Houston Astros | home_win_prob=0.9815 | pick=Houston Astros
- 2026-04-01T01:40:00+00:00 | Detroit Tigers at Arizona Diamondbacks | home_win_prob=0.2434 | pick=Detroit Tigers
- 2026-04-01T01:40:00+00:00 | San Francisco Giants at San Diego Padres | home_win_prob=0.872 | pick=San Diego Padres
- 2026-04-01T01:40:00+00:00 | New York Yankees at Seattle Mariners | home_win_prob=0.0625 | pick=New York Yankees
- 2026-04-01T02:10:00+00:00 | Cleveland Guardians at Los Angeles Dodgers | home_win_prob=0.3363 | pick=Cleveland Guardians
