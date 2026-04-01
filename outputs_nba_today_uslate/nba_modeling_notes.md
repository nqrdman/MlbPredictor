# NBA Modeling Export

- Generated at: 2026-03-30T07:22:24.300114+00:00
- Window: 2026-03-30 through 2026-03-31
- Feature history start: 2024-10-01
- Team recent-game lookback: 10
- Games exported: 11
- Team snapshots exported: 22

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

- 2026-03-30T02:00:00+00:00 | Golden State Warriors at Denver Nuggets | target_home_team_win=1
- 2026-03-30T23:00:00+00:00 | Philadelphia 76ers at Miami Heat | target_home_team_win=None
- 2026-03-30T23:30:00+00:00 | Boston Celtics at Atlanta Hawks | target_home_team_win=None
- 2026-03-31T00:00:00+00:00 | Phoenix Suns at Memphis Grizzlies | target_home_team_win=None
- 2026-03-31T00:00:00+00:00 | Chicago Bulls at San Antonio Spurs | target_home_team_win=None
- 2026-03-31T00:30:00+00:00 | Minnesota Timberwolves at Dallas Mavericks | target_home_team_win=None
- 2026-03-31T01:00:00+00:00 | Cleveland Cavaliers at Utah Jazz | target_home_team_win=None
- 2026-03-31T01:30:00+00:00 | Detroit Pistons at Oklahoma City Thunder | target_home_team_win=None
