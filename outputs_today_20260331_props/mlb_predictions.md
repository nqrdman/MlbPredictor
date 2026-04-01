# MLB Prediction Run

- Generated at: 2026-03-31T18:04:32.527916+00:00
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
- Home runs MAE: 1.6874
- Away runs MAE: 1.7511
- Total runs MAE: 2.5209
- Total runs RMSE: 3.2586
- Run line accuracy: 0.7943
- Run line log loss: 0.4333
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

- 2026-03-31T22:35:00+00:00 | Texas Rangers at Baltimore Orioles | home_win_prob=0.4525 | total=9.266 | home_runs=5.219 | away_runs=4.047 | pick=Texas Rangers
- 2026-03-31T22:40:00+00:00 | Pittsburgh Pirates at Cincinnati Reds | home_win_prob=0.4013 | total=7.538 | home_runs=3.565 | away_runs=3.973 | pick=Pittsburgh Pirates
- 2026-03-31T22:40:00+00:00 | Washington Nationals at Philadelphia Phillies | home_win_prob=0.1382 | total=9.892 | home_runs=3.164 | away_runs=6.729 | pick=Washington Nationals
- 2026-03-31T22:40:00+00:00 | Chicago White Sox at Miami Marlins | home_win_prob=0.6362 | total=10.075 | home_runs=6.969 | away_runs=3.107 | pick=Miami Marlins
- 2026-03-31T23:07:00+00:00 | Colorado Rockies at Toronto Blue Jays | home_win_prob=0.5994 | total=6.164 | home_runs=1.378 | away_runs=4.786 | pick=Toronto Blue Jays
- 2026-03-31T23:15:00+00:00 | Athletics at Atlanta Braves | home_win_prob=0.2302 | total=10.385 | home_runs=6.071 | away_runs=4.313 | pick=Athletics
- 2026-03-31T23:40:00+00:00 | Los Angeles Angels at Chicago Cubs | home_win_prob=0.2284 | total=4.11 | home_runs=0.0 | away_runs=4.11 | pick=Los Angeles Angels
- 2026-03-31T23:40:00+00:00 | Tampa Bay Rays at Milwaukee Brewers | home_win_prob=0.4124 | total=12.147 | home_runs=7.425 | away_runs=4.722 | pick=Tampa Bay Rays
- 2026-03-31T23:45:00+00:00 | New York Mets at St. Louis Cardinals | home_win_prob=0.5879 | total=10.172 | home_runs=4.747 | away_runs=5.426 | pick=St. Louis Cardinals
- 2026-04-01T00:10:00+00:00 | Boston Red Sox at Houston Astros | home_win_prob=0.7692 | total=12.548 | home_runs=8.612 | away_runs=3.936 | pick=Houston Astros
- 2026-04-01T01:40:00+00:00 | Detroit Tigers at Arizona Diamondbacks | home_win_prob=0.2655 | total=9.458 | home_runs=4.618 | away_runs=4.841 | pick=Detroit Tigers
- 2026-04-01T01:40:00+00:00 | San Francisco Giants at San Diego Padres | home_win_prob=0.7556 | total=5.128 | home_runs=3.784 | away_runs=1.344 | pick=San Diego Padres
- 2026-04-01T01:40:00+00:00 | New York Yankees at Seattle Mariners | home_win_prob=0.2221 | total=4.971 | home_runs=0.246 | away_runs=4.726 | pick=New York Yankees
- 2026-04-01T02:10:00+00:00 | Cleveland Guardians at Los Angeles Dodgers | home_win_prob=0.5251 | total=5.222 | home_runs=2.645 | away_runs=2.577 | pick=Los Angeles Dodgers
