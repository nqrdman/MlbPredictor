# NBA Modeling Export

- Generated at: 2026-03-30T06:44:37.160084+00:00
- Window: 2026-03-24 through 2026-03-30
- Feature history start: 2026-02-20
- Team recent-game lookback: 5
- Games exported: 51
- Team snapshots exported: 102

## Included Features

- Schedule context: venue, attendance, market spread/total, neutral-site flag, conference-game flag
- Team form: win rates, point differential, recent 3/5/N form, home/away splits, rest and schedule density
- Historical context: previous-season win rate when the history window contains prior years
- Standings context: conference/division rank and games back
- Matchup context: recent head-to-head, same-division/conference flags, rivalry flag
- Team boxscore form: possessions, offensive/defensive/net rating, shooting, rebounding, turnovers, pace proxies, paint/fast-break stats
- Player form: top-player and top-rotation scoring/rebounding/assist/minute concentration
- Absence context: last-game inactive counts and estimated production missing
- Current roster context for upcoming games: roster age/size/position mix, injury counts, and projected missing production
- Rating context: pregame Elo for both teams and Elo differential

## Sample Rows

- 2026-03-24T00:00:00+00:00 | Houston Rockets at Chicago Bulls | target_home_team_win=1
- 2026-03-24T01:00:00+00:00 | Toronto Raptors at Utah Jazz | target_home_team_win=0
- 2026-03-24T01:30:00+00:00 | Golden State Warriors at Dallas Mavericks | target_home_team_win=0
- 2026-03-24T02:00:00+00:00 | Brooklyn Nets at Portland Trail Blazers | target_home_team_win=1
- 2026-03-24T02:30:00+00:00 | Milwaukee Bucks at LA Clippers | target_home_team_win=1
- 2026-03-24T23:00:00+00:00 | Sacramento Kings at Charlotte Hornets | target_home_team_win=1
- 2026-03-24T23:30:00+00:00 | New Orleans Pelicans at New York Knicks | target_home_team_win=1
- 2026-03-25T00:00:00+00:00 | Orlando Magic at Cleveland Cavaliers | target_home_team_win=1
