# NBA Prediction Run

- Generated at: 2026-03-30T07:24:39.410065+00:00
- Training file: .\outputs_nba_train_fullhistory\nba_game_features.csv
- Prediction file: .\outputs_nba_today_uslate\nba_game_features.csv
- Validation fraction: 0.2
- Prediction start date: 2026-03-30
- Learning rate: 0.03
- Epochs: 3000
- L2 penalty: 0.002

## Validation Metrics

- Accuracy: 0.7197
- Log loss: 0.5650
- Brier score: 0.1905
- Training games: 956
- Validation games: 239

## Strongest Weighted Features

- diff_record_wins: 0.9088
- diff_record_losses: -0.7667
- away_record_wins: -0.4930
- diff_team_losses: 0.4792
- diff_standings_losses: 0.4743
- home_record_losses: -0.3196
- away_standings_conference_rank: -0.2975
- diff_standings_conference_rank: 0.2883
- away_team_away_win_pct: 0.2797
- home_standings_division_rank: 0.2769
- diff_team_wins: -0.2761
- diff_standings_wins: -0.2702
- away_standings_losses: -0.2700
- home_standings_losses: 0.2654
- diff_boxscore_turnoverPoints_avg: -0.2650
- away_team_losses: -0.2645
- home_boxscore_recent_turnoverPoints_avg: 0.2639
- home_team_losses: 0.2627
- home_team_previous_season_win_pct: 0.2591
- away_boxscore_effective_field_goal_pct_avg: -0.2554

## Upcoming Predictions

- 2026-03-30T23:00:00+00:00 | Philadelphia 76ers at Miami Heat | home_win_prob=0.6001 | pick=Miami Heat
- 2026-03-30T23:30:00+00:00 | Boston Celtics at Atlanta Hawks | home_win_prob=0.3808 | pick=Boston Celtics
- 2026-03-31T00:00:00+00:00 | Phoenix Suns at Memphis Grizzlies | home_win_prob=0.1284 | pick=Phoenix Suns
- 2026-03-31T00:00:00+00:00 | Chicago Bulls at San Antonio Spurs | home_win_prob=0.9985 | pick=San Antonio Spurs
- 2026-03-31T00:30:00+00:00 | Minnesota Timberwolves at Dallas Mavericks | home_win_prob=0.1276 | pick=Minnesota Timberwolves
- 2026-03-31T01:00:00+00:00 | Cleveland Cavaliers at Utah Jazz | home_win_prob=0.1119 | pick=Cleveland Cavaliers
- 2026-03-31T01:30:00+00:00 | Detroit Pistons at Oklahoma City Thunder | home_win_prob=0.736 | pick=Oklahoma City Thunder
- 2026-03-31T02:00:00+00:00 | Washington Wizards at Los Angeles Lakers | home_win_prob=0.9936 | pick=Los Angeles Lakers
- 2026-03-31T23:00:00+00:00 | Phoenix Suns at Orlando Magic | home_win_prob=0.3365 | pick=Phoenix Suns
- 2026-03-31T23:30:00+00:00 | Charlotte Hornets at Brooklyn Nets | home_win_prob=0.061 | pick=Charlotte Hornets
