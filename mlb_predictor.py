#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EXCLUDED_COLUMNS = {
    "game_pk",
    "game_date_utc",
    "status",
    "venue_name",
    "home_team_id",
    "home_team_name",
    "away_team_id",
    "away_team_name",
    "home_probable_pitcher_id",
    "home_probable_pitcher_name",
    "away_probable_pitcher_id",
    "away_probable_pitcher_name",
    "home_score",
    "away_score",
    "target_home_team_win",
}

REQUEST_HEADERS = {
    "User-Agent": "mlb-market-blend/1.0",
    "Accept": "text/html,application/xhtml+xml",
}

CBS_ABBREV_MAP = {
    "AZ": "ARI",
    "CWS": "CHW",
    "WSH": "WSH",
    "SD": "SD",
    "SF": "SF",
    "KC": "KC",
    "TB": "TB",
    "OAK": "OAK",
    "ATH": "OAK",
}


def safe_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sigmoid(value: float) -> float:
    if value >= 0:
        exp_value = math.exp(-value)
        return 1.0 / (1.0 + exp_value)
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def american_to_implied_prob(moneyline: int) -> float:
    if moneyline > 0:
        return 100.0 / (moneyline + 100.0)
    return abs(moneyline) / (abs(moneyline) + 100.0)


def no_vig_pair(away_moneyline: int, home_moneyline: int) -> tuple[float, float]:
    away_raw = american_to_implied_prob(away_moneyline)
    home_raw = american_to_implied_prob(home_moneyline)
    total = away_raw + home_raw
    return away_raw / total, home_raw / total


@dataclass(slots=True)
class DatasetRow:
    raw: dict[str, str]
    target: int | None
    game_datetime: datetime


@dataclass(slots=True)
class StandardScaler:
    means: list[float]
    scales: list[float]

    def transform_row(self, values: list[float | None]) -> list[float]:
        transformed: list[float] = []
        for index, value in enumerate(values):
            filled = self.means[index] if value is None else value
            scale = self.scales[index] if self.scales[index] else 1.0
            transformed.append((filled - self.means[index]) / scale)
        return transformed


@dataclass(slots=True)
class LogisticModel:
    feature_names: list[str]
    scaler: StandardScaler
    weights: list[float]
    bias: float

    def predict_proba(self, values: list[float | None]) -> float:
        features = self.scaler.transform_row(values)
        linear = self.bias
        for weight, feature in zip(self.weights, features):
            linear += weight * feature
        return sigmoid(linear)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_names": self.feature_names,
            "means": self.scaler.means,
            "scales": self.scaler.scales,
            "weights": self.weights,
            "bias": self.bias,
        }


@dataclass(slots=True)
class LinearModel:
    feature_names: list[str]
    scaler: StandardScaler
    weights: list[float]
    bias: float

    def predict(self, values: list[float | None]) -> float:
        features = self.scaler.transform_row(values)
        prediction = self.bias
        for weight, feature in zip(self.weights, features):
            prediction += weight * feature
        return prediction

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_names": self.feature_names,
            "means": self.scaler.means,
            "scales": self.scaler.scales,
            "weights": self.weights,
            "bias": self.bias,
        }


@dataclass(slots=True)
class ProbabilityCalibrator:
    slope: float
    intercept: float
    min_prob: float
    max_prob: float

    def calibrate(self, probability: float) -> float:
        clipped = min(max(probability, 1e-6), 1.0 - 1e-6)
        logit = math.log(clipped / (1.0 - clipped))
        calibrated = sigmoid((self.slope * logit) + self.intercept)
        return min(max(calibrated, self.min_prob), self.max_prob)

    def to_dict(self) -> dict[str, float]:
        return {
            "slope": self.slope,
            "intercept": self.intercept,
            "min_prob": self.min_prob,
            "max_prob": self.max_prob,
        }


@dataclass(slots=True)
class MarketOdds:
    away_moneyline: int | None
    home_moneyline: int | None
    away_implied_prob: float | None
    home_implied_prob: float | None


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def load_rows(csv_path: Path) -> list[DatasetRow]:
    rows: list[DatasetRow] = []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            target_value = raw.get("target_home_team_win")
            target = None if target_value in (None, "", "None") else int(float(target_value))
            rows.append(
                DatasetRow(
                    raw=raw,
                    target=target,
                    game_datetime=parse_datetime(raw["game_date_utc"]),
                )
            )
    return rows


def choose_feature_names(rows: list[DatasetRow]) -> list[str]:
    if not rows:
        return []
    feature_names: list[str] = []
    for key in rows[0].raw.keys():
        if key in EXCLUDED_COLUMNS:
            continue
        if key.endswith("_league_id") or key.endswith("_division_id"):
            continue
        if any(safe_float(row.raw.get(key)) is not None for row in rows):
            feature_names.append(key)
    return feature_names


def build_matrix(rows: list[DatasetRow], feature_names: list[str]) -> list[list[float | None]]:
    return [[safe_float(row.raw.get(name)) for name in feature_names] for row in rows]


def fit_scaler(matrix: list[list[float | None]]) -> StandardScaler:
    means: list[float] = []
    scales: list[float] = []
    feature_count = len(matrix[0]) if matrix else 0
    for index in range(feature_count):
        values = [row[index] for row in matrix if row[index] is not None]
        if not values:
            means.append(0.0)
            scales.append(1.0)
            continue
        mean_value = sum(values) / len(values)
        variance = sum((value - mean_value) ** 2 for value in values) / len(values)
        std_dev = math.sqrt(variance)
        means.append(mean_value)
        scales.append(std_dev if std_dev > 1e-9 else 1.0)
    return StandardScaler(means=means, scales=scales)


def train_logistic_regression(
    matrix: list[list[float | None]],
    targets: list[int],
    learning_rate: float,
    epochs: int,
    l2_penalty: float,
    seed: int,
) -> LogisticModel:
    if not matrix:
        raise ValueError("Training matrix is empty.")

    scaler = fit_scaler(matrix)
    features = [scaler.transform_row(row) for row in matrix]
    feature_count = len(features[0])
    random.seed(seed)
    weights = [random.uniform(-0.01, 0.01) for _ in range(feature_count)]
    bias = 0.0

    for _ in range(epochs):
        grad_w = [0.0] * feature_count
        grad_b = 0.0
        sample_count = len(features)
        for row, target in zip(features, targets):
            prediction = sigmoid(sum(weight * value for weight, value in zip(weights, row)) + bias)
            error = prediction - target
            grad_b += error
            for index, value in enumerate(row):
                grad_w[index] += error * value

        for index in range(feature_count):
            grad_w[index] = (grad_w[index] / sample_count) + (l2_penalty * weights[index])
            weights[index] -= learning_rate * grad_w[index]
        grad_b /= sample_count
        bias -= learning_rate * grad_b

    return LogisticModel(feature_names=[], scaler=scaler, weights=weights, bias=bias)


def train_linear_regression(
    matrix: list[list[float | None]],
    targets: list[float],
    learning_rate: float,
    epochs: int,
    l2_penalty: float,
    seed: int,
) -> LinearModel:
    if not matrix:
        raise ValueError("Training matrix is empty.")

    scaler = fit_scaler(matrix)
    features = [scaler.transform_row(row) for row in matrix]
    feature_count = len(features[0])
    random.seed(seed)
    weights = [random.uniform(-0.01, 0.01) for _ in range(feature_count)]
    bias = sum(targets) / len(targets) if targets else 0.0

    for _ in range(epochs):
        grad_w = [0.0] * feature_count
        grad_b = 0.0
        sample_count = len(features)
        for row, target in zip(features, targets):
            prediction = sum(weight * value for weight, value in zip(weights, row)) + bias
            error = prediction - target
            grad_b += error
            for index, value in enumerate(row):
                grad_w[index] += error * value

        for index in range(feature_count):
            grad_w[index] = (grad_w[index] / sample_count) + (l2_penalty * weights[index])
            weights[index] -= learning_rate * grad_w[index]
        grad_b /= sample_count
        bias -= learning_rate * grad_b

    return LinearModel(feature_names=[], scaler=scaler, weights=weights, bias=bias)


def accuracy_score(actual: list[int], predicted_probs: list[float]) -> float:
    correct = sum(int(prob >= 0.5) == target for target, prob in zip(actual, predicted_probs))
    return correct / len(actual) if actual else 0.0


def brier_score(actual: list[int], predicted_probs: list[float]) -> float:
    if not actual:
        return 0.0
    return sum((prob - target) ** 2 for target, prob in zip(actual, predicted_probs)) / len(actual)


def log_loss(actual: list[int], predicted_probs: list[float]) -> float:
    if not actual:
        return 0.0
    epsilon = 1e-12
    total = 0.0
    for target, prob in zip(actual, predicted_probs):
        clipped = min(max(prob, epsilon), 1.0 - epsilon)
        total += -(target * math.log(clipped) + (1 - target) * math.log(1.0 - clipped))
    return total / len(actual)


def mae(actual: list[float], predicted: list[float]) -> float:
    if not actual:
        return 0.0
    return sum(abs(pred - target) for target, pred in zip(actual, predicted)) / len(actual)


def rmse(actual: list[float], predicted: list[float]) -> float:
    if not actual:
        return 0.0
    return math.sqrt(sum((pred - target) ** 2 for target, pred in zip(actual, predicted)) / len(actual))


def fit_probability_calibrator(
    actual: list[int],
    predicted_probs: list[float],
    epochs: int,
    learning_rate: float,
    min_prob: float,
    max_prob: float,
) -> ProbabilityCalibrator:
    if not actual or not predicted_probs:
        return ProbabilityCalibrator(slope=1.0, intercept=0.0, min_prob=min_prob, max_prob=max_prob)
    logits = []
    for prob in predicted_probs:
        clipped = min(max(prob, 1e-6), 1.0 - 1e-6)
        logits.append(math.log(clipped / (1.0 - clipped)))
    slope = 1.0
    intercept = 0.0
    sample_count = len(actual)
    for _ in range(epochs):
        grad_slope = 0.0
        grad_intercept = 0.0
        for target, logit in zip(actual, logits):
            calibrated = sigmoid((slope * logit) + intercept)
            error = calibrated - target
            grad_slope += error * logit
            grad_intercept += error
        slope -= learning_rate * (grad_slope / sample_count)
        intercept -= learning_rate * (grad_intercept / sample_count)
    return ProbabilityCalibrator(
        slope=slope,
        intercept=intercept,
        min_prob=min_prob,
        max_prob=max_prob,
    )


def normalize_cbs_abbrev(value: str | None) -> str | None:
    if not value:
        return None
    upper = value.upper()
    return CBS_ABBREV_MAP.get(upper, upper)


def fetch_cbs_market_odds(away_abbrev: str | None, home_abbrev: str | None, game_date: datetime) -> MarketOdds:
    away = normalize_cbs_abbrev(away_abbrev)
    home = normalize_cbs_abbrev(home_abbrev)
    if not away or not home:
        return MarketOdds(None, None, None, None)
    date_token = game_date.strftime("%Y%m%d")
    url = f"https://new.cbssports.com/mlb/gametracker/preview/MLB_{date_token}_{away}%40{home}/"
    request = Request(url, headers=REQUEST_HEADERS)
    try:
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return MarketOdds(None, None, None, None)

    match = re.search(
        r'<span class="team-name".*?>\s*' + re.escape(away) + r'\s*</span>.*?ML:\s*([+-]\d+).*?'
        r'<span class="team-name".*?>\s*' + re.escape(home) + r'\s*</span>.*?ML:\s*([+-]\d+)',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        all_lines = re.findall(r'ML:\s*([+-]\d+)', html, re.IGNORECASE)
        if len(all_lines) >= 2:
            away_moneyline = int(all_lines[0])
            home_moneyline = int(all_lines[1])
        else:
            return MarketOdds(None, None, None, None)
    else:
        away_moneyline = int(match.group(1))
        home_moneyline = int(match.group(2))

    away_prob, home_prob = no_vig_pair(away_moneyline, home_moneyline)
    return MarketOdds(
        away_moneyline=away_moneyline,
        home_moneyline=home_moneyline,
        away_implied_prob=away_prob,
        home_implied_prob=home_prob,
    )


def chronological_split(rows: list[DatasetRow], validation_fraction: float) -> tuple[list[DatasetRow], list[DatasetRow]]:
    finalized = sorted([row for row in rows if row.target is not None], key=lambda row: row.game_datetime)
    if len(finalized) < 20:
        raise ValueError(
            "Not enough finalized games to train a model yet. Build a larger historical dataset first."
        )
    split_index = max(1, int(len(finalized) * (1.0 - validation_fraction)))
    split_index = min(split_index, len(finalized) - 1)
    return finalized[:split_index], finalized[split_index:]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(
    path: Path,
    metrics: dict[str, float],
    predictions: list[dict[str, Any]],
    top_features: list[tuple[str, float]],
    args: argparse.Namespace,
) -> None:
    lines = [
        "# MLB Prediction Run",
        "",
        f"- Generated at: {datetime.now(UTC).isoformat()}",
        f"- Training file: {args.input_csv}",
        f"- Prediction file: {args.predict_csv or args.input_csv}",
        f"- Validation fraction: {args.validation_fraction}",
        f"- Prediction start date: {args.prediction_start_date}",
        f"- Learning rate: {args.learning_rate}",
        f"- Epochs: {args.epochs}",
        f"- L2 penalty: {args.l2_penalty}",
        f"- Calibration epochs: {args.calibration_epochs}",
        f"- Probability cap range: {args.min_probability} to {args.max_probability}",
        f"- Market blend weight: {args.market_weight}",
        f"- Market source: {'CBS Sports moneylines' if args.fetch_cbs_odds else 'None'}",
        "",
        "## Validation Metrics",
        "",
        f"- Accuracy: {metrics['accuracy']:.4f}",
        f"- Log loss: {metrics['log_loss']:.4f}",
        f"- Brier score: {metrics['brier_score']:.4f}",
        f"- Calibrated log loss: {metrics['calibrated_log_loss']:.4f}",
        f"- Calibrated Brier score: {metrics['calibrated_brier_score']:.4f}",
        f"- Home runs MAE: {metrics['home_runs_mae']:.4f}",
        f"- Away runs MAE: {metrics['away_runs_mae']:.4f}",
        f"- Total runs MAE: {metrics['total_runs_mae']:.4f}",
        f"- Total runs RMSE: {metrics['total_runs_rmse']:.4f}",
        f"- Run line accuracy: {metrics['runline_accuracy']:.4f}",
        f"- Run line log loss: {metrics['runline_log_loss']:.4f}",
        f"- Training games: {int(metrics['train_games'])}",
        f"- Validation games: {int(metrics['validation_games'])}",
        "",
        "## Strongest Weighted Features",
        "",
    ]
    if top_features:
        for name, weight in top_features:
            lines.append(f"- {name}: {weight:.4f}")
    else:
        lines.append("- No feature weights available.")
    lines.extend([
        "",
        "## Upcoming Predictions",
        "",
    ])
    if predictions:
        for row in predictions[: min(20, len(predictions))]:
            lines.append(
                f"- {row['game_date_utc']} | {row['away_team_name']} at {row['home_team_name']} | "
                f"home_win_prob={row['home_win_probability']} | total={row['predicted_total_runs']} | "
                f"home_runs={row['predicted_home_runs']} | away_runs={row['predicted_away_runs']} | pick={row['predicted_winner']}"
            )
    else:
        lines.append("- No future or unresolved games were present in the input file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_predictions(
    model: LogisticModel,
    calibrator: ProbabilityCalibrator,
    home_runs_model: LinearModel,
    away_runs_model: LinearModel,
    runline_model: LogisticModel,
    runline_calibrator: ProbabilityCalibrator,
    rows: list[DatasetRow],
    feature_names: list[str],
    earliest_prediction_date: date | None,
    fetch_cbs_odds: bool,
    market_weight: float,
) -> list[dict[str, Any]]:
    pending = [
        row
        for row in rows
        if row.target is None
        and (earliest_prediction_date is None or row.game_datetime.date() >= earliest_prediction_date)
    ]
    pending = sorted(pending, key=lambda row: row.game_datetime)
    predictions: list[dict[str, Any]] = []
    odds_cache: dict[tuple[str | None, str | None, str], MarketOdds] = {}
    for row in pending:
        feature_values = [safe_float(row.raw.get(name)) for name in feature_names]
        raw_home_prob = model.predict_proba(feature_values)
        home_prob = calibrator.calibrate(raw_home_prob)
        market_odds = MarketOdds(None, None, None, None)
        if fetch_cbs_odds:
            cache_key = (
                row.raw.get("away_team_abbrev"),
                row.raw.get("home_team_abbrev"),
                row.raw.get("game_date_utc", ""),
            )
            if cache_key not in odds_cache:
                odds_cache[cache_key] = fetch_cbs_market_odds(
                    row.raw.get("away_team_abbrev"),
                    row.raw.get("home_team_abbrev"),
                    row.game_datetime,
                )
            market_odds = odds_cache[cache_key]
            if market_odds.home_implied_prob is not None:
                home_prob = ((1.0 - market_weight) * home_prob) + (market_weight * market_odds.home_implied_prob)
                home_prob = min(max(home_prob, calibrator.min_prob), calibrator.max_prob)
        away_prob = 1.0 - home_prob
        predicted_home_runs = max(home_runs_model.predict(feature_values), 0.0)
        predicted_away_runs = max(away_runs_model.predict(feature_values), 0.0)
        predicted_total_runs = predicted_home_runs + predicted_away_runs
        predicted_run_diff = predicted_home_runs - predicted_away_runs
        home_cover_minus_1_5_prob = runline_calibrator.calibrate(runline_model.predict_proba(feature_values))
        away_cover_plus_1_5_prob = 1.0 - home_cover_minus_1_5_prob
        predicted_winner = row.raw["home_team_name"] if home_prob >= 0.5 else row.raw["away_team_name"]
        predictions.append(
            {
                "game_pk": row.raw["game_pk"],
                "game_date_utc": row.raw["game_date_utc"],
                "away_team_name": row.raw["away_team_name"],
                "home_team_name": row.raw["home_team_name"],
                "away_probable_pitcher_name": row.raw.get("away_probable_pitcher_name", ""),
                "home_probable_pitcher_name": row.raw.get("home_probable_pitcher_name", ""),
                "away_moneyline": market_odds.away_moneyline,
                "home_moneyline": market_odds.home_moneyline,
                "market_home_win_probability": round(market_odds.home_implied_prob, 4) if market_odds.home_implied_prob is not None else None,
                "market_away_win_probability": round(market_odds.away_implied_prob, 4) if market_odds.away_implied_prob is not None else None,
                "home_win_probability": round(home_prob, 4),
                "away_win_probability": round(away_prob, 4),
                "predicted_home_runs": round(predicted_home_runs, 3),
                "predicted_away_runs": round(predicted_away_runs, 3),
                "predicted_total_runs": round(predicted_total_runs, 3),
                "predicted_run_diff": round(predicted_run_diff, 3),
                "home_cover_minus_1_5_probability": round(home_cover_minus_1_5_prob, 4),
                "away_cover_plus_1_5_probability": round(away_cover_plus_1_5_prob, 4),
                "predicted_runline_side": f"{row.raw['home_team_name']} -1.5" if home_cover_minus_1_5_prob >= 0.5 else f"{row.raw['away_team_name']} +1.5",
                "predicted_winner": predicted_winner,
                "prediction_confidence": round(max(home_prob, away_prob), 4),
            }
        )
    return predictions


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train a simple MLB outcome model from exported game features and predict unresolved games."
    )
    parser.add_argument(
        "--input-csv",
        default="outputs/mlb_game_features.csv",
        help="Path to the game feature CSV produced by mlb_model_builder.py",
    )
    parser.add_argument(
        "--predict-csv",
        default=None,
        help="Optional separate feature CSV to score with the trained model.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory for predictions, model metadata, and notes.",
    )
    parser.add_argument("--validation-fraction", type=float, default=0.2, help="Fraction of finalized games reserved for validation.")
    parser.add_argument("--learning-rate", type=float, default=0.05, help="Gradient descent learning rate.")
    parser.add_argument("--epochs", type=int, default=2000, help="Training epochs for logistic regression.")
    parser.add_argument("--l2-penalty", type=float, default=0.001, help="L2 regularization strength.")
    parser.add_argument("--calibration-epochs", type=int, default=1000, help="Epochs for Platt-style probability calibration.")
    parser.add_argument("--min-probability", type=float, default=0.05, help="Lower probability cap after calibration.")
    parser.add_argument("--max-probability", type=float, default=0.95, help="Upper probability cap after calibration.")
    parser.add_argument("--fetch-cbs-odds", action="store_true", help="Fetch CBS Sports moneylines and blend them into predictions.")
    parser.add_argument("--market-weight", type=float, default=0.5, help="Weight assigned to market implied probabilities when available.")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for initial model weights.")
    parser.add_argument(
        "--prediction-start-date",
        default=date.today().isoformat(),
        help="Only score unresolved games on or after this YYYY-MM-DD date.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    input_csv = Path(args.input_csv)
    if not input_csv.exists():
        raise SystemExit(f"Input CSV not found: {input_csv}")
    prediction_start_date = date.fromisoformat(args.prediction_start_date) if args.prediction_start_date else None

    rows = load_rows(input_csv)
    feature_names = choose_feature_names(rows)
    if not feature_names:
        raise SystemExit("No numeric modeling features were found in the CSV.")

    train_rows, validation_rows = chronological_split(rows, args.validation_fraction)
    train_matrix = build_matrix(train_rows, feature_names)
    train_targets = [row.target for row in train_rows if row.target is not None]
    train_home_runs = [safe_float(row.raw.get("home_score")) or 0.0 for row in train_rows]
    train_away_runs = [safe_float(row.raw.get("away_score")) or 0.0 for row in train_rows]
    train_runline_targets = [1 if (train_home - train_away) > 1.5 else 0 for train_home, train_away in zip(train_home_runs, train_away_runs)]
    model = train_logistic_regression(
        matrix=train_matrix,
        targets=train_targets,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2_penalty=args.l2_penalty,
        seed=args.seed,
    )
    model.feature_names = feature_names
    home_runs_model = train_linear_regression(
        matrix=train_matrix,
        targets=train_home_runs,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2_penalty=args.l2_penalty,
        seed=args.seed + 11,
    )
    home_runs_model.feature_names = feature_names
    away_runs_model = train_linear_regression(
        matrix=train_matrix,
        targets=train_away_runs,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2_penalty=args.l2_penalty,
        seed=args.seed + 17,
    )
    away_runs_model.feature_names = feature_names
    runline_model = train_logistic_regression(
        matrix=train_matrix,
        targets=train_runline_targets,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2_penalty=args.l2_penalty,
        seed=args.seed + 23,
    )
    runline_model.feature_names = feature_names

    validation_matrix = build_matrix(validation_rows, feature_names)
    validation_targets = [row.target for row in validation_rows if row.target is not None]
    validation_probs = [model.predict_proba(row) for row in validation_matrix]
    validation_home_runs_actual = [safe_float(row.raw.get("home_score")) or 0.0 for row in validation_rows]
    validation_away_runs_actual = [safe_float(row.raw.get("away_score")) or 0.0 for row in validation_rows]
    validation_total_runs_actual = [home + away for home, away in zip(validation_home_runs_actual, validation_away_runs_actual)]
    validation_home_runs_pred = [max(home_runs_model.predict(row), 0.0) for row in validation_matrix]
    validation_away_runs_pred = [max(away_runs_model.predict(row), 0.0) for row in validation_matrix]
    validation_total_runs_pred = [home + away for home, away in zip(validation_home_runs_pred, validation_away_runs_pred)]
    validation_runline_targets = [1 if (home - away) > 1.5 else 0 for home, away in zip(validation_home_runs_actual, validation_away_runs_actual)]
    validation_runline_probs = [runline_model.predict_proba(row) for row in validation_matrix]
    calibrator = fit_probability_calibrator(
        validation_targets,
        validation_probs,
        epochs=args.calibration_epochs,
        learning_rate=args.learning_rate,
        min_prob=args.min_probability,
        max_prob=args.max_probability,
    )
    runline_calibrator = fit_probability_calibrator(
        validation_runline_targets,
        validation_runline_probs,
        epochs=args.calibration_epochs,
        learning_rate=args.learning_rate,
        min_prob=args.min_probability,
        max_prob=args.max_probability,
    )
    calibrated_validation_probs = [calibrator.calibrate(prob) for prob in validation_probs]
    calibrated_runline_probs = [runline_calibrator.calibrate(prob) for prob in validation_runline_probs]
    metrics = {
        "accuracy": accuracy_score(validation_targets, validation_probs),
        "log_loss": log_loss(validation_targets, validation_probs),
        "brier_score": brier_score(validation_targets, validation_probs),
        "calibrated_log_loss": log_loss(validation_targets, calibrated_validation_probs),
        "calibrated_brier_score": brier_score(validation_targets, calibrated_validation_probs),
        "home_runs_mae": mae(validation_home_runs_actual, validation_home_runs_pred),
        "away_runs_mae": mae(validation_away_runs_actual, validation_away_runs_pred),
        "total_runs_mae": mae(validation_total_runs_actual, validation_total_runs_pred),
        "total_runs_rmse": rmse(validation_total_runs_actual, validation_total_runs_pred),
        "runline_accuracy": accuracy_score(validation_runline_targets, calibrated_runline_probs),
        "runline_log_loss": log_loss(validation_runline_targets, calibrated_runline_probs),
        "train_games": float(len(train_rows)),
        "validation_games": float(len(validation_rows)),
    }

    full_finalized = sorted([row for row in rows if row.target is not None], key=lambda row: row.game_datetime)
    full_matrix = build_matrix(full_finalized, feature_names)
    full_targets = [row.target for row in full_finalized if row.target is not None]
    full_home_runs = [safe_float(row.raw.get("home_score")) or 0.0 for row in full_finalized]
    full_away_runs = [safe_float(row.raw.get("away_score")) or 0.0 for row in full_finalized]
    full_runline_targets = [1 if (home - away) > 1.5 else 0 for home, away in zip(full_home_runs, full_away_runs)]
    final_model = train_logistic_regression(
        matrix=full_matrix,
        targets=full_targets,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2_penalty=args.l2_penalty,
        seed=args.seed,
    )
    final_model.feature_names = feature_names
    final_home_runs_model = train_linear_regression(
        matrix=full_matrix,
        targets=full_home_runs,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2_penalty=args.l2_penalty,
        seed=args.seed + 11,
    )
    final_home_runs_model.feature_names = feature_names
    final_away_runs_model = train_linear_regression(
        matrix=full_matrix,
        targets=full_away_runs,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2_penalty=args.l2_penalty,
        seed=args.seed + 17,
    )
    final_away_runs_model.feature_names = feature_names
    final_runline_model = train_logistic_regression(
        matrix=full_matrix,
        targets=full_runline_targets,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2_penalty=args.l2_penalty,
        seed=args.seed + 23,
    )
    final_runline_model.feature_names = feature_names

    prediction_rows = rows
    if args.predict_csv:
        predict_csv = Path(args.predict_csv)
        if not predict_csv.exists():
            raise SystemExit(f"Prediction CSV not found: {predict_csv}")
        prediction_rows = load_rows(predict_csv)
    predictions = build_predictions(
        final_model,
        calibrator,
        final_home_runs_model,
        final_away_runs_model,
        final_runline_model,
        runline_calibrator,
        prediction_rows,
        feature_names,
        prediction_start_date,
        args.fetch_cbs_odds,
        args.market_weight,
    )
    top_features = sorted(
        zip(final_model.feature_names, final_model.weights),
        key=lambda item: abs(item[1]),
        reverse=True,
    )[:15]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_csv = output_dir / "mlb_predictions.csv"
    model_json = output_dir / "mlb_model.json"
    notes_md = output_dir / "mlb_predictions.md"

    write_csv(predictions_csv, predictions)
    model_json.write_text(
        json.dumps(
            {
                "metrics": metrics,
                "moneyline_model": final_model.to_dict(),
                "moneyline_calibrator": calibrator.to_dict(),
                "home_runs_model": final_home_runs_model.to_dict(),
                "away_runs_model": final_away_runs_model.to_dict(),
                "runline_model": final_runline_model.to_dict(),
                "runline_calibrator": runline_calibrator.to_dict(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_markdown(notes_md, metrics, predictions, top_features, args)

    print(f"Validation accuracy: {metrics['accuracy']:.4f}")
    print(f"Validation log loss: {metrics['log_loss']:.4f}")
    print(f"Wrote predictions to {predictions_csv}")
    print(f"Wrote model metadata to {model_json}")
    print(f"Wrote prediction notes to {notes_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
