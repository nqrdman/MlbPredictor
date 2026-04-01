# MLB Prediction Run

- Generated at: 2026-04-01T03:49:45.284696+00:00
- Training file: C:\Users\nordm\Documents\Playground 7\exports_20260401\training\mlb_game_features.csv
- Prediction file: C:\Users\nordm\Documents\Playground 7\exports_20260401\slate\mlb_game_features.csv
- Validation fraction: 0.2
- Prediction start date: 2026-04-01
- Learning rate: 0.05
- Epochs: 2000
- L2 penalty: 0.001
- Calibration epochs: 1000
- Probability cap range: 0.05 to 0.95
- Market blend weight: 0.5
- Market source: CBS Sports moneylines

## Validation Metrics

- Accuracy: 0.7678
- Log loss: 0.4621
- Brier score: 0.1514
- Calibrated log loss: 0.4600
- Calibrated Brier score: 0.1498
- Home runs MAE: 1.6899
- Away runs MAE: 1.7520
- Total runs MAE: 2.5073
- Total runs RMSE: 3.2445
- Run line accuracy: 0.7882
- Run line log loss: 0.4341
- Training games: 1961
- Validation games: 491

## Strongest Weighted Features

- away_pitcher_last_appearance_earned_runs: 1.4483
- home_pitcher_last_appearance_earned_runs: -1.4182
- home_pitcher_last_appearance_innings_pitched: 0.6210
- away_pitcher_last_appearance_innings_pitched: -0.3887
- home_pitcher_season_whip: 0.2133
- away_pitcher_season_appearances: 0.2092
- away_boxscore_pitching_walks_allowed_avg: -0.2062
- home_pitcher_recent_strikeouts: -0.1794
- away_pitcher_recent_hits_allowed: -0.1785
- away_boxscore_batting_left_on_base_avg: 0.1721
- away_team_last_game_won: 0.1570
- home_pitcher_recent_era: -0.1521
- away_boxscore_batting_triples_avg: -0.1502
- away_pitcher_season_innings_pitched: -0.1501
- home_pitcher_recent_walks: -0.1390

## Upcoming Predictions

- 2026-04-01T16:15:00+00:00 | Athletics at Atlanta Braves | home_win_prob=0.5578 | total=5.278 | home_runs=4.0 | away_runs=1.278 | pick=Atlanta Braves
- 2026-04-01T16:35:00+00:00 | Texas Rangers at Baltimore Orioles | home_win_prob=0.7295 | total=6.734 | home_runs=6.734 | away_runs=0.0 | pick=Baltimore Orioles
- 2026-04-01T16:40:00+00:00 | Pittsburgh Pirates at Cincinnati Reds | home_win_prob=0.6818 | total=10.874 | home_runs=9.712 | away_runs=1.162 | pick=Cincinnati Reds
- 2026-04-01T17:05:00+00:00 | Washington Nationals at Philadelphia Phillies | home_win_prob=0.6887 | total=7.781 | home_runs=3.879 | away_runs=3.903 | pick=Philadelphia Phillies
- 2026-04-01T17:07:00+00:00 | Colorado Rockies at Toronto Blue Jays | home_win_prob=0.6891 | total=3.803 | home_runs=1.283 | away_runs=2.52 | pick=Toronto Blue Jays
- 2026-04-01T17:10:00+00:00 | Chicago White Sox at Miami Marlins | home_win_prob=0.7657 | total=8.144 | home_runs=8.144 | away_runs=0.0 | pick=Miami Marlins
- 2026-04-01T17:15:00+00:00 | New York Mets at St. Louis Cardinals | home_win_prob=0.6706 | total=8.698 | home_runs=4.851 | away_runs=3.846 | pick=St. Louis Cardinals
- 2026-04-01T17:40:00+00:00 | Tampa Bay Rays at Milwaukee Brewers | home_win_prob=0.5022 | total=7.769 | home_runs=4.971 | away_runs=2.797 | pick=Milwaukee Brewers
- 2026-04-01T18:10:00+00:00 | Boston Red Sox at Houston Astros | home_win_prob=0.236 | total=7.155 | home_runs=0.581 | away_runs=6.574 | pick=Boston Red Sox
- 2026-04-01T18:20:00+00:00 | Los Angeles Angels at Chicago Cubs | home_win_prob=0.324 | total=11.038 | home_runs=2.143 | away_runs=8.895 | pick=Los Angeles Angels
- 2026-04-01T19:40:00+00:00 | Detroit Tigers at Arizona Diamondbacks | home_win_prob=0.2216 | total=7.424 | home_runs=0.461 | away_runs=6.963 | pick=Detroit Tigers
- 2026-04-01T20:10:00+00:00 | San Francisco Giants at San Diego Padres | home_win_prob=0.4192 | total=19.345 | home_runs=9.261 | away_runs=10.084 | pick=San Francisco Giants
- 2026-04-01T20:10:00+00:00 | New York Yankees at Seattle Mariners | home_win_prob=0.4311 | total=3.305 | home_runs=0.797 | away_runs=2.508 | pick=New York Yankees
- 2026-04-01T23:40:00+00:00 | Minnesota Twins at Kansas City Royals | home_win_prob=0.263 | total=2.943 | home_runs=0.0 | away_runs=2.943 | pick=Minnesota Twins
- 2026-04-02T00:20:00+00:00 | Cleveland Guardians at Los Angeles Dodgers | home_win_prob=0.7108 | total=11.644 | home_runs=7.176 | away_runs=4.468 | pick=Los Angeles Dodgers
