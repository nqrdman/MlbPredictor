# MLB Prediction Run

- Generated at: 2026-03-31T16:14:06.275290+00:00
- Training file: .\outputs_full_20260331_v2\mlb_game_features.csv
- Prediction file: .\outputs_today_20260331_v2\mlb_game_features.csv
- Validation fraction: 0.2
- Prediction start date: 2026-03-31
- Learning rate: 0.05
- Epochs: 2000
- L2 penalty: 0.001
- Calibration epochs: 1000
- Probability cap range: 0.05 to 0.95

## Validation Metrics

- Accuracy: 0.7739
- Log loss: 0.4556
- Brier score: 0.1491
- Calibrated log loss: 0.4553
- Calibrated Brier score: 0.1481
- Training games: 1961
- Validation games: 491

## Strongest Weighted Features

- away_pitcher_last_appearance_earned_runs: 1.4516
- home_pitcher_last_appearance_earned_runs: -1.4085
- home_pitcher_last_appearance_innings_pitched: 0.6228
- away_pitcher_last_appearance_innings_pitched: -0.3901
- home_pitcher_season_whip: 0.2150
- away_boxscore_pitching_walks_allowed_avg: -0.2113
- away_pitcher_season_appearances: 0.2095
- away_pitcher_recent_hits_allowed: -0.1829
- home_pitcher_recent_strikeouts: -0.1633
- home_pitcher_recent_era: -0.1506
- away_pitcher_season_innings_pitched: -0.1494
- away_team_last_game_won: 0.1466
- home_bullpen_avg_relievers_per_game: 0.1412
- away_pitcher_season_era: 0.1374
- home_standings_division_rank: 0.1338

## Upcoming Predictions

- 2026-03-31T22:35:00+00:00 | Texas Rangers at Baltimore Orioles | home_win_prob=0.5392 | pick=Baltimore Orioles
- 2026-03-31T22:40:00+00:00 | Pittsburgh Pirates at Cincinnati Reds | home_win_prob=0.4774 | pick=Pittsburgh Pirates
- 2026-03-31T22:40:00+00:00 | Washington Nationals at Philadelphia Phillies | home_win_prob=0.2174 | pick=Washington Nationals
- 2026-03-31T22:40:00+00:00 | Chicago White Sox at Miami Marlins | home_win_prob=0.5402 | pick=Miami Marlins
- 2026-03-31T23:07:00+00:00 | Colorado Rockies at Toronto Blue Jays | home_win_prob=0.5587 | pick=Toronto Blue Jays
- 2026-03-31T23:15:00+00:00 | Athletics at Atlanta Braves | home_win_prob=0.5615 | pick=Atlanta Braves
- 2026-03-31T23:40:00+00:00 | Los Angeles Angels at Chicago Cubs | home_win_prob=0.0544 | pick=Los Angeles Angels
- 2026-03-31T23:40:00+00:00 | Tampa Bay Rays at Milwaukee Brewers | home_win_prob=0.5756 | pick=Milwaukee Brewers
- 2026-03-31T23:45:00+00:00 | New York Mets at St. Louis Cardinals | home_win_prob=0.5517 | pick=St. Louis Cardinals
- 2026-04-01T00:10:00+00:00 | Boston Red Sox at Houston Astros | home_win_prob=0.9468 | pick=Houston Astros
- 2026-04-01T01:40:00+00:00 | Detroit Tigers at Arizona Diamondbacks | home_win_prob=0.5034 | pick=Arizona Diamondbacks
- 2026-04-01T01:40:00+00:00 | San Francisco Giants at San Diego Padres | home_win_prob=0.7577 | pick=San Diego Padres
- 2026-04-01T01:40:00+00:00 | New York Yankees at Seattle Mariners | home_win_prob=0.0838 | pick=New York Yankees
- 2026-04-01T02:10:00+00:00 | Cleveland Guardians at Los Angeles Dodgers | home_win_prob=0.3618 | pick=Cleveland Guardians
