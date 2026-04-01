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


MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_CACHE_DIR = Path(".cache") / "mlb_model_builder"
REQUEST_HEADERS = {
    "User-Agent": "mlb-model-builder/1.0",
    "Accept": "application/json",
}


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def safe_float(value: Any) -> float | None:
    if value in (None, "", "-.--", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def innings_to_float(value: Any) -> float:
    if value in (None, "", "--"):
        return 0.0
    text = str(value)
    if "." not in text:
        return safe_float(text) or 0.0
    whole, frac = text.split(".", 1)
    outs = int(frac) if frac.isdigit() else 0
    return (safe_float(whole) or 0.0) + (outs / 3.0)


class JsonClient:
    def __init__(self, cache_dir: Path, ttl_hours: float = 6.0, pause_seconds: float = 0.15) -> None:
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
            with urlopen(request, timeout=45) as response:
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
    game_pk: int
    game_datetime: datetime
    status: str
    venue_id: int | None
    venue_name: str
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    home_score: int | None
    away_score: int | None
    home_probable_pitcher_id: int | None
    home_probable_pitcher_name: str | None
    away_probable_pitcher_id: int | None
    away_probable_pitcher_name: str | None
    doubleheader: str | None = None

    @property
    def is_final(self) -> bool:
        return self.status.lower() in {"final", "game over", "completed early", "completed"}


def flatten_schedule(schedule_payload: dict[str, Any]) -> list[GameRow]:
    rows: list[GameRow] = []
    for date_block in schedule_payload.get("dates", []):
        for game in date_block.get("games", []):
            teams = game.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            venue = game.get("venue", {}) or {}
            home_probable = home.get("probablePitcher") or {}
            away_probable = away.get("probablePitcher") or {}
            rows.append(
                GameRow(
                    game_pk=int(game["gamePk"]),
                    game_datetime=parse_iso_datetime(game["gameDate"]),
                    status=game.get("status", {}).get("detailedState", "Unknown"),
                    venue_id=venue.get("id"),
                    venue_name=venue.get("name", "Unknown"),
                    home_team_id=int(home["team"]["id"]),
                    home_team_name=home["team"]["name"],
                    away_team_id=int(away["team"]["id"]),
                    away_team_name=away["team"]["name"],
                    home_score=home.get("score"),
                    away_score=away.get("score"),
                    home_probable_pitcher_id=home_probable.get("id"),
                    home_probable_pitcher_name=home_probable.get("fullName"),
                    away_probable_pitcher_id=away_probable.get("id"),
                    away_probable_pitcher_name=away_probable.get("fullName"),
                    doubleheader=game.get("doubleHeader"),
                )
            )
    return sorted(rows, key=lambda row: row.game_datetime)


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def pct(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def season_from_date(target: date) -> int:
    return target.year


def season_start(target_season: int) -> date:
    return date(target_season, 3, 1)


def current_season_games(team_logs: list[dict[str, Any]], before_dt: datetime) -> list[dict[str, Any]]:
    season_open = season_start(before_dt.date().year)
    return [game for game in team_logs if season_open <= game["game_datetime"].date() < before_dt.date()]


def previous_season_games(team_logs: list[dict[str, Any]], before_dt: datetime) -> list[dict[str, Any]]:
    current_open = season_start(before_dt.date().year)
    previous_open = season_start(before_dt.date().year - 1)
    return [game for game in team_logs if previous_open <= game["game_datetime"].date() < current_open]


def carryover_weight(current_games_played: int, max_weight: float = 0.35, fade_games: int = 20) -> float:
    progress = min(current_games_played / fade_games, 1.0)
    return max_weight * (1.0 - progress)


def weighted_mean_pair(current_value: float | None, prior_value: float | None, prior_weight: float) -> float | None:
    if current_value is None and prior_value is None:
        return None
    if current_value is None:
        return prior_value
    if prior_value is None or prior_weight <= 0:
        return current_value
    return ((1.0 - prior_weight) * current_value) + (prior_weight * prior_value)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def normalize_result(game: GameRow, team_id: int) -> dict[str, Any]:
    is_home = game.home_team_id == team_id
    team_score = game.home_score if is_home else game.away_score
    opp_score = game.away_score if is_home else game.home_score
    opponent_id = game.away_team_id if is_home else game.home_team_id
    opponent_name = game.away_team_name if is_home else game.home_team_name
    if team_score is None or opp_score is None:
        won = None
        margin = None
    else:
        won = team_score > opp_score
        margin = team_score - opp_score
    return {
        "game_pk": game.game_pk,
        "game_datetime": game.game_datetime,
        "team_id": team_id,
        "opponent_id": opponent_id,
        "opponent_name": opponent_name,
        "is_home": is_home,
        "venue_id": game.venue_id,
        "doubleheader": game.doubleheader,
        "runs_scored": team_score,
        "runs_allowed": opp_score,
        "won": won,
        "margin": margin,
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


def get_team_metadata(client: JsonClient, season: int) -> dict[int, dict[str, Any]]:
    payload = client.get_json(
        f"{MLB_API_BASE}/teams",
        {
            "sportId": 1,
            "season": season,
        },
    )
    metadata: dict[int, dict[str, Any]] = {}
    for team in payload.get("teams", []):
        metadata[int(team["id"])] = {
            "team_name": team.get("name"),
            "abbreviation": team.get("abbreviation"),
            "league_id": (team.get("league") or {}).get("id"),
            "division_id": (team.get("division") or {}).get("id"),
            "venue_id": (team.get("venue") or {}).get("id"),
        }
    return metadata


def build_standings_snapshot(
    team_history: dict[int, list[dict[str, Any]]],
    before_dt: datetime,
    team_metadata: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    standings: dict[int, dict[str, Any]] = {}
    for team_id, logs in team_history.items():
        current = current_season_games(logs, before_dt)
        previous = previous_season_games(logs, before_dt)
        prior_weight = carryover_weight(len(current))
        current_wins = sum(1 for game in current if game["won"] is True)
        current_losses = sum(1 for game in current if game["won"] is False)
        previous_wins = sum(1 for game in previous if game["won"] is True)
        previous_losses = sum(1 for game in previous if game["won"] is False)
        wins = current_wins + (prior_weight * previous_wins)
        losses = current_losses + (prior_weight * previous_losses)
        current_runs_scored = sum(int(game["runs_scored"]) for game in current if game["runs_scored"] is not None)
        current_runs_allowed = sum(int(game["runs_allowed"]) for game in current if game["runs_allowed"] is not None)
        previous_runs_scored = sum(int(game["runs_scored"]) for game in previous if game["runs_scored"] is not None)
        previous_runs_allowed = sum(int(game["runs_allowed"]) for game in previous if game["runs_allowed"] is not None)
        runs_scored = current_runs_scored + (prior_weight * previous_runs_scored)
        runs_allowed = current_runs_allowed + (prior_weight * previous_runs_allowed)
        win_pct = pct(wins, wins + losses) or 0.0
        pythag = None
        if runs_scored > 0 or runs_allowed > 0:
            rs_exp = runs_scored ** 2
            ra_exp = runs_allowed ** 2
            pythag = rs_exp / (rs_exp + ra_exp) if (rs_exp + ra_exp) else None
        standings[team_id] = {
            "wins": wins,
            "losses": losses,
            "games_played": wins + losses,
            "win_pct": win_pct,
            "run_diff": runs_scored - runs_allowed,
            "pythag_win_pct": pythag,
            "carryover_weight": prior_weight,
            "league_id": team_metadata.get(team_id, {}).get("league_id"),
            "division_id": team_metadata.get(team_id, {}).get("division_id"),
        }

    league_groups: dict[int | None, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    division_groups: dict[int | None, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for team_id, row in standings.items():
        league_groups[row["league_id"]].append((team_id, row))
        division_groups[row["division_id"]].append((team_id, row))

    for group in league_groups.values():
        group.sort(key=lambda item: (item[1]["win_pct"], item[1]["run_diff"]), reverse=True)
        leader_wins = group[0][1]["wins"] if group else 0
        leader_losses = group[0][1]["losses"] if group else 0
        for rank, (team_id, row) in enumerate(group, start=1):
            games_back = ((leader_wins - row["wins"]) + (row["losses"] - leader_losses)) / 2.0
            standings[team_id]["league_rank"] = rank
            standings[team_id]["league_games_back"] = games_back

    for group in division_groups.values():
        group.sort(key=lambda item: (item[1]["win_pct"], item[1]["run_diff"]), reverse=True)
        leader_wins = group[0][1]["wins"] if group else 0
        leader_losses = group[0][1]["losses"] if group else 0
        for rank, (team_id, row) in enumerate(group, start=1):
            games_back = ((leader_wins - row["wins"]) + (row["losses"] - leader_losses)) / 2.0
            standings[team_id]["division_rank"] = rank
            standings[team_id]["division_games_back"] = games_back

    return standings


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


def summarize_team_form(
    team_logs: list[dict[str, Any]],
    before_dt: datetime,
    recent_games: int,
    current_venue_id: int | None,
    venue_coords: dict[int, tuple[float | None, float | None]],
) -> dict[str, Any]:
    prior = current_season_games(team_logs, before_dt)
    previous = previous_season_games(team_logs, before_dt)
    prior_weight = carryover_weight(len(prior))
    recent = prior[-recent_games:]
    previous_recent = previous[-recent_games:]
    recent_3 = prior[-3:]
    previous_recent_3 = previous[-3:]
    recent_5 = prior[-5:]
    previous_recent_5 = previous[-5:]
    season_wins = sum(1 for game in prior if game["won"] is True)
    season_losses = sum(1 for game in prior if game["won"] is False)
    previous_wins = sum(1 for game in previous if game["won"] is True)
    previous_losses = sum(1 for game in previous if game["won"] is False)
    recent_wins = sum(1 for game in recent if game["won"] is True)
    previous_recent_wins = sum(1 for game in previous_recent if game["won"] is True)
    home_games = [game for game in prior if game["is_home"]]
    previous_home_games = [game for game in previous if game["is_home"]]
    away_games = [game for game in prior if not game["is_home"]]
    previous_away_games = [game for game in previous if not game["is_home"]]
    one_run_games = [game for game in prior if game["margin"] is not None and abs(game["margin"]) == 1]
    previous_one_run_games = [game for game in previous if game["margin"] is not None and abs(game["margin"]) == 1]
    last_game = prior[-1] if prior else None
    rest_days = None
    travel_distance_km = None
    played_yesterday = None
    games_last_7_days = 0
    if last_game:
        rest_days = max((before_dt.date() - last_game["game_datetime"].date()).days - 1, 0)
        played_yesterday = int((before_dt.date() - last_game["game_datetime"].date()).days == 1)
        if current_venue_id is not None and last_game.get("venue_id") is not None:
            current_coords = venue_coords.get(current_venue_id)
            previous_coords = venue_coords.get(last_game["venue_id"])
            if current_coords and previous_coords and None not in current_coords and None not in previous_coords:
                travel_distance_km = haversine_km(
                    current_coords[0],
                    current_coords[1],
                    previous_coords[0],
                    previous_coords[1],
                )
    week_ago = before_dt - timedelta(days=7)
    games_last_7_days = sum(1 for game in prior if game["game_datetime"] >= week_ago)

    season_runs_scored = sum(float(game["runs_scored"]) for game in prior if game["runs_scored"] is not None)
    season_runs_allowed = sum(float(game["runs_allowed"]) for game in prior if game["runs_allowed"] is not None)
    previous_runs_scored = sum(float(game["runs_scored"]) for game in previous if game["runs_scored"] is not None)
    previous_runs_allowed = sum(float(game["runs_allowed"]) for game in previous if game["runs_allowed"] is not None)
    blended_runs_scored = season_runs_scored + (prior_weight * previous_runs_scored)
    blended_runs_allowed = season_runs_allowed + (prior_weight * previous_runs_allowed)
    pythag_win_pct = None
    if blended_runs_scored > 0 or blended_runs_allowed > 0:
        rs_exp = blended_runs_scored ** 2
        ra_exp = blended_runs_allowed ** 2
        pythag_win_pct = rs_exp / (rs_exp + ra_exp) if (rs_exp + ra_exp) else None

    return {
        "games_played": len(prior) + (prior_weight * len(previous)),
        "wins": season_wins + (prior_weight * previous_wins),
        "losses": season_losses + (prior_weight * previous_losses),
        "win_pct": weighted_mean_pair(
            pct(season_wins, season_wins + season_losses),
            pct(previous_wins, previous_wins + previous_losses),
            prior_weight,
        ),
        "runs_scored_avg": weighted_mean_pair(
            mean([float(game["runs_scored"]) for game in prior if game["runs_scored"] is not None]),
            mean([float(game["runs_scored"]) for game in previous if game["runs_scored"] is not None]),
            prior_weight,
        ),
        "runs_allowed_avg": weighted_mean_pair(
            mean([float(game["runs_allowed"]) for game in prior if game["runs_allowed"] is not None]),
            mean([float(game["runs_allowed"]) for game in previous if game["runs_allowed"] is not None]),
            prior_weight,
        ),
        "run_diff_avg": weighted_mean_pair(
            mean([float(game["margin"]) for game in prior if game["margin"] is not None]),
            mean([float(game["margin"]) for game in previous if game["margin"] is not None]),
            prior_weight,
        ),
        "recent_games": len(recent) + (prior_weight * len(previous_recent)),
        "recent_win_pct": weighted_mean_pair(
            pct(recent_wins, len(recent)),
            pct(previous_recent_wins, len(previous_recent)),
            prior_weight,
        ),
        "recent_runs_scored_avg": weighted_mean_pair(
            mean([float(game["runs_scored"]) for game in recent if game["runs_scored"] is not None]),
            mean([float(game["runs_scored"]) for game in previous_recent if game["runs_scored"] is not None]),
            prior_weight,
        ),
        "recent_runs_allowed_avg": weighted_mean_pair(
            mean([float(game["runs_allowed"]) for game in recent if game["runs_allowed"] is not None]),
            mean([float(game["runs_allowed"]) for game in previous_recent if game["runs_allowed"] is not None]),
            prior_weight,
        ),
        "recent_run_diff_avg": weighted_mean_pair(
            mean([float(game["margin"]) for game in recent if game["margin"] is not None]),
            mean([float(game["margin"]) for game in previous_recent if game["margin"] is not None]),
            prior_weight,
        ),
        "streak": compute_streak(prior) if prior else (compute_streak(previous) * prior_weight if previous else None),
        "home_win_pct": weighted_mean_pair(
            pct(sum(1 for game in home_games if game["won"] is True), len(home_games)),
            pct(sum(1 for game in previous_home_games if game["won"] is True), len(previous_home_games)),
            prior_weight,
        ),
        "away_win_pct": weighted_mean_pair(
            pct(sum(1 for game in away_games if game["won"] is True), len(away_games)),
            pct(sum(1 for game in previous_away_games if game["won"] is True), len(previous_away_games)),
            prior_weight,
        ),
        "home_runs_scored_avg": weighted_mean_pair(
            mean([float(game["runs_scored"]) for game in home_games if game["runs_scored"] is not None]),
            mean([float(game["runs_scored"]) for game in previous_home_games if game["runs_scored"] is not None]),
            prior_weight,
        ),
        "home_runs_allowed_avg": weighted_mean_pair(
            mean([float(game["runs_allowed"]) for game in home_games if game["runs_allowed"] is not None]),
            mean([float(game["runs_allowed"]) for game in previous_home_games if game["runs_allowed"] is not None]),
            prior_weight,
        ),
        "away_runs_scored_avg": weighted_mean_pair(
            mean([float(game["runs_scored"]) for game in away_games if game["runs_scored"] is not None]),
            mean([float(game["runs_scored"]) for game in previous_away_games if game["runs_scored"] is not None]),
            prior_weight,
        ),
        "away_runs_allowed_avg": weighted_mean_pair(
            mean([float(game["runs_allowed"]) for game in away_games if game["runs_allowed"] is not None]),
            mean([float(game["runs_allowed"]) for game in previous_away_games if game["runs_allowed"] is not None]),
            prior_weight,
        ),
        "one_run_win_pct": weighted_mean_pair(
            pct(sum(1 for game in one_run_games if game["won"] is True), len(one_run_games)),
            pct(sum(1 for game in previous_one_run_games if game["won"] is True), len(previous_one_run_games)),
            prior_weight,
        ),
        "recent3_win_pct": weighted_mean_pair(
            pct(sum(1 for game in recent_3 if game["won"] is True), len(recent_3)),
            pct(sum(1 for game in previous_recent_3 if game["won"] is True), len(previous_recent_3)),
            prior_weight,
        ),
        "recent5_win_pct": weighted_mean_pair(
            pct(sum(1 for game in recent_5 if game["won"] is True), len(recent_5)),
            pct(sum(1 for game in previous_recent_5 if game["won"] is True), len(previous_recent_5)),
            prior_weight,
        ),
        "recent3_runs_scored_avg": weighted_mean_pair(
            mean([float(game["runs_scored"]) for game in recent_3 if game["runs_scored"] is not None]),
            mean([float(game["runs_scored"]) for game in previous_recent_3 if game["runs_scored"] is not None]),
            prior_weight,
        ),
        "recent3_runs_allowed_avg": weighted_mean_pair(
            mean([float(game["runs_allowed"]) for game in recent_3 if game["runs_allowed"] is not None]),
            mean([float(game["runs_allowed"]) for game in previous_recent_3 if game["runs_allowed"] is not None]),
            prior_weight,
        ),
        "recent5_runs_scored_avg": weighted_mean_pair(
            mean([float(game["runs_scored"]) for game in recent_5 if game["runs_scored"] is not None]),
            mean([float(game["runs_scored"]) for game in previous_recent_5 if game["runs_scored"] is not None]),
            prior_weight,
        ),
        "recent5_runs_allowed_avg": weighted_mean_pair(
            mean([float(game["runs_allowed"]) for game in recent_5 if game["runs_allowed"] is not None]),
            mean([float(game["runs_allowed"]) for game in previous_recent_5 if game["runs_allowed"] is not None]),
            prior_weight,
        ),
        "pythag_win_pct": pythag_win_pct,
        "carryover_weight": prior_weight,
        "rest_days": rest_days,
        "played_yesterday": played_yesterday,
        "games_last_7_days": games_last_7_days,
        "travel_distance_km": travel_distance_km,
        "last_game_was_home": last_game["is_home"] if last_game else None,
        "last_game_margin": last_game["margin"] if last_game else None,
        "last_game_runs_scored": last_game["runs_scored"] if last_game else None,
        "last_game_runs_allowed": last_game["runs_allowed"] if last_game else None,
        "last_game_won": last_game["won"] if last_game else None,
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
    home_team_wins = 0
    home_team_run_diffs: list[float] = []
    for game in recent:
        if game.home_score is None or game.away_score is None:
            continue
        if game.home_team_id == home_team_id:
            run_diff = float(game.home_score - game.away_score)
            home_team_wins += int(game.home_score > game.away_score)
        else:
            run_diff = float(game.away_score - game.home_score)
            home_team_wins += int(game.away_score > game.home_score)
        home_team_run_diffs.append(run_diff)

    last_meeting_home_team_won = None
    if recent:
        last_game = recent[-1]
        if last_game.home_score is not None and last_game.away_score is not None:
            if last_game.home_team_id == home_team_id:
                last_meeting_home_team_won = last_game.home_score > last_game.away_score
            else:
                last_meeting_home_team_won = last_game.away_score > last_game.home_score

    return {
        "games": len(prior),
        "recent_games": len(recent),
        "home_team_recent_win_pct": pct(home_team_wins, len(recent)),
        "home_team_recent_run_diff_avg": mean(home_team_run_diffs),
        "last_meeting_home_team_won": last_meeting_home_team_won,
    }


def extract_pitching_stats(split: dict[str, Any]) -> dict[str, float | None]:
    stat = split.get("stat", {})
    innings_pitched = innings_to_float(stat.get("inningsPitched"))
    earned_runs = safe_float(stat.get("earnedRuns")) or 0.0
    hits = safe_float(stat.get("hits")) or 0.0
    walks = safe_float(stat.get("baseOnBalls")) or 0.0
    strikeouts = safe_float(stat.get("strikeOuts")) or 0.0
    home_runs = safe_float(stat.get("homeRuns")) or 0.0
    pitches = safe_float(stat.get("numberOfPitches"))
    batters_faced = safe_float(stat.get("battersFaced"))
    if innings_pitched > 0:
        era = (earned_runs * 9.0) / innings_pitched
        whip = (walks + hits) / innings_pitched
        k_per_9 = (strikeouts * 9.0) / innings_pitched
        bb_per_9 = (walks * 9.0) / innings_pitched
        hr_per_9 = (home_runs * 9.0) / innings_pitched
    else:
        era = None
        whip = None
        k_per_9 = None
        bb_per_9 = None
        hr_per_9 = None
    return {
        "innings_pitched": innings_pitched,
        "earned_runs": earned_runs,
        "hits": hits,
        "walks": walks,
        "strikeouts": strikeouts,
        "home_runs": home_runs,
        "pitches": pitches,
        "batters_faced": batters_faced,
        "era": era,
        "whip": whip,
        "k_per_9": k_per_9,
        "bb_per_9": bb_per_9,
        "hr_per_9": hr_per_9,
    }


def summarize_pitcher_logs(
    splits: list[dict[str, Any]],
    before_dt: datetime,
    recent_games: int,
) -> dict[str, Any]:
    parsed: list[tuple[datetime, dict[str, float | None], dict[str, Any]]] = []
    for split in splits:
        stat_date = split.get("date")
        if not stat_date:
            continue
        dt = datetime.fromisoformat(f"{stat_date}T00:00:00+00:00")
        if dt >= before_dt:
            continue
        stats = extract_pitching_stats(split)
        parsed.append((dt, stats, split))
    parsed.sort(key=lambda item: item[0])
    recent = parsed[-recent_games:]
    season = parsed

    total_ip = sum(item[1]["innings_pitched"] or 0.0 for item in recent)
    total_er = sum(item[1]["earned_runs"] or 0.0 for item in recent)
    total_hits = sum(item[1]["hits"] or 0.0 for item in recent)
    total_walks = sum(item[1]["walks"] or 0.0 for item in recent)
    total_so = sum(item[1]["strikeouts"] or 0.0 for item in recent)
    total_hr = sum(item[1]["home_runs"] or 0.0 for item in recent)
    total_pitches = sum(item[1]["pitches"] or 0.0 for item in recent)
    total_bf = sum(item[1]["batters_faced"] or 0.0 for item in recent)
    season_ip = sum(item[1]["innings_pitched"] or 0.0 for item in season)
    season_er = sum(item[1]["earned_runs"] or 0.0 for item in season)
    season_hits = sum(item[1]["hits"] or 0.0 for item in season)
    season_walks = sum(item[1]["walks"] or 0.0 for item in season)
    season_so = sum(item[1]["strikeouts"] or 0.0 for item in season)
    season_hr = sum(item[1]["home_runs"] or 0.0 for item in season)

    season_era = (season_er * 9.0 / season_ip) if season_ip else None
    season_whip = ((season_hits + season_walks) / season_ip) if season_ip else None
    season_k_per_9 = (season_so * 9.0 / season_ip) if season_ip else None
    season_bb_per_9 = (season_walks * 9.0 / season_ip) if season_ip else None
    season_hr_per_9 = (season_hr * 9.0 / season_ip) if season_ip else None

    last_appearance = recent[-1] if recent else None
    days_since_last_appearance = None
    if last_appearance:
        days_since_last_appearance = max((before_dt.date() - last_appearance[0].date()).days, 0)

    era = (total_er * 9.0 / total_ip) if total_ip else None
    whip = ((total_hits + total_walks) / total_ip) if total_ip else None
    k_per_9 = (total_so * 9.0 / total_ip) if total_ip else None
    bb_per_9 = (total_walks * 9.0 / total_ip) if total_ip else None
    hr_per_9 = (total_hr * 9.0 / total_ip) if total_ip else None

    return {
        "recent_appearances": len(recent),
        "recent_innings_pitched": total_ip or None,
        "recent_era": era,
        "recent_whip": whip,
        "recent_k_per_9": k_per_9,
        "recent_bb_per_9": bb_per_9,
        "recent_hr_per_9": hr_per_9,
        "recent_strikeouts": total_so or None,
        "recent_walks": total_walks or None,
        "recent_hits_allowed": total_hits or None,
        "recent_pitches": total_pitches or None,
        "recent_batters_faced": total_bf or None,
        "season_appearances": len(season),
        "season_innings_pitched": season_ip or None,
        "season_era": season_era,
        "season_whip": season_whip,
        "season_k_per_9": season_k_per_9,
        "season_bb_per_9": season_bb_per_9,
        "season_hr_per_9": season_hr_per_9,
        "days_since_last_appearance": days_since_last_appearance,
        "last_appearance_innings_pitched": last_appearance[1]["innings_pitched"] if last_appearance else None,
        "last_appearance_earned_runs": last_appearance[1]["earned_runs"] if last_appearance else None,
        "last_appearance_hits": last_appearance[1]["hits"] if last_appearance else None,
        "last_appearance_walks": last_appearance[1]["walks"] if last_appearance else None,
        "last_appearance_strikeouts": last_appearance[1]["strikeouts"] if last_appearance else None,
        "last_appearance_pitches": last_appearance[1]["pitches"] if last_appearance else None,
    }


def value_for_export(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 4)
    if isinstance(value, bool):
        return int(value)
    return value


def get_pitcher_log_splits(client: JsonClient, pitcher_id: int, season: int) -> list[dict[str, Any]]:
    payload = client.get_json(
        f"{MLB_API_BASE}/people/{pitcher_id}/stats",
        {
            "stats": "gameLog",
            "group": "pitching",
            "season": season,
            "gameType": "R",
        },
    )
    stats_blocks = payload.get("stats", [])
    if not stats_blocks:
        return []
    return stats_blocks[0].get("splits", [])


def get_venue_coordinates(
    client: JsonClient,
    venue_id: int | None,
    venue_coords_cache: dict[int, tuple[float | None, float | None]],
) -> tuple[float | None, float | None]:
    if venue_id is None:
        return None, None
    if venue_id in venue_coords_cache:
        return venue_coords_cache[venue_id]
    payload = client.get_json(f"{MLB_API_BASE}/venues/{venue_id}")
    venues = payload.get("venues", [])
    if not venues:
        return None, None
    location = venues[0].get("location", {})
    coords = location.get("defaultCoordinates", {})
    latitude = safe_float(coords.get("latitude"))
    longitude = safe_float(coords.get("longitude"))
    venue_coords_cache[venue_id] = (latitude, longitude)
    return latitude, longitude


def get_boxscore(client: JsonClient, game_pk: int) -> dict[str, Any]:
    return client.get_json(f"{MLB_API_BASE}/game/{game_pk}/boxscore")


def summarize_bullpen_usage(
    client: JsonClient,
    team_logs: list[dict[str, Any]],
    team_id: int,
    before_dt: datetime,
    recent_games: int,
    boxscore_cache: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    prior = current_season_games(team_logs, before_dt)
    previous = previous_season_games(team_logs, before_dt)
    prior_weight = carryover_weight(len(prior))
    recent = prior[-recent_games:]
    previous_recent = previous[-recent_games:]
    total_ip = 0.0
    total_er = 0.0
    total_hits = 0.0
    total_walks = 0.0
    total_so = 0.0
    total_pitches = 0.0
    relievers_used = 0
    games_with_relief = 0

    def accumulate(games: list[dict[str, Any]], weight: float) -> tuple[float, float, float, float, float, float, float, float]:
        local_ip = 0.0
        local_er = 0.0
        local_hits = 0.0
        local_walks = 0.0
        local_so = 0.0
        local_pitches = 0.0
        local_relievers = 0.0
        local_games_relief = 0.0
        for game in games:
            try:
                payload = boxscore_cache.setdefault(game["game_pk"], get_boxscore(client, game["game_pk"]))
            except RuntimeError:
                continue
            teams = payload.get("teams", {})
            side = "home" if teams.get("home", {}).get("team", {}).get("id") == team_id else "away"
            team_box = teams.get(side, {})
            pitchers = team_box.get("pitchers", []) or []
            players = team_box.get("players", {}) or {}
            relief_pitchers = pitchers[1:] if len(pitchers) > 1 else []
            if relief_pitchers:
                local_games_relief += weight
            for pitcher_id in relief_pitchers:
                player = players.get(f"ID{pitcher_id}", {})
                stat = (player.get("stats") or {}).get("pitching", {})
                local_ip += weight * innings_to_float(stat.get("inningsPitched"))
                local_er += weight * (safe_float(stat.get("earnedRuns")) or 0.0)
                local_hits += weight * (safe_float(stat.get("hits")) or 0.0)
                local_walks += weight * (safe_float(stat.get("baseOnBalls")) or 0.0)
                local_so += weight * (safe_float(stat.get("strikeOuts")) or 0.0)
                local_pitches += weight * (safe_float(stat.get("numberOfPitches")) or 0.0)
                local_relievers += weight
        return local_ip, local_er, local_hits, local_walks, local_so, local_pitches, local_relievers, local_games_relief

    current_totals = accumulate(recent, 1.0)
    previous_totals = accumulate(previous_recent, prior_weight)
    total_ip = current_totals[0] + previous_totals[0]
    total_er = current_totals[1] + previous_totals[1]
    total_hits = current_totals[2] + previous_totals[2]
    total_walks = current_totals[3] + previous_totals[3]
    total_so = current_totals[4] + previous_totals[4]
    total_pitches = current_totals[5] + previous_totals[5]
    relievers_used = current_totals[6] + previous_totals[6]
    games_with_relief = current_totals[7] + previous_totals[7]

    bullpen_era = (total_er * 9.0 / total_ip) if total_ip else None
    bullpen_whip = ((total_hits + total_walks) / total_ip) if total_ip else None
    bullpen_k_per_9 = (total_so * 9.0 / total_ip) if total_ip else None
    return {
        "recent_games": len(recent) + (prior_weight * len(previous_recent)),
        "games_with_relief": games_with_relief,
        "relievers_used": relievers_used,
        "innings_pitched": total_ip or None,
        "era": bullpen_era,
        "whip": bullpen_whip,
        "k_per_9": bullpen_k_per_9,
        "pitches": total_pitches or None,
        "avg_relievers_per_game": (
            relievers_used / (len(recent) + (prior_weight * len(previous_recent)))
            if (len(recent) + (prior_weight * len(previous_recent))) > 0
            else None
        ),
        "carryover_weight": prior_weight,
    }


def extract_team_game_boxscore(
    client: JsonClient,
    game_pk: int,
    team_id: int,
    boxscore_cache: dict[int, dict[str, Any]],
) -> dict[str, float | None]:
    payload = boxscore_cache.setdefault(game_pk, get_boxscore(client, game_pk))
    teams = payload.get("teams", {})
    side = "home" if teams.get("home", {}).get("team", {}).get("id") == team_id else "away"
    team_box = teams.get(side, {})
    batting = (team_box.get("teamStats") or {}).get("batting", {}) or {}
    pitching = (team_box.get("teamStats") or {}).get("pitching", {}) or {}
    fielding = (team_box.get("teamStats") or {}).get("fielding", {}) or {}
    doubles = safe_float(batting.get("doubles")) or 0.0
    triples = safe_float(batting.get("triples")) or 0.0
    home_runs = safe_float(batting.get("homeRuns")) or 0.0
    hits = safe_float(batting.get("hits")) or 0.0
    at_bats = safe_float(batting.get("atBats")) or 0.0
    walks = safe_float(batting.get("baseOnBalls")) or 0.0
    singles = max(hits - doubles - triples - home_runs, 0.0)
    total_bases = singles + (2.0 * doubles) + (3.0 * triples) + (4.0 * home_runs)
    obp_proxy = ((hits + walks) / (at_bats + walks)) if (at_bats + walks) else None
    slg_proxy = (total_bases / at_bats) if at_bats else None
    return {
        "batting_runs": safe_float(batting.get("runs")),
        "batting_hits": hits,
        "batting_walks": walks,
        "batting_strikeouts": safe_float(batting.get("strikeOuts")),
        "batting_home_runs": home_runs,
        "batting_doubles": doubles,
        "batting_triples": triples,
        "batting_stolen_bases": safe_float(batting.get("stolenBases")),
        "batting_left_on_base": safe_float(batting.get("leftOnBase")),
        "batting_at_bats": at_bats,
        "batting_obp_proxy": obp_proxy,
        "batting_slg_proxy": slg_proxy,
        "pitching_runs_allowed": safe_float(pitching.get("runs")),
        "pitching_hits_allowed": safe_float(pitching.get("hits")),
        "pitching_walks_allowed": safe_float(pitching.get("baseOnBalls")),
        "pitching_strikeouts": safe_float(pitching.get("strikeOuts")),
        "pitching_home_runs_allowed": safe_float(pitching.get("homeRuns")),
        "fielding_errors": safe_float(fielding.get("errors")),
    }


def summarize_team_boxscore_form(
    client: JsonClient,
    team_logs: list[dict[str, Any]],
    team_id: int,
    before_dt: datetime,
    recent_games: int,
    boxscore_cache: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    prior = current_season_games(team_logs, before_dt)
    previous = previous_season_games(team_logs, before_dt)
    prior_weight = carryover_weight(len(prior))
    recent = prior[-recent_games:]
    previous_recent = previous[-recent_games:]
    stat_rows: list[dict[str, float | None]] = []
    for game in recent:
        try:
            stat_rows.append(extract_team_game_boxscore(client, game["game_pk"], team_id, boxscore_cache))
        except RuntimeError:
            continue
    previous_stat_rows: list[dict[str, float | None]] = []
    for game in previous_recent:
        try:
            previous_stat_rows.append(extract_team_game_boxscore(client, game["game_pk"], team_id, boxscore_cache))
        except RuntimeError:
            continue
    summary: dict[str, Any] = {"recent_games": len(recent) + (prior_weight * len(previous_recent)), "carryover_weight": prior_weight}
    keys = [
        "batting_runs",
        "batting_hits",
        "batting_walks",
        "batting_strikeouts",
        "batting_home_runs",
        "batting_doubles",
        "batting_triples",
        "batting_stolen_bases",
        "batting_left_on_base",
        "batting_at_bats",
        "batting_obp_proxy",
        "batting_slg_proxy",
        "pitching_runs_allowed",
        "pitching_hits_allowed",
        "pitching_walks_allowed",
        "pitching_strikeouts",
        "pitching_home_runs_allowed",
        "fielding_errors",
    ]
    for key in keys:
        summary[f"{key}_avg"] = weighted_mean_pair(
            mean([float(row[key]) for row in stat_rows if row.get(key) is not None]),
            mean([float(row[key]) for row in previous_stat_rows if row.get(key) is not None]),
            prior_weight,
        )
    return summary


def get_pitcher_profile(client: JsonClient, pitcher_id: int) -> dict[str, Any]:
    payload = client.get_json(f"{MLB_API_BASE}/people/{pitcher_id}")
    people = payload.get("people", [])
    if not people:
        return {}
    person = people[0]
    birth_date = person.get("birthDate")
    age = None
    if birth_date:
        born = date.fromisoformat(birth_date)
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    throwing_hand = ((person.get("pitchHand") or {}).get("code") or "").upper()
    batting_side = ((person.get("batSide") or {}).get("code") or "").upper()
    return {
        "age": age,
        "height_inches": _height_to_inches(person.get("height")),
        "weight_lbs": safe_float(person.get("weight")),
        "throws_right": int(throwing_hand == "R") if throwing_hand else None,
        "throws_left": int(throwing_hand == "L") if throwing_hand else None,
        "bats_right": int(batting_side == "R") if batting_side else None,
        "bats_left": int(batting_side == "L") if batting_side else None,
    }


def _height_to_inches(height_text: Any) -> float | None:
    if not height_text or not isinstance(height_text, str) or "'" not in height_text:
        return None
    feet_text, inches_text = height_text.replace('"', "").split("'", 1)
    feet = safe_float(feet_text.strip())
    inches = safe_float(inches_text.strip())
    if feet is None:
        return None
    return (feet * 12.0) + (inches or 0.0)


def get_weather_snapshot(
    client: JsonClient,
    when: datetime,
    venue_id: int | None,
    venue_coords_cache: dict[int, tuple[float | None, float | None]],
) -> dict[str, Any]:
    latitude, longitude = get_venue_coordinates(client, venue_id, venue_coords_cache)
    if latitude is None or longitude is None:
        return {}

    target_date = when.date().isoformat()
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_gusts_10m,pressure_msl",
        "timezone": "GMT",
        "start_date": target_date,
        "end_date": target_date,
    }
    url = OPEN_METEO_ARCHIVE_URL if when.date() < date.today() else OPEN_METEO_FORECAST_URL
    payload = client.get_json(url, params)
    hourly = payload.get("hourly", {})
    timestamps = hourly.get("time", [])
    if not timestamps:
        return {}

    target_hour = when.replace(minute=0, second=0, microsecond=0)
    best_index = 0
    best_delta = None
    for index, timestamp in enumerate(timestamps):
        hour_dt = datetime.fromisoformat(f"{timestamp}+00:00").astimezone(UTC)
        delta = abs((hour_dt - target_hour).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_index = index

    def pick(key: str) -> Any:
        values = hourly.get(key, [])
        return values[best_index] if best_index < len(values) else None

    return {
        "weather_temperature_c": pick("temperature_2m"),
        "weather_relative_humidity": pick("relative_humidity_2m"),
        "weather_precipitation_mm": pick("precipitation"),
        "weather_wind_speed_kmh": pick("wind_speed_10m"),
        "weather_wind_gust_kmh": pick("wind_gusts_10m"),
        "weather_pressure_hpa": pick("pressure_msl"),
    }


def fetch_schedule(
    client: JsonClient,
    start_dt: date,
    end_dt: date,
    season: int | None = None,
) -> list[GameRow]:
    params = {
        "sportId": 1,
        "startDate": start_dt.isoformat(),
        "endDate": end_dt.isoformat(),
        "gameType": "R",
        "hydrate": "probablePitcher,venue",
    }
    if season is not None:
        params["season"] = season
    payload = client.get_json(f"{MLB_API_BASE}/schedule", params)
    return flatten_schedule(payload)


def build_game_feature_rows(
    client: JsonClient,
    target_games: list[GameRow],
    history_games: list[GameRow],
    team_metadata: dict[int, dict[str, Any]],
    recent_games: int,
    pitcher_recent_games: int,
    bullpen_recent_games: int,
    include_weather: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    team_history = build_team_history(history_games)
    pitcher_logs_cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
    pitcher_profile_cache: dict[int, dict[str, Any]] = {}
    venue_coords_cache: dict[int, tuple[float | None, float | None]] = {}
    boxscore_cache: dict[int, dict[str, Any]] = {}
    game_rows: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []

    for game in target_games:
        season = season_from_date(game.game_datetime.date())
        standings = build_standings_snapshot(team_history, game.game_datetime, team_metadata)
        if game.venue_id is not None:
            get_venue_coordinates(client, game.venue_id, venue_coords_cache)
        home_form = summarize_team_form(
            team_history.get(game.home_team_id, []),
            game.game_datetime,
            recent_games,
            game.venue_id,
            venue_coords_cache,
        )
        away_form = summarize_team_form(
            team_history.get(game.away_team_id, []),
            game.game_datetime,
            recent_games,
            game.venue_id,
            venue_coords_cache,
        )
        h2h = summarize_head_to_head(history_games, game.home_team_id, game.away_team_id, game.game_datetime, recent_games)
        home_standings = standings.get(game.home_team_id, {})
        away_standings = standings.get(game.away_team_id, {})
        home_boxscore_form = summarize_team_boxscore_form(
            client,
            team_history.get(game.home_team_id, []),
            game.home_team_id,
            game.game_datetime,
            recent_games,
            boxscore_cache,
        )
        away_boxscore_form = summarize_team_boxscore_form(
            client,
            team_history.get(game.away_team_id, []),
            game.away_team_id,
            game.game_datetime,
            recent_games,
            boxscore_cache,
        )
        home_bullpen = summarize_bullpen_usage(
            client,
            team_history.get(game.home_team_id, []),
            game.home_team_id,
            game.game_datetime,
            bullpen_recent_games,
            boxscore_cache,
        )
        away_bullpen = summarize_bullpen_usage(
            client,
            team_history.get(game.away_team_id, []),
            game.away_team_id,
            game.game_datetime,
            bullpen_recent_games,
            boxscore_cache,
        )

        home_pitcher = {}
        away_pitcher = {}
        home_pitcher_profile = {}
        away_pitcher_profile = {}
        if game.home_probable_pitcher_id:
            key = (game.home_probable_pitcher_id, season)
            pitcher_logs_cache.setdefault(key, get_pitcher_log_splits(client, key[0], key[1]))
            home_pitcher = summarize_pitcher_logs(pitcher_logs_cache[key], game.game_datetime, pitcher_recent_games)
            pitcher_profile_cache.setdefault(
                game.home_probable_pitcher_id,
                get_pitcher_profile(client, game.home_probable_pitcher_id),
            )
            home_pitcher_profile = pitcher_profile_cache[game.home_probable_pitcher_id]
        if game.away_probable_pitcher_id:
            key = (game.away_probable_pitcher_id, season)
            pitcher_logs_cache.setdefault(key, get_pitcher_log_splits(client, key[0], key[1]))
            away_pitcher = summarize_pitcher_logs(pitcher_logs_cache[key], game.game_datetime, pitcher_recent_games)
            pitcher_profile_cache.setdefault(
                game.away_probable_pitcher_id,
                get_pitcher_profile(client, game.away_probable_pitcher_id),
            )
            away_pitcher_profile = pitcher_profile_cache[game.away_probable_pitcher_id]

        weather = (
            get_weather_snapshot(client, game.game_datetime, game.venue_id, venue_coords_cache)
            if include_weather
            else {}
        )
        home_team_won = None
        if game.home_score is not None and game.away_score is not None:
            home_team_won = game.home_score > game.away_score

        row = {
            "game_pk": game.game_pk,
            "game_date_utc": game.game_datetime.isoformat(),
            "status": game.status,
            "venue_name": game.venue_name,
            "home_team_id": game.home_team_id,
            "home_team_name": game.home_team_name,
            "home_team_abbrev": team_metadata.get(game.home_team_id, {}).get("abbreviation"),
            "away_team_id": game.away_team_id,
            "away_team_name": game.away_team_name,
            "away_team_abbrev": team_metadata.get(game.away_team_id, {}).get("abbreviation"),
            "home_probable_pitcher_id": game.home_probable_pitcher_id,
            "home_probable_pitcher_name": game.home_probable_pitcher_name,
            "away_probable_pitcher_id": game.away_probable_pitcher_id,
            "away_probable_pitcher_name": game.away_probable_pitcher_name,
            "home_score": game.home_score,
            "away_score": game.away_score,
            "target_home_team_win": home_team_won,
            "is_doubleheader": int(game.doubleheader == "Y") if game.doubleheader is not None else None,
            **{f"home_team_{key}": value for key, value in home_form.items()},
            **{f"away_team_{key}": value for key, value in away_form.items()},
            **{f"home_standings_{key}": value for key, value in home_standings.items()},
            **{f"away_standings_{key}": value for key, value in away_standings.items()},
            **{f"h2h_{key}": value for key, value in h2h.items()},
            **{f"home_boxscore_{key}": value for key, value in home_boxscore_form.items()},
            **{f"away_boxscore_{key}": value for key, value in away_boxscore_form.items()},
            **{f"home_bullpen_{key}": value for key, value in home_bullpen.items()},
            **{f"away_bullpen_{key}": value for key, value in away_bullpen.items()},
            **{f"home_pitcher_{key}": value for key, value in home_pitcher.items()},
            **{f"away_pitcher_{key}": value for key, value in away_pitcher.items()},
            **{f"home_pitcher_profile_{key}": value for key, value in home_pitcher_profile.items()},
            **{f"away_pitcher_profile_{key}": value for key, value in away_pitcher_profile.items()},
            **weather,
        }
        game_rows.append({key: value_for_export(value) for key, value in row.items()})

        home_snapshot = {
            "game_pk": game.game_pk,
            "game_date_utc": game.game_datetime.isoformat(),
            "team_side": "home",
            "team_id": game.home_team_id,
            "team_name": game.home_team_name,
            "team_abbrev": team_metadata.get(game.home_team_id, {}).get("abbreviation"),
            "opponent_team_id": game.away_team_id,
            "opponent_team_name": game.away_team_name,
            "opponent_team_abbrev": team_metadata.get(game.away_team_id, {}).get("abbreviation"),
            "probable_pitcher_id": game.home_probable_pitcher_id,
            "probable_pitcher_name": game.home_probable_pitcher_name,
            **home_form,
            **{f"standings_{key}": value for key, value in home_standings.items()},
            **{f"boxscore_{key}": value for key, value in home_boxscore_form.items()},
            **{f"bullpen_{key}": value for key, value in home_bullpen.items()},
            **{f"pitcher_{key}": value for key, value in home_pitcher.items()},
            **{f"pitcher_profile_{key}": value for key, value in home_pitcher_profile.items()},
            **weather,
        }
        away_snapshot = {
            "game_pk": game.game_pk,
            "game_date_utc": game.game_datetime.isoformat(),
            "team_side": "away",
            "team_id": game.away_team_id,
            "team_name": game.away_team_name,
            "team_abbrev": team_metadata.get(game.away_team_id, {}).get("abbreviation"),
            "opponent_team_id": game.home_team_id,
            "opponent_team_name": game.home_team_name,
            "opponent_team_abbrev": team_metadata.get(game.home_team_id, {}).get("abbreviation"),
            "probable_pitcher_id": game.away_probable_pitcher_id,
            "probable_pitcher_name": game.away_probable_pitcher_name,
            **away_form,
            **{f"standings_{key}": value for key, value in away_standings.items()},
            **{f"boxscore_{key}": value for key, value in away_boxscore_form.items()},
            **{f"bullpen_{key}": value for key, value in away_bullpen.items()},
            **{f"pitcher_{key}": value for key, value in away_pitcher.items()},
            **{f"pitcher_profile_{key}": value for key, value in away_pitcher_profile.items()},
            **weather,
        }
        snapshot_rows.append({key: value_for_export(value) for key, value in home_snapshot.items()})
        snapshot_rows.append({key: value_for_export(value) for key, value in away_snapshot.items()})

    return game_rows, snapshot_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_summary(
    path: Path,
    game_rows: list[dict[str, Any]],
    snapshot_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> None:
    lines = [
        "# MLB Modeling Export",
        "",
        f"- Generated at: {datetime.now(UTC).isoformat()}",
        f"- Window: {args.start_date} through {args.end_date}",
        f"- Feature history start: {args.history_start_date or season_start(args.season).isoformat()}",
        f"- Team recent-game lookback: {args.recent_games}",
        f"- Pitcher recent-appearance lookback: {args.pitcher_recent_games}",
        f"- Bullpen recent-game lookback: {args.bullpen_recent_games}",
        f"- Games exported: {len(game_rows)}",
        f"- Team/pitcher snapshots exported: {len(snapshot_rows)}",
        "",
        "## Included Features",
        "",
        "- Team form: season and recent win rates, scoring, run differential, streaks, home/away split, one-run game performance",
        "- Team context: rest days, schedule density, travel distance, previous-game context, pythagorean expectation",
        "- Relative strength: league/division rank, games back, standings-based win strength",
        "- Matchup context: recent head-to-head win rate, run differential, last meeting outcome",
        "- Recent boxscore form: hits, walks, strikeouts, power, OBP/SLG proxies, runs allowed, errors",
        "- Bullpen workload: recent relief innings, relievers used, pitches, ERA, WHIP, K/9",
        "- Pitching form: recent and season ERA, WHIP, K/9, BB/9, HR/9, innings, strikeouts, walks, batters faced, pitches, rest",
        "- Pitcher profile: handedness, age, height, weight, batting side",
        "- Game context: venue, probable pitchers, final scores when available, target label for home-team win",
    ]
    if args.include_weather:
        lines.append("- Weather context: temperature, humidity, precipitation, wind, gusts, pressure")

    lines.extend(["", "## Sample Rows", ""])
    for row in game_rows[: min(5, len(game_rows))]:
        lines.append(f"- {row['game_date_utc']} | {row['away_team_name']} at {row['home_team_name']} | target_home_team_win={row['target_home_team_win']}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build modeling-ready MLB datasets with team form, probable pitcher form, head-to-head context, and weather."
    )
    today = date.today()
    parser.add_argument("--start-date", default=today.isoformat(), help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", default=today.isoformat(), help="End date in YYYY-MM-DD format.")
    parser.add_argument("--season", type=int, default=today.year, help="MLB season year to pull.")
    parser.add_argument(
        "--history-start-date",
        default=None,
        help="Optional earlier date for feature history. Use this for multi-season training windows.",
    )
    parser.add_argument("--recent-games", type=int, default=10, help="Lookback window for team recent form.")
    parser.add_argument(
        "--pitcher-recent-games",
        type=int,
        default=5,
        help="Lookback window for recent probable-pitcher appearances.",
    )
    parser.add_argument(
        "--bullpen-recent-games",
        type=int,
        default=3,
        help="Lookback window for recent bullpen boxscore usage.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory for exported files.",
    )
    parser.add_argument(
        "--include-weather",
        action="store_true",
        help="Include historical/forecast weather features from Open-Meteo.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore cached responses and fetch fresh data.",
    )
    parser.add_argument(
        "--note-file",
        default="mlb_modeling_notes.md",
        help="Markdown summary filename written inside the output directory.",
    )
    return parser


def validate_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid date: {value}") from exc


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    start_dt = validate_date(args.start_date)
    end_dt = validate_date(args.end_date)
    if end_dt < start_dt:
        raise SystemExit("--end-date must be on or after --start-date")
    history_start = validate_date(args.history_start_date) if args.history_start_date else season_start(args.season)
    if history_start > start_dt:
        history_start = start_dt

    client = JsonClient(DEFAULT_CACHE_DIR)
    if args.force_refresh:
        client.ttl = timedelta(seconds=0)

    target_games = fetch_schedule(client, start_dt, end_dt)
    history_games = fetch_schedule(client, history_start, end_dt)
    team_metadata = get_team_metadata(client, args.season)

    game_rows, snapshot_rows = build_game_feature_rows(
        client=client,
        target_games=target_games,
        history_games=history_games,
        team_metadata=team_metadata,
        recent_games=args.recent_games,
        pitcher_recent_games=args.pitcher_recent_games,
        bullpen_recent_games=args.bullpen_recent_games,
        include_weather=args.include_weather,
    )

    output_dir = Path(args.output_dir)
    games_csv = output_dir / "mlb_game_features.csv"
    snapshots_csv = output_dir / "mlb_team_pitcher_snapshots.csv"
    note_path = output_dir / args.note_file

    write_csv(games_csv, game_rows)
    write_csv(snapshots_csv, snapshot_rows)
    write_markdown_summary(note_path, game_rows, snapshot_rows, args)

    print(f"Wrote {len(game_rows)} game rows to {games_csv}")
    print(f"Wrote {len(snapshot_rows)} snapshot rows to {snapshots_csv}")
    print(f"Wrote markdown notes to {note_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
