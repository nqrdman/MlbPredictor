# NBA Prediction Run

- Generated at: 2026-03-30T06:44:48.767510+00:00
- Training file: .\outputs_nba_test\nba_game_features.csv
- Prediction file: .\outputs_nba_test\nba_game_features.csv
- Validation fraction: 0.2
- Prediction start date: 2026-03-30
- Learning rate: 0.03
- Epochs: 3000
- L2 penalty: 0.002

## Validation Metrics

- Accuracy: 0.2727
- Log loss: 8.5811
- Brier score: 0.6669
- Training games: 40
- Validation games: 11

## Strongest Weighted Features

- diff_team_streak: -0.5593
- home_player_top_player_assists_avg: 0.5071
- home_boxscore_offensiveRebounds_avg: -0.4884
- h2h_is_named_rivalry: 0.4606
- diff_team_rest_days: 0.4515
- away_team_streak: 0.4467
- away_boxscore_recent_blocks_avg: -0.4347
- away_boxscore_turnovers_avg: 0.4226
- home_team_recent_points_allowed_avg: -0.4171
- home_boxscore_recent_offensiveRebounds_avg: -0.4156
- away_absence_last_game_inactive_count: 0.4019
- diff_boxscore_freeThrowPct_avg: 0.3891
- home_boxscore_freeThrowPct_avg: 0.3704
- home_player_bench_points_avg: -0.3676
- diff_player_top_player_assists_avg: 0.3657
- home_team_games_last_14_days: -0.3615
- away_team_games_last_14_days: -0.3581
- diff_standings_division_games_back: 0.3581
- home_team_rest_days: 0.3468
- diff_record_wins: 0.3430

## Upcoming Predictions

- No future or unresolved games were present in the input file.
