# MLB Modeling Dataset Builder

This project builds local MLB exports that are useful for predictive modeling. It pulls current schedule and results data from MLB's public Stats API, then combines that with recent team form, recent probable-pitcher form, head-to-head context, and optional weather from Open-Meteo.

## What It Exports

- `outputs/mlb_game_features.csv`: one row per game in the requested date window, with modeling features and a `target_home_team_win` label when the game is already final.
- `outputs/mlb_team_pitcher_snapshots.csv`: one row per team/game side, focused on recent team and probable-pitcher stats.
- `outputs/mlb_modeling_notes.md`: a quick note file describing the run and showing a few sample rows.

## Quick Start

Run today's slate:

```powershell
python .\mlb_model_builder.py --include-weather
```

Run a date range:

```powershell
python .\mlb_model_builder.py --start-date 2026-03-25 --end-date 2026-03-30 --include-weather
```

Build a bigger historical training window:

```powershell
python .\mlb_model_builder.py --start-date 2025-03-27 --end-date 2025-09-30 --season 2025 --recent-games 15 --pitcher-recent-games 6 --include-weather
```

Tune the bullpen lookback too:

```powershell
python .\mlb_model_builder.py --start-date 2025-03-27 --end-date 2026-03-30 --season 2026 --recent-games 15 --pitcher-recent-games 6 --bullpen-recent-games 5 --include-weather
```

For multi-season training, set an earlier feature history window:

```powershell
python .\mlb_model_builder.py --start-date 2025-03-27 --end-date 2026-03-30 --season 2026 --history-start-date 2024-03-28 --recent-games 15 --pitcher-recent-games 6 --bullpen-recent-games 5 --include-weather
```

## Feature Groups

- Team form: win percentage, scoring, runs allowed, run differential, streak, home/away splits, one-run game performance
- Team context: rest days, played-yesterday flag, recent schedule density, travel distance, previous-game context, pythagorean expectation
- Relative strength: division rank, league rank, division games back, league games back
- Head-to-head: recent meetings, recent matchup win rate, recent matchup run differential, last meeting result
- Recent boxscore form: hits, walks, strikeouts, home runs, doubles, triples, steals, left on base, OBP/SLG proxies, runs allowed, errors
- Bullpen workload: recent relief innings, ERA, WHIP, K/9, relievers used, pitches
- Probable pitcher form: recent and season ERA, WHIP, K/9, BB/9, HR/9, innings, strikeouts, walks, batters faced, pitches, days since last appearance
- Probable pitcher profile: handedness, age, height, weight, batting side
- Weather: temperature, humidity, precipitation, wind speed, wind gusts, pressure

## Notes

- The script uses a local cache in `.cache/mlb_model_builder` to speed up repeated runs.
- Pitcher form is based on the probable pitcher listed on the MLB schedule endpoint. If a probable pitcher is missing, the pitcher columns stay blank.
- Weather comes from Open-Meteo using venue coordinates from MLB's venue endpoint.
- The script is standard-library only, so there are no package install steps.

## Modeling Ideas

- Start by training on `mlb_game_features.csv`.
- Use the snapshot export for slate previews, lineup dashboards, or manual inspections.
- You can extend the script to add bullpen usage, batter splits, park factors, standings rank, betting lines, or Statcast-derived metrics.

## Train And Predict

The predictor uses standard-library logistic regression, so it does not need extra packages.

Train on a feature file and score upcoming games in that same file:

```powershell
python .\mlb_predictor.py --input-csv .\outputs\mlb_game_features.csv --output-dir .\outputs --prediction-start-date 2026-03-30
```

Typical workflow for live use:

```powershell
python .\mlb_model_builder.py --start-date 2025-03-27 --end-date 2026-03-30 --season 2026 --history-start-date 2024-03-28 --recent-games 15 --pitcher-recent-games 6 --bullpen-recent-games 5 --include-weather
python .\mlb_predictor.py --input-csv .\outputs\mlb_game_features.csv --output-dir .\outputs
```

Prediction outputs:

- `outputs/mlb_predictions.csv`: win probabilities and predicted winner for unresolved games
- `outputs/mlb_model.json`: learned weights, scaling stats, and validation metrics
- `outputs/mlb_predictions.md`: note file with validation metrics, strongest weighted features, and a readable slate summary

The prediction export now also includes:

- `predicted_home_runs`
- `predicted_away_runs`
- `predicted_total_runs`
- `predicted_run_diff`
- `home_cover_minus_1_5_probability`
- `away_cover_plus_1_5_probability`
- `predicted_runline_side`

Important:

- You need enough finalized games in the feature file for the model to train. If the CSV mostly contains future games, build a larger historical date range first.
- The model is intentionally lightweight and explainable. It is a strong starting point, but you will likely improve it by adding bullpen usage, batter splits, park factors, and lineup data later.

## NBA Modeling Dataset Builder

There is now a parallel NBA workflow in this repo as well. It uses ESPN-powered public JSON endpoints for schedule, finalized boxscores, roster metadata, and current injury snapshots.

Build today’s NBA slate with a deeper historical window:

```powershell
python .\nba_model_builder.py --history-start-date 2025-10-01 --include-rosters
```

Build a larger multi-month feature set:

```powershell
python .\nba_model_builder.py --start-date 2026-03-30 --end-date 2026-04-05 --history-start-date 2024-10-01 --recent-games 10 --include-rosters --output-dir .\outputs_nba
```

What the NBA export includes:

- Team form: season and recent win rates, scoring, point differential, home/away split, streak, rest, back-to-back, schedule density
- Standings context: conference rank, division rank, games back
- Matchup context: head-to-head, same-division and same-conference flags, named rivalry flags
- Team boxscore form: possessions, offensive and defensive rating proxies, net rating, shooting, rebounding, turnovers, paint scoring, fast-break scoring
- Player concentration: top players’ recent scoring, rebounding, assists, minutes, bench scoring, position scoring mix
- Availability context: last-game inactive player impact plus current roster injury counts and estimated missing production for upcoming games
- Market context: spread and total when present on the scoreboard feed
- Rating context: pregame Elo and Elo differential

NBA outputs:

- `outputs_nba/nba_game_features.csv`
- `outputs_nba/nba_team_snapshots.csv`
- `outputs_nba/nba_modeling_notes.md`

Train and score upcoming NBA games:

```powershell
python .\nba_predictor.py --input-csv .\outputs_nba\nba_game_features.csv --output-dir .\outputs_nba
```

Prediction outputs:

- `outputs_nba/nba_predictions.csv`
- `outputs_nba/nba_model.json`
- `outputs_nba/nba_predictions.md`
