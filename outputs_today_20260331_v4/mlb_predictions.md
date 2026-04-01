# MLB Prediction Run

- Generated at: 2026-03-31T17:46:08.619872+00:00
- Training file: .\outputs_full_20260331_v3\mlb_game_features.csv
- Prediction file: .\outputs_today_20260331_v4\mlb_game_features.csv
- Validation fraction: 0.2
- Prediction start date: 2026-03-31
- Learning rate: 0.05
- Epochs: 2000
- L2 penalty: 0.001
- Calibration epochs: 1000
- Probability cap range: 0.05 to 0.95
- Market blend weight: 0.35
- Market source: CBS Sports moneylines

## Validation Metrics

- Accuracy: 0.7719
- Log loss: 0.4610
- Brier score: 0.1510
- Calibrated log loss: 0.4592
- Calibrated Brier score: 0.1495
- Training games: 1961
- Validation games: 491

## Strongest Weighted Features

- away_pitcher_last_appearance_earned_runs: 1.4454
- home_pitcher_last_appearance_earned_runs: -1.4153
- home_pitcher_last_appearance_innings_pitched: 0.6186
- away_pitcher_last_appearance_innings_pitched: -0.3879
- home_pitcher_season_whip: 0.2146
- away_boxscore_pitching_walks_allowed_avg: -0.2082
- away_pitcher_season_appearances: 0.2077
- away_pitcher_recent_hits_allowed: -0.1797
- away_boxscore_batting_left_on_base_avg: 0.1723
- home_pitcher_recent_strikeouts: -0.1710
- away_team_last_game_won: 0.1572
- home_pitcher_recent_era: -0.1555
- away_boxscore_batting_triples_avg: -0.1500
- away_pitcher_season_innings_pitched: -0.1482
- home_pitcher_recent_walks: -0.1334

## Upcoming Predictions

- 2026-03-31T22:35:00+00:00 | Texas Rangers at Baltimore Orioles | home_win_prob=0.4521 | pick=Texas Rangers
- 2026-03-31T22:40:00+00:00 | Pittsburgh Pirates at Cincinnati Reds | home_win_prob=0.4013 | pick=Pittsburgh Pirates
- 2026-03-31T22:40:00+00:00 | Washington Nationals at Philadelphia Phillies | home_win_prob=0.1382 | pick=Washington Nationals
- 2026-03-31T22:40:00+00:00 | Chicago White Sox at Miami Marlins | home_win_prob=0.6362 | pick=Miami Marlins
- 2026-03-31T23:07:00+00:00 | Colorado Rockies at Toronto Blue Jays | home_win_prob=0.5994 | pick=Toronto Blue Jays
- 2026-03-31T23:15:00+00:00 | Athletics at Atlanta Braves | home_win_prob=0.2302 | pick=Athletics
- 2026-03-31T23:40:00+00:00 | Los Angeles Angels at Chicago Cubs | home_win_prob=0.2284 | pick=Los Angeles Angels
- 2026-03-31T23:40:00+00:00 | Tampa Bay Rays at Milwaukee Brewers | home_win_prob=0.4124 | pick=Tampa Bay Rays
- 2026-03-31T23:45:00+00:00 | New York Mets at St. Louis Cardinals | home_win_prob=0.5879 | pick=St. Louis Cardinals
- 2026-04-01T00:10:00+00:00 | Boston Red Sox at Houston Astros | home_win_prob=0.9456 | pick=Houston Astros
- 2026-04-01T01:40:00+00:00 | Detroit Tigers at Arizona Diamondbacks | home_win_prob=0.2655 | pick=Detroit Tigers
- 2026-04-01T01:40:00+00:00 | San Francisco Giants at San Diego Padres | home_win_prob=0.7556 | pick=San Diego Padres
- 2026-04-01T01:40:00+00:00 | New York Yankees at Seattle Mariners | home_win_prob=0.2221 | pick=New York Yankees
- 2026-04-01T02:10:00+00:00 | Cleveland Guardians at Los Angeles Dodgers | home_win_prob=0.4363 | pick=Cleveland Guardians
