#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ESPN_SITE_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ESPN_CORE_BASE = "https://cdn.espn.com/core/nba"
DEFAULT_CACHE_DIR = Path(".cache") / "nba_model_builder"
REQUEST_HEADERS = {
    "User-Agent": "nba-model-builder/1.0",
    "Accept": "application/json",
}


TEAM_DIVISION_MAP: dict[int, dict[str, str]] = {
    1: {"conference": "Eastern", "division": "Southeast"},
    2: {"conference": "Eastern", "division": "Atlantic"},
    3: {"conference": "Eastern", "division": "Central"},
    4: {"conference": "Eastern", "division": "Central"},
    5: {"conference": "Eastern", "division": "Central"},
    6: {"conference": "Western", "division": "Southwest"},
    7: {"conference": "Western", "division": "Northwest"},
    8: {"conference": "Eastern", "division": "Atlantic"},
    9: {"conference": "Western", "division": "Pacific"},
    10: {"conference": "Western", "division": "Northwest"},
    11: {"conference": "Eastern", "division": "Southeast"},
    12: {"conference": "Western", "division": "Pacific"},
    13: {"conference": "Western", "division": "Pacific"},
    14: {"conference": "Eastern", "division": "Southeast"},
    15: {"conference": "Eastern", "division": "Central"},
    16: {"conference": "Western", "division": "Southwest"},
    17: {"conference": "Western", "division": "Southwest"},
    18: {"conference": "Eastern", "division": "Atlantic"},
    19: {"conference": "Eastern", "division": "Central"},
    20: {"conference": "Eastern", "division": "Atlantic"},
    21: {"conference": "Western", "division": "Pacific"},
    22: {"conference": "Western", "division": "Northwest"},
    23: {"conference": "Western", "division": "Southwest"},
    24: {"conference": "Western", "division": "Northwest"},
    25: {"conference": "Eastern", "division": "Atlantic"},
    26: {"conference": "Western", "division": "Southwest"},
    27: {"conference": "Eastern", "division": "Southeast"},
    28: {"conference": "Western", "division": "Northwest"},
    29: {"conference": "Eastern", "division": "Central"},
    30: {"conference": "Eastern", "division": "Southeast"},
}


KNOWN_RIVALRIES = {
    frozenset({2, 13}),
    frozenset({12, 13}),
    frozenset({18, 20}),
    frozenset({18, 25}),
    frozenset({5, 29}),
    frozenset({3, 15}),
    frozenset({4, 29}),
    frozenset({11, 18}),
    frozenset({1, 25}),
    frozenset({23, 26}),
}


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def safe_float(value: Any) -> float | None:
    if value in (None, "", "None", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    parsed = safe_float(value)
    if parsed is None:
        return None
    return int(parsed)


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def pct(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def parse_record_summary(value: str | None) -> tuple[int, int] | None:
    if not value or "-" not in value:
        return None
    wins_text, losses_text = value.split("-", 1)
    wins = safe_int(wins_text)
    losses = safe_int(losses_text)
    if wins is None or losses is None:
        return None
    return wins, losses


def parse_made_attempted(value: str | None) -> tuple[float | None, float | None]:
    if not value or "-" not in value:
        return None, None
    made_text, attempted_text = value.split("-", 1)
    return safe_float(made_text), safe_float(attempted_text)


def parse_minutes(value: str | None) -> float | None:
    if not value:
        return None
    if ":" not in value:
        return safe_float(value)
    minutes_text, seconds_text = value.split(":", 1)
    minutes = safe_float(minutes_text)
    seconds = safe_float(seconds_text)
    if minutes is None or seconds is None:
        return None
    return minutes + (seconds / 60.0)


def game_status_is_final(status: str) -> bool:
    normalized = status.lower()
    return "final" in normalized or normalized == "postponed final"


def value_for_export(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    return value


def date_range(start_dt: date, end_dt: date) -> list[date]:
    total_days = (end_dt - start_dt).days
    return [start_dt + timedelta(days=offset) for offset in range(total_days + 1)]


class JsonClient:
    def __init__(self, cache_dir: Path, ttl_hours: float = 24.0, pause_seconds: float = 0.15) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)
        self.pause_seconds = pause_seconds

    def get_json(self, url: str, params: dict[str, Any] | None = None, force_refresh: bool = False) -> Any:
        query = urlencode(sorted((params or {}).items()), doseq=True)
        full_url = f"{url}?{query}" if query else url
        cache_key = hashlib.sha256(full_url.encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"

        if not force_refresh and cache_path.exists():
            age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
            if age <= self.ttl:
                return json.loads(cache_path.read_text(encoding="utf-8"))

        request = Request(full_url, headers=REQUEST_HEADERS)
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} for {full_url}") from exc
        except URLError as exc:
            raise RuntimeError(f"Network error for {full_url}: {exc.reason}") from exc

        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        time.sleep(self.pause_seconds)
        return payload


@dataclass(slots=True)
class GameRow:
    game_id: int
    game_datetime: datetime
    status: str
    venue_id: str | None
    venue_name: str
    home_team_id: int
    home_team_name: str
    home_team_abbr: str
    away_team_id: int
    away_team_name: str
    away_team_abbr: str
    home_score: int | None
    away_score: int | None
    home_record_summary: str | None
    away_record_summary: str | None
    attendance: int | None
    neutral_site: bool
    conference_competition: bool
    over_under: float | None
    home_spread: float | None
    odds_details: str | None

    @property
    def is_final(self) -> bool:
        return game_status_is_final(self.status)


def fetch_scoreboard_for_date(client: JsonClient, target_date: date) -> dict[str, Any]:
    return client.get_json(
        f"{ESPN_SITE_BASE}/scoreboard",
        {"dates": target_date.strftime("%Y%m%d"), "limit": 200},
    )


def flatten_scoreboard(payload: dict[str, Any]) -> list[GameRow]:
    rows: list[GameRow] = []
    for event in payload.get("events", []):
        competitions = event.get("competitions", [])
        if not competitions:
            continue
        competition = competitions[0]
        competitors = competition.get("competitors", [])
        home = next((item for item in competitors if item.get("homeAway") == "home"), None)
        away = next((item for item in competitors if item.get("homeAway") == "away"), None)
        if not home or not away:
            continue

        home_team = home.get("team", {}) or {}
        away_team = away.get("team", {}) or {}
        home_record_summary = next((row.get("summary") for row in home.get("records", []) if row.get("summary")), None)
        away_record_summary = next((row.get("summary") for row in away.get("records", []) if row.get("summary")), None)
        odds = competition.get("odds", []) or []
        odds_row = odds[0] if odds else {}
        spread = safe_float(odds_row.get("spread"))
        venue = competition.get("venue", {}) or {}
        rows.append(
            GameRow(
                game_id=int(event["id"]),
                game_datetime=parse_iso_datetime(competition["date"]),
                status=(competition.get("status", {}) or {}).get("type", {}).get("description", "Unknown"),
                venue_id=str(venue.get("id")) if venue.get("id") is not None else None,
                venue_name=venue.get("fullName", "Unknown"),
                home_team_id=int(home_team["id"]),
                home_team_name=home_team.get("displayName", "Unknown"),
                home_team_abbr=home_team.get("abbreviation", "UNK"),
                away_team_id=int(away_team["id"]),
                away_team_name=away_team.get("displayName", "Unknown"),
                away_team_abbr=away_team.get("abbreviation", "UNK"),
                home_score=safe_int(home.get("score")),
                away_score=safe_int(away.get("score")),
                home_record_summary=home_record_summary,
                away_record_summary=away_record_summary,
                attendance=safe_int(competition.get("attendance")),
                neutral_site=bool(competition.get("neutralSite")),
                conference_competition=bool(competition.get("conferenceCompetition")),
                over_under=safe_float(odds_row.get("overUnder")),
                home_spread=spread,
                odds_details=odds_row.get("details"),
            )
        )
    return sorted(rows, key=lambda row: row.game_datetime)


def fetch_schedule_range(client: JsonClient, start_dt: date, end_dt: date) -> list[GameRow]:
    rows: list[GameRow] = []
    for target_date in date_range(start_dt, end_dt):
        rows.extend(flatten_scoreboard(fetch_scoreboard_for_date(client, target_date)))
    deduped: dict[int, GameRow] = {}
    for row in rows:
        deduped[row.game_id] = row
    return sorted(deduped.values(), key=lambda row: row.game_datetime)


def fetch_boxscore(client: JsonClient, game_id: int) -> dict[str, Any]:
    payload = client.get_json(f"{ESPN_CORE_BASE}/boxscore", {"xhr": 1, "gameId": game_id})
    return ((payload.get("gamepackageJSON") or {}).get("boxscore") or {})


def fetch_teams_metadata(client: JsonClient) -> dict[int, dict[str, Any]]:
    payload = client.get_json(f"{ESPN_SITE_BASE}/teams")
    metadata: dict[int, dict[str, Any]] = {}
    for sport in payload.get("sports", []):
        for league in sport.get("leagues", []):
            teams_block = league.get("teams")
            if not teams_block:
                continue
            if isinstance(teams_block, str):
                team_payload = client.get_json(teams_block.strip())
                sports = team_payload.get("sports", [])
                if not sports:
                    continue
                leagues = sports[0].get("leagues", [])
                if not leagues:
                    continue
                teams_iterable = leagues[0].get("teams", [])
            else:
                teams_iterable = teams_block
            for row in teams_iterable:
                team = row.get("team", {}) or {}
                team_id = safe_int(team.get("id"))
                if team_id is None:
                    continue
                division_meta = TEAM_DIVISION_MAP.get(team_id, {})
                metadata[team_id] = {
                    "display_name": team.get("displayName", ""),
                    "abbreviation": team.get("abbreviation", ""),
                    "location": team.get("location", ""),
                    "name": team.get("name", ""),
                    "conference": division_meta.get("conference"),
                    "division": division_meta.get("division"),
                }
    return metadata


def fetch_team_roster(client: JsonClient, team_id: int) -> dict[str, Any]:
    return client.get_json(f"{ESPN_SITE_BASE}/teams/{team_id}/roster")


def normalize_result(game: GameRow, team_id: int) -> dict[str, Any]:
    is_home = game.home_team_id == team_id
    team_score = game.home_score if is_home else game.away_score
    opp_score = game.away_score if is_home else game.home_score
    if team_score is None or opp_score is None:
        won = None
        margin = None
    else:
        won = team_score > opp_score
        margin = team_score - opp_score
    opponent_id = game.away_team_id if is_home else game.home_team_id
    return {
        "game_id": game.game_id,
        "game_datetime": game.game_datetime,
        "team_id": team_id,
        "opponent_id": opponent_id,
        "is_home": is_home,
        "points_scored": team_score,
        "points_allowed": opp_score,
        "won": won,
        "margin": margin,
        "venue_name": game.venue_name,
        "attendance": game.attendance,
        "neutral_site": game.neutral_site,
        "conference_competition": game.conference_competition,
        "over_under": game.over_under,
        "home_spread": game.home_spread,
    }


def build_team_history(games: list[GameRow]) -> dict[int, list[dict[str, Any]]]:
    history: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for game in games:
        if not game.is_final:
            continue
        history[game.home_team_id].append(normalize_result(game, game.home_team_id))
        history[game.away_team_id].append(normalize_result(game, game.away_team_id))
    for logs in history.values():
        logs.sort(key=lambda row: row["game_datetime"])
    return history


def compute_streak(games: list[dict[str, Any]]) -> int:
    streak = 0
    for game in reversed(games):
        if game["won"] is None:
            continue
        if game["won"]:
            if streak < 0:
                break
            streak += 1
        else:
            if streak > 0:
                break
            streak -= 1
    return streak


def build_standings_snapshot(
    team_history: dict[int, list[dict[str, Any]]],
    before_dt: datetime,
    team_metadata: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    standings: dict[int, dict[str, Any]] = {}
    for team_id, logs in team_history.items():
        prior = [game for game in logs if game["game_datetime"] < before_dt]
        wins = sum(1 for game in prior if game["won"] is True)
        losses = sum(1 for game in prior if game["won"] is False)
        points_scored = sum(float(game["points_scored"]) for game in prior if game["points_scored"] is not None)
        points_allowed = sum(float(game["points_allowed"]) for game in prior if game["points_allowed"] is not None)
        games_played = wins + losses
        standings[team_id] = {
            "wins": wins,
            "losses": losses,
            "games_played": games_played,
            "win_pct": pct(wins, games_played),
            "points_diff_total": points_scored - points_allowed,
            "points_diff_avg": (points_scored - points_allowed) / games_played if games_played else None,
            "conference": team_metadata.get(team_id, {}).get("conference"),
            "division": team_metadata.get(team_id, {}).get("division"),
        }

    conference_groups: dict[str | None, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    division_groups: dict[str | None, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for team_id, row in standings.items():
        conference_groups[row["conference"]].append((team_id, row))
        division_groups[row["division"]].append((team_id, row))

    for group in conference_groups.values():
        group.sort(key=lambda item: ((item[1]["win_pct"] or 0.0), (item[1]["points_diff_avg"] or 0.0)), reverse=True)
        leader_wins = group[0][1]["wins"] if group else 0
        leader_losses = group[0][1]["losses"] if group else 0
        for rank, (team_id, row) in enumerate(group, start=1):
            games_back = ((leader_wins - row["wins"]) + (row["losses"] - leader_losses)) / 2.0
            standings[team_id]["conference_rank"] = rank
            standings[team_id]["conference_games_back"] = games_back

    for group in division_groups.values():
        group.sort(key=lambda item: ((item[1]["win_pct"] or 0.0), (item[1]["points_diff_avg"] or 0.0)), reverse=True)
        leader_wins = group[0][1]["wins"] if group else 0
        leader_losses = group[0][1]["losses"] if group else 0
        for rank, (team_id, row) in enumerate(group, start=1):
            games_back = ((leader_wins - row["wins"]) + (row["losses"] - leader_losses)) / 2.0
            standings[team_id]["division_rank"] = rank
            standings[team_id]["division_games_back"] = games_back

    return standings


def summarize_team_form(team_logs: list[dict[str, Any]], before_dt: datetime, recent_games: int) -> dict[str, Any]:
    prior = [game for game in team_logs if game["game_datetime"] < before_dt]
    recent = prior[-recent_games:]
    recent_3 = prior[-3:]
    recent_5 = prior[-5:]
    home_games = [game for game in prior if game["is_home"]]
    away_games = [game for game in prior if not game["is_home"]]
    last_game = prior[-1] if prior else None
    back_to_back = None
    rest_days = None
    if last_game:
        delta_days = (before_dt.date() - last_game["game_datetime"].date()).days
        back_to_back = int(delta_days == 1)
        rest_days = max(delta_days - 1, 0)

    recent_wins = sum(1 for game in recent if game["won"] is True)
    season_wins = sum(1 for game in prior if game["won"] is True)
    season_losses = sum(1 for game in prior if game["won"] is False)
    points_scored = [float(game["points_scored"]) for game in prior if game["points_scored"] is not None]
    points_allowed = [float(game["points_allowed"]) for game in prior if game["points_allowed"] is not None]
    margins = [float(game["margin"]) for game in prior if game["margin"] is not None]
    prior_seasons = sorted({game["game_datetime"].year for game in prior})
    previous_season_games = [
        game for game in prior if game["game_datetime"].year == prior_seasons[-2]
    ] if len(prior_seasons) >= 2 else []
    previous_season_wins = sum(1 for game in previous_season_games if game["won"] is True)
    previous_season_losses = sum(1 for game in previous_season_games if game["won"] is False)
    recent_7_days = before_dt - timedelta(days=7)
    recent_14_days = before_dt - timedelta(days=14)
    games_last_7 = sum(1 for game in prior if game["game_datetime"] >= recent_7_days)
    games_last_14 = sum(1 for game in prior if game["game_datetime"] >= recent_14_days)

    return {
        "games_played": len(prior),
        "wins": season_wins,
        "losses": season_losses,
        "win_pct": pct(season_wins, season_wins + season_losses),
        "points_scored_avg": mean(points_scored),
        "points_allowed_avg": mean(points_allowed),
        "point_diff_avg": mean(margins),
        "recent_games": len(recent),
        "recent_win_pct": pct(recent_wins, len(recent)),
        "recent_points_scored_avg": mean([float(game["points_scored"]) for game in recent if game["points_scored"] is not None]),
        "recent_points_allowed_avg": mean([float(game["points_allowed"]) for game in recent if game["points_allowed"] is not None]),
        "recent_point_diff_avg": mean([float(game["margin"]) for game in recent if game["margin"] is not None]),
        "recent3_win_pct": pct(sum(1 for game in recent_3 if game["won"] is True), len(recent_3)),
        "recent5_win_pct": pct(sum(1 for game in recent_5 if game["won"] is True), len(recent_5)),
        "recent3_point_diff_avg": mean([float(game["margin"]) for game in recent_3 if game["margin"] is not None]),
        "recent5_point_diff_avg": mean([float(game["margin"]) for game in recent_5 if game["margin"] is not None]),
        "home_win_pct": pct(sum(1 for game in home_games if game["won"] is True), len(home_games)),
        "away_win_pct": pct(sum(1 for game in away_games if game["won"] is True), len(away_games)),
        "home_points_scored_avg": mean([float(game["points_scored"]) for game in home_games if game["points_scored"] is not None]),
        "away_points_scored_avg": mean([float(game["points_scored"]) for game in away_games if game["points_scored"] is not None]),
        "home_points_allowed_avg": mean([float(game["points_allowed"]) for game in home_games if game["points_allowed"] is not None]),
        "away_points_allowed_avg": mean([float(game["points_allowed"]) for game in away_games if game["points_allowed"] is not None]),
        "streak": compute_streak(prior),
        "rest_days": rest_days,
        "back_to_back": back_to_back,
        "games_last_7_days": games_last_7,
        "games_last_14_days": games_last_14,
        "last_game_margin": last_game["margin"] if last_game else None,
        "last_game_won": last_game["won"] if last_game else None,
        "previous_season_win_pct": pct(previous_season_wins, previous_season_wins + previous_season_losses),
        "previous_season_games": len(previous_season_games),
    }


def summarize_head_to_head(
    all_games: list[GameRow],
    home_team_id: int,
    away_team_id: int,
    before_dt: datetime,
    recent_games: int,
) -> dict[str, Any]:
    prior = [
        game
        for game in all_games
        if game.is_final
        and game.game_datetime < before_dt
        and {game.home_team_id, game.away_team_id} == {home_team_id, away_team_id}
    ]
    recent = prior[-recent_games:]
    home_wins = 0
    home_margins: list[float] = []
    for game in recent:
        if game.home_score is None or game.away_score is None:
            continue
        if game.home_team_id == home_team_id:
            margin = float(game.home_score - game.away_score)
            home_wins += int(game.home_score > game.away_score)
        else:
            margin = float(game.away_score - game.home_score)
            home_wins += int(game.away_score > game.home_score)
        home_margins.append(margin)
    last_meeting_home_won = None
    if recent:
        last_game = recent[-1]
        if last_game.home_score is not None and last_game.away_score is not None:
            if last_game.home_team_id == home_team_id:
                last_meeting_home_won = last_game.home_score > last_game.away_score
            else:
                last_meeting_home_won = last_game.away_score > last_game.home_score
    return {
        "games": len(prior),
        "recent_games": len(recent),
        "home_team_recent_win_pct": pct(home_wins, len(recent)),
        "home_team_recent_margin_avg": mean(home_margins),
        "last_meeting_home_team_won": last_meeting_home_won,
        "same_division": int(
            TEAM_DIVISION_MAP.get(home_team_id, {}).get("division") == TEAM_DIVISION_MAP.get(away_team_id, {}).get("division")
        ),
        "same_conference": int(
            TEAM_DIVISION_MAP.get(home_team_id, {}).get("conference") == TEAM_DIVISION_MAP.get(away_team_id, {}).get("conference")
        ),
        "is_named_rivalry": int(frozenset({home_team_id, away_team_id}) in KNOWN_RIVALRIES),
    }


def parse_team_stat_block(stat_rows: list[dict[str, Any]]) -> dict[str, float | None]:
    summary: dict[str, float | None] = {}
    raw: dict[str, str] = {}
    for row in stat_rows:
        name = row.get("name")
        display_value = row.get("displayValue")
        if not name or display_value in (None, ""):
            continue
        raw[name] = display_value
        parsed = safe_float(display_value)
        if parsed is not None:
            summary[name] = parsed

    fgm, fga = parse_made_attempted(raw.get("fieldGoalsMade-fieldGoalsAttempted"))
    three_made, three_att = parse_made_attempted(raw.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
    ftm, fta = parse_made_attempted(raw.get("freeThrowsMade-freeThrowsAttempted"))
    summary["field_goals_made"] = fgm
    summary["field_goals_attempted"] = fga
    summary["three_points_made"] = three_made
    summary["three_points_attempted"] = three_att
    summary["free_throws_made"] = ftm
    summary["free_throws_attempted"] = fta
    turnovers = summary.get("turnovers")
    offensive_rebounds = summary.get("offensiveRebounds")
    points = summary.get("points")
    possessions = None
    if fga is not None and offensive_rebounds is not None and turnovers is not None and fta is not None:
        possessions = fga - offensive_rebounds + turnovers + (0.44 * fta)
    summary["estimated_possessions"] = possessions
    if fgm is not None and three_made is not None and fga:
        summary["effective_field_goal_pct"] = (fgm + (0.5 * three_made)) / fga
    else:
        summary["effective_field_goal_pct"] = None
    if points is not None and fga is not None and fta is not None and (fga + 0.44 * fta) > 0:
        summary["true_shooting_pct"] = points / (2.0 * (fga + (0.44 * fta)))
    else:
        summary["true_shooting_pct"] = None
    return summary


def parse_player_stat_table(team_id: int, game_id: int, game_datetime: datetime, block: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stat_table in block.get("statistics", []):
        keys = stat_table.get("keys", [])
        for player_row in stat_table.get("athletes", []):
            athlete = player_row.get("athlete", {}) or {}
            stats = player_row.get("stats", []) or []
            stat_map = {key: stats[index] if index < len(stats) else None for index, key in enumerate(keys)}
            plus_minus_text = str(stat_map.get("plusMinus", "")).replace("+", "")
            three_made, three_attempted = parse_made_attempted(stat_map.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
            fg_made, fg_attempted = parse_made_attempted(stat_map.get("fieldGoalsMade-fieldGoalsAttempted"))
            ft_made, ft_attempted = parse_made_attempted(stat_map.get("freeThrowsMade-freeThrowsAttempted"))
            rows.append(
                {
                    "game_id": game_id,
                    "game_datetime": game_datetime,
                    "team_id": team_id,
                    "player_id": safe_int(athlete.get("id")),
                    "player_name": athlete.get("displayName"),
                    "position": ((athlete.get("position") or {}).get("abbreviation")),
                    "starter": bool(player_row.get("starter")),
                    "active": bool(player_row.get("active")),
                    "did_not_play": bool(player_row.get("didNotPlay")),
                    "reason": player_row.get("reason"),
                    "minutes": parse_minutes(stat_map.get("minutes")),
                    "points": safe_float(stat_map.get("points")),
                    "rebounds": safe_float(stat_map.get("rebounds")),
                    "assists": safe_float(stat_map.get("assists")),
                    "turnovers": safe_float(stat_map.get("turnovers")),
                    "steals": safe_float(stat_map.get("steals")),
                    "blocks": safe_float(stat_map.get("blocks")),
                    "plus_minus": safe_float(plus_minus_text),
                    "field_goals_made": fg_made,
                    "field_goals_attempted": fg_attempted,
                    "three_points_made": three_made,
                    "three_points_attempted": three_attempted,
                    "free_throws_made": ft_made,
                    "free_throws_attempted": ft_attempted,
                }
            )
    return rows


def build_boxscore_histories(
    client: JsonClient,
    games: list[GameRow],
) -> tuple[dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]], dict[int, dict[str, Any]]]:
    team_boxscores: dict[int, list[dict[str, Any]]] = defaultdict(list)
    player_logs: dict[int, list[dict[str, Any]]] = defaultdict(list)
    game_boxscores: dict[int, dict[str, Any]] = {}
    for game in games:
        if not game.is_final:
            continue
        boxscore = fetch_boxscore(client, game.game_id)
        game_boxscores[game.game_id] = boxscore
        team_blocks = boxscore.get("teams", []) or []
        player_blocks = boxscore.get("players", []) or []
        parsed_team_blocks: dict[int, dict[str, Any]] = {}
        for block in team_blocks:
            team = block.get("team", {}) or {}
            team_id = safe_int(team.get("id"))
            if team_id is None:
                continue
            parsed_team_blocks[team_id] = parse_team_stat_block(block.get("statistics", []))
        for team_id, stats in parsed_team_blocks.items():
            opponent_id = game.away_team_id if team_id == game.home_team_id else game.home_team_id
            opponent_stats = parsed_team_blocks.get(opponent_id, {})
            points = stats.get("points")
            opponent_points = opponent_stats.get("points")
            possessions = stats.get("estimated_possessions")
            opponent_possessions = opponent_stats.get("estimated_possessions")
            offensive_rating = (points / possessions * 100.0) if points is not None and possessions and possessions > 0 else None
            defensive_rating = (
                (opponent_points / opponent_possessions * 100.0)
                if opponent_points is not None and opponent_possessions and opponent_possessions > 0
                else None
            )
            row = {
                "game_id": game.game_id,
                "game_datetime": game.game_datetime,
                "team_id": team_id,
                "opponent_id": opponent_id,
                "is_home": int(team_id == game.home_team_id),
                "points": points,
                "opponent_points": opponent_points,
                "margin": (points - opponent_points) if points is not None and opponent_points is not None else None,
                "estimated_possessions": possessions,
                "opponent_estimated_possessions": opponent_possessions,
                "offensive_rating": offensive_rating,
                "defensive_rating": defensive_rating,
                "net_rating": (offensive_rating - defensive_rating) if offensive_rating is not None and defensive_rating is not None else None,
                **stats,
            }
            if stats.get("totalRebounds") is not None and opponent_stats.get("totalRebounds") is not None:
                total_rebounds = stats["totalRebounds"] + opponent_stats["totalRebounds"]
                row["rebound_share"] = stats["totalRebounds"] / total_rebounds if total_rebounds else None
            team_boxscores[team_id].append(row)

        for block in player_blocks:
            team = block.get("team", {}) or {}
            team_id = safe_int(team.get("id"))
            if team_id is None:
                continue
            player_logs[team_id].extend(parse_player_stat_table(team_id, game.game_id, game.game_datetime, block))

    for rows in team_boxscores.values():
        rows.sort(key=lambda row: row["game_datetime"])
    for rows in player_logs.values():
        rows.sort(key=lambda row: row["game_datetime"])
    return team_boxscores, player_logs, game_boxscores


def summarize_team_boxscore_form(team_logs: list[dict[str, Any]], before_dt: datetime, recent_games: int) -> dict[str, Any]:
    prior = [row for row in team_logs if row["game_datetime"] < before_dt]
    recent = prior[-recent_games:]
    keys = [
        "points",
        "opponent_points",
        "margin",
        "estimated_possessions",
        "offensive_rating",
        "defensive_rating",
        "net_rating",
        "fieldGoalPct",
        "threePointFieldGoalPct",
        "freeThrowPct",
        "totalRebounds",
        "offensiveRebounds",
        "defensiveRebounds",
        "assists",
        "turnovers",
        "steals",
        "blocks",
        "fastBreakPoints",
        "pointsInPaint",
        "turnoverPoints",
        "leadChanges",
        "leadPercentage",
        "effective_field_goal_pct",
        "true_shooting_pct",
        "rebound_share",
    ]
    summary: dict[str, Any] = {}
    for key in keys:
        summary[f"{key}_avg"] = mean([float(row[key]) for row in prior if row.get(key) is not None])
        summary[f"recent_{key}_avg"] = mean([float(row[key]) for row in recent if row.get(key) is not None])
    return summary


def summarize_player_form(player_logs: list[dict[str, Any]], before_dt: datetime, recent_games: int) -> dict[str, Any]:
    prior = [row for row in player_logs if row["game_datetime"] < before_dt and not row.get("did_not_play")]
    if not prior:
        return {}
    recent = prior[-(recent_games * 12):]
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in recent:
        player_id = row.get("player_id")
        if player_id is None:
            continue
        by_player[player_id].append(row)

    player_summaries: list[dict[str, Any]] = []
    for logs in by_player.values():
        logs.sort(key=lambda row: row["game_datetime"])
        points_avg = mean([float(row["points"]) for row in logs if row.get("points") is not None]) or 0.0
        rebounds_avg = mean([float(row["rebounds"]) for row in logs if row.get("rebounds") is not None]) or 0.0
        assists_avg = mean([float(row["assists"]) for row in logs if row.get("assists") is not None]) or 0.0
        minutes_avg = mean([float(row["minutes"]) for row in logs if row.get("minutes") is not None]) or 0.0
        threes_avg = mean([float(row["three_points_made"]) for row in logs if row.get("three_points_made") is not None]) or 0.0
        usage_proxy = points_avg + rebounds_avg + assists_avg
        player_summaries.append(
            {
                "player_id": logs[-1].get("player_id"),
                "player_name": logs[-1].get("player_name"),
                "position": logs[-1].get("position"),
                "points_avg": points_avg,
                "rebounds_avg": rebounds_avg,
                "assists_avg": assists_avg,
                "minutes_avg": minutes_avg,
                "three_points_avg": threes_avg,
                "usage_proxy": usage_proxy,
            }
        )

    player_summaries.sort(key=lambda row: (row["minutes_avg"], row["usage_proxy"]), reverse=True)
    top3 = player_summaries[:3]
    top5 = player_summaries[:5]
    bench = player_summaries[5:]
    guards = [row for row in player_summaries if row.get("position") == "G"]
    forwards = [row for row in player_summaries if row.get("position") == "F"]
    centers = [row for row in player_summaries if row.get("position") == "C"]
    return {
        "rotation_player_count": len(player_summaries),
        "top3_points_avg": sum(row["points_avg"] for row in top3),
        "top3_rebounds_avg": sum(row["rebounds_avg"] for row in top3),
        "top3_assists_avg": sum(row["assists_avg"] for row in top3),
        "top3_minutes_avg": sum(row["minutes_avg"] for row in top3),
        "top5_points_avg": sum(row["points_avg"] for row in top5),
        "top5_usage_proxy_avg": sum(row["usage_proxy"] for row in top5),
        "bench_points_avg": sum(row["points_avg"] for row in bench),
        "guard_points_avg": sum(row["points_avg"] for row in guards),
        "forward_points_avg": sum(row["points_avg"] for row in forwards),
        "center_points_avg": sum(row["points_avg"] for row in centers),
        "top_player_points_avg": top3[0]["points_avg"] if top3 else None,
        "top_player_rebounds_avg": top3[0]["rebounds_avg"] if top3 else None,
        "top_player_assists_avg": top3[0]["assists_avg"] if top3 else None,
        "top_player_minutes_avg": top3[0]["minutes_avg"] if top3 else None,
        "second_player_points_avg": top3[1]["points_avg"] if len(top3) > 1 else None,
        "third_player_points_avg": top3[2]["points_avg"] if len(top3) > 2 else None,
    }


def summarize_recent_absences(player_logs: list[dict[str, Any]], before_dt: datetime, recent_games: int) -> dict[str, Any]:
    prior = [row for row in player_logs if row["game_datetime"] < before_dt]
    if not prior:
        return {}
    recent = prior[-(recent_games * 12):]
    recent_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in recent:
        player_id = row.get("player_id")
        if player_id is None:
            continue
        recent_by_player[player_id].append(row)
    baseline: dict[int, dict[str, float]] = {}
    for player_id, logs in recent_by_player.items():
        played = [row for row in logs if not row.get("did_not_play")]
        if not played:
            continue
        baseline[player_id] = {
            "points": mean([float(row["points"]) for row in played if row.get("points") is not None]) or 0.0,
            "rebounds": mean([float(row["rebounds"]) for row in played if row.get("rebounds") is not None]) or 0.0,
            "assists": mean([float(row["assists"]) for row in played if row.get("assists") is not None]) or 0.0,
            "minutes": mean([float(row["minutes"]) for row in played if row.get("minutes") is not None]) or 0.0,
        }
    last_game_dt = max(row["game_datetime"] for row in prior)
    last_game_rows = [row for row in prior if row["game_datetime"] == last_game_dt]
    inactive = [row for row in last_game_rows if row.get("did_not_play")]
    return {
        "last_game_inactive_count": len(inactive),
        "last_game_missing_points_estimate": sum(baseline.get(row.get("player_id"), {}).get("points", 0.0) for row in inactive),
        "last_game_missing_rebounds_estimate": sum(baseline.get(row.get("player_id"), {}).get("rebounds", 0.0) for row in inactive),
        "last_game_missing_assists_estimate": sum(baseline.get(row.get("player_id"), {}).get("assists", 0.0) for row in inactive),
        "last_game_missing_minutes_estimate": sum(baseline.get(row.get("player_id"), {}).get("minutes", 0.0) for row in inactive),
    }


def summarize_current_roster(
    roster_payload: dict[str, Any],
    player_logs: list[dict[str, Any]],
    before_dt: datetime,
) -> dict[str, Any]:
    athletes = roster_payload.get("athletes", []) or []
    recent_player_rows = [row for row in player_logs if row["game_datetime"] < before_dt and not row.get("did_not_play")]
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in recent_player_rows:
        player_id = row.get("player_id")
        if player_id is None:
            continue
        by_player[player_id].append(row)

    out_count = 0
    doubtful_count = 0
    questionable_count = 0
    suspended_count = 0
    injured_points = 0.0
    injured_rebounds = 0.0
    injured_assists = 0.0
    injured_minutes = 0.0
    ages: list[float] = []
    heights: list[float] = []
    weights: list[float] = []
    salaries: list[float] = []
    guards = 0
    forwards = 0
    centers = 0

    for athlete in athletes:
        player_id = safe_int(athlete.get("id"))
        age = safe_float(athlete.get("age"))
        height = safe_float(athlete.get("height"))
        weight = safe_float(athlete.get("weight"))
        if age is not None:
            ages.append(age)
        if height is not None:
            heights.append(height)
        if weight is not None:
            weights.append(weight)
        salary = safe_float(((athlete.get("contract") or {}).get("salary")))
        if salary is not None:
            salaries.append(salary)
        position = ((athlete.get("position") or {}).get("abbreviation") or "").upper()
        if position == "G":
            guards += 1
        elif position == "F":
            forwards += 1
        elif position == "C":
            centers += 1

        status_rows = athlete.get("injuries", []) or []
        status_text = " ".join(str(row.get("status", "")) for row in status_rows).lower()
        if "out" in status_text:
            out_count += 1
        if "doubt" in status_text:
            doubtful_count += 1
        if "question" in status_text:
            questionable_count += 1
        if "suspension" in status_text or "suspend" in status_text:
            suspended_count += 1

        if not status_text or player_id is None:
            continue
        played = by_player.get(player_id, [])
        if not played:
            continue
        points_avg = mean([float(row["points"]) for row in played if row.get("points") is not None]) or 0.0
        rebounds_avg = mean([float(row["rebounds"]) for row in played if row.get("rebounds") is not None]) or 0.0
        assists_avg = mean([float(row["assists"]) for row in played if row.get("assists") is not None]) or 0.0
        minutes_avg = mean([float(row["minutes"]) for row in played if row.get("minutes") is not None]) or 0.0
        injured_points += points_avg
        injured_rebounds += rebounds_avg
        injured_assists += assists_avg
        injured_minutes += minutes_avg

    return {
        "roster_player_count": len(athletes),
        "roster_avg_age": mean(ages),
        "roster_avg_height_inches": mean(heights),
        "roster_avg_weight_lbs": mean(weights),
        "roster_total_salary": sum(salaries) if salaries else None,
        "roster_guard_count": guards,
        "roster_forward_count": forwards,
        "roster_center_count": centers,
        "current_injury_out_count": out_count,
        "current_injury_doubtful_count": doubtful_count,
        "current_injury_questionable_count": questionable_count,
        "current_injury_suspended_count": suspended_count,
        "current_injury_points_impact": injured_points,
        "current_injury_rebounds_impact": injured_rebounds,
        "current_injury_assists_impact": injured_assists,
        "current_injury_minutes_impact": injured_minutes,
    }


def build_pregame_elo_snapshots(games: list[GameRow]) -> dict[int, dict[int, float]]:
    ratings: dict[int, float] = defaultdict(lambda: 1500.0)
    snapshots: dict[int, dict[int, float]] = {}
    sorted_games = sorted(games, key=lambda row: row.game_datetime)
    current_season: int | None = None
    for game in sorted_games:
        season_key = game.game_datetime.year if game.game_datetime.month >= 7 else game.game_datetime.year
        if current_season is None:
            current_season = season_key
        elif season_key != current_season:
            for team_id in list(ratings):
                ratings[team_id] = 1500.0 + ((ratings[team_id] - 1500.0) * 0.75)
            current_season = season_key
        snapshots[game.game_id] = {
            game.home_team_id: ratings[game.home_team_id],
            game.away_team_id: ratings[game.away_team_id],
        }
        if not game.is_final or game.home_score is None or game.away_score is None:
            continue
        home_rating = ratings[game.home_team_id]
        away_rating = ratings[game.away_team_id]
        expected_home = 1.0 / (1.0 + (10.0 ** ((away_rating - (home_rating + 65.0)) / 400.0)))
        actual_home = 1.0 if game.home_score > game.away_score else 0.0
        margin = abs(game.home_score - game.away_score)
        rating_gap = abs(home_rating - away_rating)
        multiplier = math.log(max(margin, 1) + 1.0) * (2.2 / ((rating_gap * 0.001) + 2.2))
        delta = 20.0 * multiplier * (actual_home - expected_home)
        ratings[game.home_team_id] += delta
        ratings[game.away_team_id] -= delta
    return snapshots


def build_game_feature_rows(
    client: JsonClient,
    target_games: list[GameRow],
    history_games: list[GameRow],
    team_metadata: dict[int, dict[str, Any]],
    recent_games: int,
    include_rosters: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    team_history = build_team_history(history_games)
    team_boxscore_history, player_logs_history, _ = build_boxscore_histories(client, history_games)
    elo_snapshots = build_pregame_elo_snapshots(history_games)
    roster_cache: dict[int, dict[str, Any]] = {}
    if include_rosters:
        target_team_ids = {team_id for game in target_games for team_id in (game.home_team_id, game.away_team_id)}
        for team_id in target_team_ids:
            roster_cache[team_id] = fetch_team_roster(client, team_id)

    game_rows: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []
    today = date.today()
    for game in target_games:
        standings = build_standings_snapshot(team_history, game.game_datetime, team_metadata)
        home_form = summarize_team_form(team_history.get(game.home_team_id, []), game.game_datetime, recent_games)
        away_form = summarize_team_form(team_history.get(game.away_team_id, []), game.game_datetime, recent_games)
        h2h = summarize_head_to_head(history_games, game.home_team_id, game.away_team_id, game.game_datetime, recent_games)
        home_box = summarize_team_boxscore_form(team_boxscore_history.get(game.home_team_id, []), game.game_datetime, recent_games)
        away_box = summarize_team_boxscore_form(team_boxscore_history.get(game.away_team_id, []), game.game_datetime, recent_games)
        home_players = summarize_player_form(player_logs_history.get(game.home_team_id, []), game.game_datetime, recent_games)
        away_players = summarize_player_form(player_logs_history.get(game.away_team_id, []), game.game_datetime, recent_games)
        home_absences = summarize_recent_absences(player_logs_history.get(game.home_team_id, []), game.game_datetime, recent_games)
        away_absences = summarize_recent_absences(player_logs_history.get(game.away_team_id, []), game.game_datetime, recent_games)
        home_standings = standings.get(game.home_team_id, {})
        away_standings = standings.get(game.away_team_id, {})
        elo_row = elo_snapshots.get(game.game_id, {})
        home_elo = elo_row.get(game.home_team_id)
        away_elo = elo_row.get(game.away_team_id)
        home_record = parse_record_summary(game.home_record_summary)
        away_record = parse_record_summary(game.away_record_summary)

        home_roster = {}
        away_roster = {}
        if include_rosters and game.game_datetime.date() >= today:
            home_roster = summarize_current_roster(
                roster_cache.get(game.home_team_id, {}),
                player_logs_history.get(game.home_team_id, []),
                game.game_datetime,
            )
            away_roster = summarize_current_roster(
                roster_cache.get(game.away_team_id, {}),
                player_logs_history.get(game.away_team_id, []),
                game.game_datetime,
            )

        home_team_won = None
        if game.is_final and game.home_score is not None and game.away_score is not None:
            home_team_won = game.home_score > game.away_score

        row = {
            "game_id": game.game_id,
            "game_date_utc": game.game_datetime.isoformat(),
            "status": game.status,
            "venue_name": game.venue_name,
            "home_team_id": game.home_team_id,
            "home_team_name": game.home_team_name,
            "home_team_abbr": game.home_team_abbr,
            "away_team_id": game.away_team_id,
            "away_team_name": game.away_team_name,
            "away_team_abbr": game.away_team_abbr,
            "home_score": game.home_score,
            "away_score": game.away_score,
            "target_home_team_win": home_team_won,
            "attendance": game.attendance,
            "neutral_site": int(game.neutral_site),
            "conference_competition": int(game.conference_competition),
            "market_home_spread": game.home_spread,
            "market_total": game.over_under,
            "home_record_wins": home_record[0] if home_record else None,
            "home_record_losses": home_record[1] if home_record else None,
            "away_record_wins": away_record[0] if away_record else None,
            "away_record_losses": away_record[1] if away_record else None,
            "home_team_elo_pre": home_elo,
            "away_team_elo_pre": away_elo,
            "elo_diff": (home_elo - away_elo) if home_elo is not None and away_elo is not None else None,
            **{f"home_team_{key}": value for key, value in home_form.items()},
            **{f"away_team_{key}": value for key, value in away_form.items()},
            **{f"home_standings_{key}": value for key, value in home_standings.items()},
            **{f"away_standings_{key}": value for key, value in away_standings.items()},
            **{f"h2h_{key}": value for key, value in h2h.items()},
            **{f"home_boxscore_{key}": value for key, value in home_box.items()},
            **{f"away_boxscore_{key}": value for key, value in away_box.items()},
            **{f"home_player_{key}": value for key, value in home_players.items()},
            **{f"away_player_{key}": value for key, value in away_players.items()},
            **{f"home_absence_{key}": value for key, value in home_absences.items()},
            **{f"away_absence_{key}": value for key, value in away_absences.items()},
            **{f"home_roster_{key}": value for key, value in home_roster.items()},
            **{f"away_roster_{key}": value for key, value in away_roster.items()},
        }
        game_rows.append({key: value_for_export(value) for key, value in row.items()})

        home_snapshot = {
            "game_id": game.game_id,
            "game_date_utc": game.game_datetime.isoformat(),
            "team_side": "home",
            "team_id": game.home_team_id,
            "team_name": game.home_team_name,
            "team_abbr": game.home_team_abbr,
            "opponent_team_id": game.away_team_id,
            "opponent_team_name": game.away_team_name,
            "elo_pre": home_elo,
            **home_form,
            **{f"standings_{key}": value for key, value in home_standings.items()},
            **{f"boxscore_{key}": value for key, value in home_box.items()},
            **{f"player_{key}": value for key, value in home_players.items()},
            **{f"absence_{key}": value for key, value in home_absences.items()},
            **{f"roster_{key}": value for key, value in home_roster.items()},
        }
        away_snapshot = {
            "game_id": game.game_id,
            "game_date_utc": game.game_datetime.isoformat(),
            "team_side": "away",
            "team_id": game.away_team_id,
            "team_name": game.away_team_name,
            "team_abbr": game.away_team_abbr,
            "opponent_team_id": game.home_team_id,
            "opponent_team_name": game.home_team_name,
            "elo_pre": away_elo,
            **away_form,
            **{f"standings_{key}": value for key, value in away_standings.items()},
            **{f"boxscore_{key}": value for key, value in away_box.items()},
            **{f"player_{key}": value for key, value in away_players.items()},
            **{f"absence_{key}": value for key, value in away_absences.items()},
            **{f"roster_{key}": value for key, value in away_roster.items()},
        }
        snapshot_rows.append({key: value_for_export(value) for key, value in home_snapshot.items()})
        snapshot_rows.append({key: value_for_export(value) for key, value in away_snapshot.items()})

    return game_rows, snapshot_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_summary(path: Path, game_rows: list[dict[str, Any]], snapshot_rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    lines = [
        "# NBA Modeling Export",
        "",
        f"- Generated at: {datetime.now(UTC).isoformat()}",
        f"- Window: {args.start_date} through {args.end_date}",
        f"- Feature history start: {args.history_start_date}",
        f"- Team recent-game lookback: {args.recent_games}",
        f"- Games exported: {len(game_rows)}",
        f"- Team snapshots exported: {len(snapshot_rows)}",
        "",
        "## Included Features",
        "",
        "- Schedule context: venue, attendance, market spread/total, neutral-site flag, conference-game flag",
        "- Team form: win rates, point differential, recent 3/5/N form, home/away splits, rest and schedule density",
        "- Historical context: previous-season win rate when the history window contains prior years",
        "- Standings context: conference/division rank and games back",
        "- Matchup context: recent head-to-head, same-division/conference flags, rivalry flag",
        "- Team boxscore form: possessions, offensive/defensive/net rating, shooting, rebounding, turnovers, pace proxies, paint/fast-break stats",
        "- Player form: top-player and top-rotation scoring/rebounding/assist/minute concentration",
        "- Absence context: last-game inactive counts and estimated production missing",
        "- Current roster context for upcoming games: roster age/size/position mix, injury counts, and projected missing production",
        "- Rating context: pregame Elo for both teams and Elo differential",
        "",
        "## Sample Rows",
        "",
    ]
    for row in game_rows[: min(8, len(game_rows))]:
        lines.append(
            f"- {row['game_date_utc']} | {row['away_team_name']} at {row['home_team_name']} | target_home_team_win={row['target_home_team_win']}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid date: {value}") from exc


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build modeling-ready NBA datasets with schedule, boxscore, player, injury, standings, and historical context."
    )
    today = date.today()
    default_history = (today - timedelta(days=370)).isoformat()
    parser.add_argument("--start-date", default=today.isoformat(), help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", default=today.isoformat(), help="End date in YYYY-MM-DD format.")
    parser.add_argument(
        "--history-start-date",
        default=default_history,
        help="Earlier date for feature history. Use multiple seasons for richer old-season context.",
    )
    parser.add_argument("--recent-games", type=int, default=10, help="Lookback window for recent team/player summaries.")
    parser.add_argument("--output-dir", default="outputs_nba", help="Directory for exported files.")
    parser.add_argument("--force-refresh", action="store_true", help="Ignore cached responses and fetch fresh data.")
    parser.add_argument("--include-rosters", action="store_true", help="Include current roster and injury snapshots for upcoming games.")
    parser.add_argument("--note-file", default="nba_modeling_notes.md", help="Markdown summary filename inside the output directory.")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    start_dt = validate_date(args.start_date)
    end_dt = validate_date(args.end_date)
    history_start = validate_date(args.history_start_date)
    if end_dt < start_dt:
        raise SystemExit("--end-date must be on or after --start-date")
    if history_start > start_dt:
        history_start = start_dt

    client = JsonClient(DEFAULT_CACHE_DIR)
    if args.force_refresh:
        client.ttl = timedelta(seconds=0)

    team_metadata = fetch_teams_metadata(client)
    history_games = fetch_schedule_range(client, history_start, end_dt)
    target_games = [game for game in history_games if start_dt <= game.game_datetime.date() <= end_dt]
    if not target_games:
        target_games = fetch_schedule_range(client, start_dt, end_dt)

    game_rows, snapshot_rows = build_game_feature_rows(
        client=client,
        target_games=target_games,
        history_games=history_games,
        team_metadata=team_metadata,
        recent_games=args.recent_games,
        include_rosters=args.include_rosters,
    )

    output_dir = Path(args.output_dir)
    games_csv = output_dir / "nba_game_features.csv"
    snapshots_csv = output_dir / "nba_team_snapshots.csv"
    notes_md = output_dir / args.note_file

    write_csv(games_csv, game_rows)
    write_csv(snapshots_csv, snapshot_rows)
    write_markdown_summary(notes_md, game_rows, snapshot_rows, args)

    print(f"Wrote {len(game_rows)} game rows to {games_csv}")
    print(f"Wrote {len(snapshot_rows)} snapshot rows to {snapshots_csv}")
    print(f"Wrote markdown notes to {notes_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
