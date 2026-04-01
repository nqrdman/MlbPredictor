#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from mlb_model_builder import JsonClient, MLB_API_BASE, get_pitcher_log_splits, summarize_pitcher_logs


REQUEST_CACHE = Path(".cache") / "mlb_player_props"


def safe_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@dataclass(slots=True)
class HRCandidate:
    player_id: int
    player_name: str
    score: float
    season_home_runs: float | None
    season_slg: float | None
    recent_home_runs: float | None
    bats: str | None


@dataclass(slots=True)
class BatterPropCandidate:
    player_id: int
    player_name: str
    team_name: str
    bats: str | None
    hit_probability: float
    expected_hits: float
    expected_total_bases: float
    expected_rbi: float
    home_run_probability: float
    score: float


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def get_person(client: JsonClient, person_id: int) -> dict[str, Any]:
    payload = client.get_json(f"{MLB_API_BASE}/people/{person_id}")
    people = payload.get("people", [])
    return people[0] if people else {}


def get_team_roster(client: JsonClient, team_id: int, season: int) -> list[dict[str, Any]]:
    payload = client.get_json(
        f"{MLB_API_BASE}/teams/{team_id}/roster",
        {
            "rosterType": "active",
            "season": season,
        },
    )
    return payload.get("roster", [])


def get_batting_season_stats(client: JsonClient, player_id: int, season: int) -> dict[str, float | None]:
    payload = client.get_json(
        f"{MLB_API_BASE}/people/{player_id}/stats",
        {
            "stats": "season",
            "group": "hitting",
            "season": season,
            "gameType": "R",
        },
    )
    blocks = payload.get("stats", [])
    if not blocks or not blocks[0].get("splits"):
        return {}
    stat = blocks[0]["splits"][0].get("stat", {})
    return {
        "plate_appearances": safe_float(stat.get("plateAppearances")),
        "at_bats": safe_float(stat.get("atBats")),
        "home_runs": safe_float(stat.get("homeRuns")),
        "hits": safe_float(stat.get("hits")),
        "walks": safe_float(stat.get("baseOnBalls")),
        "slugging": safe_float(stat.get("slg")),
        "ops": safe_float(stat.get("ops")),
        "obp": safe_float(stat.get("obp")),
    }


def get_batting_gamelog(client: JsonClient, player_id: int, season: int) -> list[dict[str, Any]]:
    payload = client.get_json(
        f"{MLB_API_BASE}/people/{player_id}/stats",
        {
            "stats": "gameLog",
            "group": "hitting",
            "season": season,
            "gameType": "R",
        },
    )
    blocks = payload.get("stats", [])
    if not blocks:
        return []
    return blocks[0].get("splits", [])


def get_pitch_hand(client: JsonClient, pitcher_id: int | None) -> str | None:
    if not pitcher_id:
        return None
    person = get_person(client, pitcher_id)
    return ((person.get("pitchHand") or {}).get("code") or "").upper() or None


def recent_home_runs(gamelogs: list[dict[str, Any]], before_dt: datetime, recent_games: int) -> float | None:
    prior = []
    for split in gamelogs:
        game_date = split.get("date")
        if not game_date:
            continue
        dt = datetime.fromisoformat(f"{game_date}T00:00:00+00:00")
        if dt < before_dt:
            prior.append(split)
    recent = prior[-recent_games:]
    if not recent:
        return None
    total = 0.0
    for split in recent:
        stat = split.get("stat", {})
        total += safe_float(stat.get("homeRuns")) or 0.0
    return total / len(recent)


def recent_stat_rate(
    gamelogs: list[dict[str, Any]],
    before_dt: datetime,
    recent_games: int,
    stat_key: str,
    denominator_key: str,
) -> float | None:
    prior = []
    for split in gamelogs:
        game_date = split.get("date")
        if not game_date:
            continue
        dt = datetime.fromisoformat(f"{game_date}T00:00:00+00:00")
        if dt < before_dt:
            prior.append(split)
    recent = prior[-recent_games:]
    numerator = 0.0
    denominator = 0.0
    for split in recent:
        stat = split.get("stat", {})
        numerator += safe_float(stat.get(stat_key)) or 0.0
        denominator += safe_float(stat.get(denominator_key)) or 0.0
    if denominator <= 0:
        return None
    return numerator / denominator


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def expected_pitcher_outs(summary: dict[str, Any]) -> float:
    recent_ip = summary.get("recent_innings_pitched")
    season_ip = summary.get("season_innings_pitched")
    recent_apps = summary.get("recent_appearances") or 0
    season_apps = summary.get("season_appearances") or 0
    recent_ip_per_app = (recent_ip / recent_apps) if recent_ip and recent_apps else None
    season_ip_per_app = (season_ip / season_apps) if season_ip and season_apps else None
    if recent_ip_per_app is not None and season_ip_per_app is not None:
        ip = (0.7 * recent_ip_per_app) + (0.3 * season_ip_per_app)
    elif recent_ip_per_app is not None:
        ip = recent_ip_per_app
    elif season_ip_per_app is not None:
        ip = season_ip_per_app
    else:
        ip = 5.0
    return max(ip * 3.0, 0.0)


def expected_pitcher_strikeouts(summary: dict[str, Any], opponent_recent_ks: float | None) -> float:
    expected_outs = expected_pitcher_outs(summary)
    expected_ip = expected_outs / 3.0
    recent_k9 = summary.get("recent_k_per_9")
    season_k9 = summary.get("season_k_per_9")
    if recent_k9 is not None and season_k9 is not None:
        k9 = (0.7 * recent_k9) + (0.3 * season_k9)
    else:
        k9 = recent_k9 if recent_k9 is not None else season_k9
    if k9 is None:
        k9 = 8.0
    strikeouts = expected_ip * (k9 / 9.0)
    if opponent_recent_ks is not None:
        strikeouts *= max(min(opponent_recent_ks / 8.5, 1.2), 0.8)
    return max(strikeouts, 0.0)


def expected_pitcher_earned_runs(summary: dict[str, Any], opponent_recent_runs: float | None) -> float:
    expected_outs = expected_pitcher_outs(summary)
    expected_ip = expected_outs / 3.0
    recent_era = summary.get("recent_era")
    season_era = summary.get("season_era")
    if recent_era is not None and season_era is not None:
        era = (0.7 * recent_era) + (0.3 * season_era)
    else:
        era = recent_era if recent_era is not None else season_era
    if era is None:
        era = 4.2
    earned_runs = expected_ip * (era / 9.0)
    if opponent_recent_runs is not None:
        earned_runs *= max(min(opponent_recent_runs / 4.3, 1.2), 0.8)
    return max(earned_runs, 0.0)


def expected_pitcher_hits_allowed(summary: dict[str, Any], opponent_recent_hits: float | None) -> float:
    expected_outs = expected_pitcher_outs(summary)
    expected_ip = expected_outs / 3.0
    whip_recent = summary.get("recent_whip")
    whip_season = summary.get("season_whip")
    if whip_recent is not None and whip_season is not None:
        whip = (0.7 * whip_recent) + (0.3 * whip_season)
    else:
        whip = whip_recent if whip_recent is not None else whip_season
    if whip is None:
        whip = 1.30
    baserunners = expected_ip * whip
    hits = baserunners * 0.72
    if opponent_recent_hits is not None:
        hits *= max(min(opponent_recent_hits / 8.2, 1.2), 0.8)
    return max(hits, 0.0)


def rank_home_run_candidates(
    client: JsonClient,
    team_id: int,
    opposing_pitcher_hand: str | None,
    game_dt: datetime,
    season: int,
    recent_games: int,
) -> list[HRCandidate]:
    roster = get_team_roster(client, team_id, season)
    candidates: list[HRCandidate] = []
    for player in roster:
        person = player.get("person", {}) or {}
        player_id = person.get("id")
        if not player_id:
            continue
        position_type = ((player.get("position") or {}).get("type") or "").lower()
        if "pitcher" in position_type:
            continue

        profile = get_person(client, int(player_id))
        bats = ((profile.get("batSide") or {}).get("code") or "").upper() or None
        current_stats = get_batting_season_stats(client, int(player_id), season)
        prior_stats = get_batting_season_stats(client, int(player_id), season - 1)
        gamelog = get_batting_gamelog(client, int(player_id), season)

        current_pa = current_stats.get("plate_appearances") or 0.0
        carryover = 0.55 if current_pa < 25 else 0.25
        season_hr = ((1.0 - carryover) * (current_stats.get("home_runs") or 0.0)) + (carryover * (prior_stats.get("home_runs") or 0.0))
        season_slg = ((1.0 - carryover) * (current_stats.get("slugging") or 0.0)) + (carryover * (prior_stats.get("slugging") or 0.0))
        season_ops = ((1.0 - carryover) * (current_stats.get("ops") or 0.0)) + (carryover * (prior_stats.get("ops") or 0.0))
        recent_hr = recent_home_runs(gamelog, game_dt, recent_games)
        recent_hr_value = recent_hr or 0.0

        platoon_bonus = 0.0
        if opposing_pitcher_hand == "R" and bats == "L":
            platoon_bonus = 0.08
        elif opposing_pitcher_hand == "L" and bats == "R":
            platoon_bonus = 0.08
        elif bats and opposing_pitcher_hand and bats == opposing_pitcher_hand:
            platoon_bonus = -0.04

        score = (
            (season_hr * 0.09)
            + (season_slg * 1.4)
            + (season_ops * 0.6)
            + (recent_hr_value * 1.8)
            + platoon_bonus
        )
        if score <= 0:
            continue

        candidates.append(
            HRCandidate(
                player_id=int(player_id),
                player_name=person.get("fullName", "Unknown"),
                score=score,
                season_home_runs=season_hr,
                season_slg=season_slg,
                recent_home_runs=recent_hr,
                bats=bats,
            )
        )

    return sorted(candidates, key=lambda item: item.score, reverse=True)[:5]


def rank_batter_props(
    client: JsonClient,
    team_id: int,
    team_name: str,
    opposing_pitcher_hand: str | None,
    game_dt: datetime,
    season: int,
    recent_games: int,
) -> list[BatterPropCandidate]:
    roster = get_team_roster(client, team_id, season)
    candidates: list[BatterPropCandidate] = []
    for player in roster:
        person = player.get("person", {}) or {}
        player_id = person.get("id")
        if not player_id:
            continue
        position_type = ((player.get("position") or {}).get("type") or "").lower()
        if "pitcher" in position_type:
            continue

        profile = get_person(client, int(player_id))
        bats = ((profile.get("batSide") or {}).get("code") or "").upper() or None
        current_stats = get_batting_season_stats(client, int(player_id), season)
        prior_stats = get_batting_season_stats(client, int(player_id), season - 1)
        gamelog = get_batting_gamelog(client, int(player_id), season)

        current_pa = current_stats.get("plate_appearances") or 0.0
        carryover = 0.60 if current_pa < 20 else 0.25

        current_at_bats = current_stats.get("at_bats") or 0.0
        prior_at_bats = prior_stats.get("at_bats") or 0.0
        current_hits = current_stats.get("hits") or 0.0
        prior_hits = prior_stats.get("hits") or 0.0
        current_hr = current_stats.get("home_runs") or 0.0
        prior_hr = prior_stats.get("home_runs") or 0.0
        current_walks = current_stats.get("walks") or 0.0
        prior_walks = prior_stats.get("walks") or 0.0
        current_slg = current_stats.get("slugging") or 0.0
        prior_slg = prior_stats.get("slugging") or 0.0
        current_obp = current_stats.get("obp") or 0.0
        prior_obp = prior_stats.get("obp") or 0.0
        current_ops = current_stats.get("ops") or 0.0
        prior_ops = prior_stats.get("ops") or 0.0

        avg_rate = ((1.0 - carryover) * (current_hits / current_at_bats if current_at_bats else 0.0)) + (
            carryover * (prior_hits / prior_at_bats if prior_at_bats else 0.0)
        )
        hr_rate = ((1.0 - carryover) * (current_hr / current_at_bats if current_at_bats else 0.0)) + (
            carryover * (prior_hr / prior_at_bats if prior_at_bats else 0.0)
        )
        walk_rate = ((1.0 - carryover) * (current_walks / current_pa if current_pa else 0.0)) + (
            carryover * (prior_walks / ((prior_stats.get("plate_appearances") or 0.0)) if (prior_stats.get("plate_appearances") or 0.0) else 0.0)
        )
        slg = ((1.0 - carryover) * current_slg) + (carryover * prior_slg)
        obp = ((1.0 - carryover) * current_obp) + (carryover * prior_obp)
        ops = ((1.0 - carryover) * current_ops) + (carryover * prior_ops)

        recent_avg = recent_stat_rate(gamelog, game_dt, recent_games, "hits", "atBats")
        recent_hr_rate = recent_stat_rate(gamelog, game_dt, recent_games, "homeRuns", "atBats")
        recent_tb_rate = recent_stat_rate(gamelog, game_dt, recent_games, "totalBases", "atBats")
        recent_rbi_rate = recent_stat_rate(gamelog, game_dt, recent_games, "rbi", "gamesPlayed")

        if recent_avg is not None:
            avg_rate = (0.65 * avg_rate) + (0.35 * recent_avg)
        if recent_hr_rate is not None:
            hr_rate = (0.55 * hr_rate) + (0.45 * recent_hr_rate)
        if recent_tb_rate is not None:
            slg = (0.65 * slg) + (0.35 * recent_tb_rate)

        platoon_bonus = 0.0
        if opposing_pitcher_hand == "R" and bats == "L":
            platoon_bonus = 0.02
        elif opposing_pitcher_hand == "L" and bats == "R":
            platoon_bonus = 0.02
        elif bats and opposing_pitcher_hand and bats == opposing_pitcher_hand:
            platoon_bonus = -0.01

        expected_pa = 4.1 + max(min((obp - 0.315) * 4.0, 0.4), -0.3)
        expected_abs = max(expected_pa - (walk_rate * expected_pa), 2.8)
        adjusted_avg = clamp(avg_rate + platoon_bonus, 0.08, 0.42)
        adjusted_hr_rate = clamp(hr_rate + (platoon_bonus * 0.5), 0.005, 0.12)
        adjusted_slg = clamp(slg + (platoon_bonus * 0.25), 0.18, 0.85)

        hit_probability = 1.0 - ((1.0 - adjusted_avg) ** expected_abs)
        expected_hits = adjusted_avg * expected_abs
        expected_total_bases = adjusted_slg * expected_abs
        home_run_probability = 1.0 - ((1.0 - adjusted_hr_rate) ** expected_abs)
        expected_rbi = max(((recent_rbi_rate or 0.14) * expected_pa) + (home_run_probability * 0.35), 0.0)
        score = (hit_probability * 1.2) + (expected_total_bases * 0.5) + (home_run_probability * 2.4) + (ops * 0.3)

        candidates.append(
            BatterPropCandidate(
                player_id=int(player_id),
                player_name=person.get("fullName", "Unknown"),
                team_name=team_name,
                bats=bats,
                hit_probability=hit_probability,
                expected_hits=expected_hits,
                expected_total_bases=expected_total_bases,
                expected_rbi=expected_rbi,
                home_run_probability=home_run_probability,
                score=score,
            )
        )

    return sorted(candidates, key=lambda item: item.score, reverse=True)[:5]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict[str, Any]], batter_rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    lines = [
        "# MLB Player Props",
        "",
        f"- Generated at: {datetime.now(UTC).isoformat()}",
        f"- Prediction source file: {args.predict_csv}",
        "",
        "## Games",
        "",
    ]
    for row in rows:
        lines.append(
            f"- {row['away_team_name']} at {row['home_team_name']} | "
            f"{row['away_pitcher_name']} Ks {row['away_pitcher_predicted_strikeouts']} / Outs {row['away_pitcher_predicted_outs']} | "
            f"{row['home_pitcher_name']} Ks {row['home_pitcher_predicted_strikeouts']} / Outs {row['home_pitcher_predicted_outs']}"
        )
        lines.append(f"  Away HR candidates: {row['away_home_run_candidates']}")
        lines.append(f"  Home HR candidates: {row['home_home_run_candidates']}")
    lines.extend(["", "## Batter Props", ""])
    for row in batter_rows[: min(40, len(batter_rows))]:
        lines.append(
            f"- {row['team_name']} | {row['player_name']} | 1+ hit {row['hit_probability']} | "
            f"TB {row['expected_total_bases']} | RBI {row['expected_rbi']} | HR {row['home_run_probability']}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build MLB pitcher props and home run candidate outputs from a slate feature CSV.")
    parser.add_argument("--predict-csv", default="outputs/mlb_game_features.csv", help="Feature CSV for the slate to score.")
    parser.add_argument("--output-dir", default="outputs", help="Directory for prop exports.")
    parser.add_argument("--recent-games", type=int, default=10, help="Recent batting game lookback for home run candidates.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    predict_csv = Path(args.predict_csv)
    if not predict_csv.exists():
        raise SystemExit(f"Prediction CSV not found: {predict_csv}")

    client = JsonClient(REQUEST_CACHE)
    rows = load_rows(predict_csv)
    output_rows: list[dict[str, Any]] = []
    batter_prop_rows: list[dict[str, Any]] = []

    for row in rows:
        game_dt = parse_datetime(row["game_date_utc"])
        season = game_dt.year
        away_team_id = int(row["away_team_id"])
        home_team_id = int(row["home_team_id"])
        away_pitcher_id = int(row["away_probable_pitcher_id"]) if row.get("away_probable_pitcher_id") else None
        home_pitcher_id = int(row["home_probable_pitcher_id"]) if row.get("home_probable_pitcher_id") else None

        away_pitcher_summary = summarize_pitcher_logs(
            get_pitcher_log_splits(client, away_pitcher_id, season) if away_pitcher_id else [],
            game_dt,
            6,
        )
        home_pitcher_summary = summarize_pitcher_logs(
            get_pitcher_log_splits(client, home_pitcher_id, season) if home_pitcher_id else [],
            game_dt,
            6,
        )

        away_pitch_hand = get_pitch_hand(client, away_pitcher_id)
        home_pitch_hand = get_pitch_hand(client, home_pitcher_id)

        away_hr_candidates = rank_home_run_candidates(
            client,
            away_team_id,
            home_pitch_hand,
            game_dt,
            season,
            args.recent_games,
        )
        home_hr_candidates = rank_home_run_candidates(
            client,
            home_team_id,
            away_pitch_hand,
            game_dt,
            season,
            args.recent_games,
        )
        away_batter_props = rank_batter_props(
            client,
            away_team_id,
            row["away_team_name"],
            home_pitch_hand,
            game_dt,
            season,
            args.recent_games,
        )
        home_batter_props = rank_batter_props(
            client,
            home_team_id,
            row["home_team_name"],
            away_pitch_hand,
            game_dt,
            season,
            args.recent_games,
        )

        away_recent_ks = safe_float(row.get("away_boxscore_batting_strikeouts_avg"))
        home_recent_ks = safe_float(row.get("home_boxscore_batting_strikeouts_avg"))
        away_recent_runs = safe_float(row.get("away_boxscore_batting_runs_avg"))
        home_recent_runs = safe_float(row.get("home_boxscore_batting_runs_avg"))
        away_recent_hits = safe_float(row.get("away_boxscore_batting_hits_avg"))
        home_recent_hits = safe_float(row.get("home_boxscore_batting_hits_avg"))

        output_rows.append(
            {
                "game_pk": row["game_pk"],
                "game_date_utc": row["game_date_utc"],
                "away_team_name": row["away_team_name"],
                "home_team_name": row["home_team_name"],
                "away_pitcher_name": row.get("away_probable_pitcher_name", ""),
                "home_pitcher_name": row.get("home_probable_pitcher_name", ""),
                "away_pitcher_predicted_strikeouts": round(expected_pitcher_strikeouts(away_pitcher_summary, home_recent_ks), 2),
                "away_pitcher_predicted_outs": round(expected_pitcher_outs(away_pitcher_summary), 2),
                "away_pitcher_predicted_earned_runs": round(expected_pitcher_earned_runs(away_pitcher_summary, home_recent_runs), 2),
                "away_pitcher_predicted_hits_allowed": round(expected_pitcher_hits_allowed(away_pitcher_summary, home_recent_hits), 2),
                "home_pitcher_predicted_strikeouts": round(expected_pitcher_strikeouts(home_pitcher_summary, away_recent_ks), 2),
                "home_pitcher_predicted_outs": round(expected_pitcher_outs(home_pitcher_summary), 2),
                "home_pitcher_predicted_earned_runs": round(expected_pitcher_earned_runs(home_pitcher_summary, away_recent_runs), 2),
                "home_pitcher_predicted_hits_allowed": round(expected_pitcher_hits_allowed(home_pitcher_summary, away_recent_hits), 2),
                "away_home_run_candidates": "; ".join(
                    f"{candidate.player_name} ({candidate.score:.2f})" for candidate in away_hr_candidates[:3]
                ),
                "home_home_run_candidates": "; ".join(
                    f"{candidate.player_name} ({candidate.score:.2f})" for candidate in home_hr_candidates[:3]
                ),
            }
        )
        for side, candidates in (("away", away_batter_props), ("home", home_batter_props)):
            for candidate in candidates:
                batter_prop_rows.append(
                    {
                        "game_pk": row["game_pk"],
                        "game_date_utc": row["game_date_utc"],
                        "team_side": side,
                        "team_name": candidate.team_name,
                        "player_id": candidate.player_id,
                        "player_name": candidate.player_name,
                        "bats": candidate.bats,
                        "hit_probability": round(candidate.hit_probability, 4),
                        "expected_hits": round(candidate.expected_hits, 3),
                        "expected_total_bases": round(candidate.expected_total_bases, 3),
                        "expected_rbi": round(candidate.expected_rbi, 3),
                        "home_run_probability": round(candidate.home_run_probability, 4),
                        "prop_score": round(candidate.score, 4),
                    }
                )

    output_dir = Path(args.output_dir)
    csv_path = output_dir / "mlb_player_props.csv"
    batter_csv_path = output_dir / "mlb_batter_props.csv"
    md_path = output_dir / "mlb_player_props.md"
    write_csv(csv_path, output_rows)
    write_csv(batter_csv_path, batter_prop_rows)
    write_markdown(md_path, output_rows, batter_prop_rows, args)
    print(f"Wrote player props to {csv_path}")
    print(f"Wrote batter props to {batter_csv_path}")
    print(f"Wrote player prop notes to {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
