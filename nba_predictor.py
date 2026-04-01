#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


EXCLUDED_COLUMNS = {
    "game_id",
    "game_date_utc",
    "status",
    "venue_name",
    "home_team_id",
    "home_team_name",
    "home_team_abbr",
    "away_team_id",
    "away_team_name",
    "away_team_abbr",
    "home_score",
    "away_score",
    "target_home_team_win",
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


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def load_rows(csv_path: Path) -> list[DatasetRow]:
    rows: list[DatasetRow] = []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            target_value = raw.get("target_home_team_win")
            target = None if target_value in (None, "", "None") else int(float(target_value))
            rows.append(DatasetRow(raw=raw, target=target, game_datetime=parse_datetime(raw["game_date_utc"])))
    return rows


def choose_feature_names(rows: list[DatasetRow]) -> list[str]:
    if not rows:
        return []
    feature_names: list[str] = []
    for key in rows[0].raw.keys():
        if key in EXCLUDED_COLUMNS:
            continue
        if key.endswith("_conference") or key.endswith("_division"):
            continue
        if any(safe_float(row.raw.get(key)) is not None for row in rows):
            feature_names.append(key)
    return feature_names


def make_diff_feature_names(feature_names: list[str]) -> list[tuple[str, str, str]]:
    diff_specs: list[tuple[str, str, str]] = []
    for name in feature_names:
        if name.startswith("home_"):
            counterpart = "away_" + name[len("home_") :]
            if counterpart in feature_names:
                diff_specs.append((f"diff_{name[len('home_'):]}", name, counterpart))
    return diff_specs


def feature_value_map(raw: dict[str, str], feature_names: list[str], diff_specs: list[tuple[str, str, str]]) -> dict[str, float | None]:
    values = {name: safe_float(raw.get(name)) for name in feature_names}
    for diff_name, home_name, away_name in diff_specs:
        home_value = values.get(home_name)
        away_value = values.get(away_name)
        values[diff_name] = (home_value - away_value) if home_value is not None and away_value is not None else None
    return values


def build_matrix(
    rows: list[DatasetRow],
    feature_names: list[str],
    diff_specs: list[tuple[str, str, str]],
    expanded_feature_names: list[str],
) -> list[list[float | None]]:
    matrix: list[list[float | None]] = []
    for row in rows:
        value_map = feature_value_map(row.raw, feature_names, diff_specs)
        matrix.append([value_map.get(name) for name in expanded_feature_names])
    return matrix


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
        means.append(mean_value)
        scales.append(math.sqrt(variance) if variance > 1e-9 else 1.0)
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


def chronological_split(rows: list[DatasetRow], validation_fraction: float) -> tuple[list[DatasetRow], list[DatasetRow]]:
    finalized = sorted([row for row in rows if row.target is not None], key=lambda row: row.game_datetime)
    if len(finalized) < 30:
        raise ValueError("Not enough finalized NBA games to train a model yet. Build a larger historical dataset first.")
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
        "# NBA Prediction Run",
        "",
        f"- Generated at: {datetime.now(UTC).isoformat()}",
        f"- Training file: {args.input_csv}",
        f"- Prediction file: {args.predict_csv or args.input_csv}",
        f"- Validation fraction: {args.validation_fraction}",
        f"- Prediction start date: {args.prediction_start_date}",
        f"- Learning rate: {args.learning_rate}",
        f"- Epochs: {args.epochs}",
        f"- L2 penalty: {args.l2_penalty}",
        "",
        "## Validation Metrics",
        "",
        f"- Accuracy: {metrics['accuracy']:.4f}",
        f"- Log loss: {metrics['log_loss']:.4f}",
        f"- Brier score: {metrics['brier_score']:.4f}",
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
    lines.extend(["", "## Upcoming Predictions", ""])
    if predictions:
        for row in predictions[: min(20, len(predictions))]:
            lines.append(
                f"- {row['game_date_utc']} | {row['away_team_name']} at {row['home_team_name']} | "
                f"home_win_prob={row['home_win_probability']} | pick={row['predicted_winner']}"
            )
    else:
        lines.append("- No future or unresolved games were present in the input file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_predictions(
    model: LogisticModel,
    rows: list[DatasetRow],
    feature_names: list[str],
    diff_specs: list[tuple[str, str, str]],
    expanded_feature_names: list[str],
    earliest_prediction_date: date | None,
) -> list[dict[str, Any]]:
    pending = [
        row
        for row in rows
        if row.target is None and (earliest_prediction_date is None or row.game_datetime.date() >= earliest_prediction_date)
    ]
    pending = sorted(pending, key=lambda row: row.game_datetime)
    predictions: list[dict[str, Any]] = []
    for row in pending:
        value_map = feature_value_map(row.raw, feature_names, diff_specs)
        feature_values = [value_map.get(name) for name in expanded_feature_names]
        home_prob = model.predict_proba(feature_values)
        away_prob = 1.0 - home_prob
        predicted_winner = row.raw["home_team_name"] if home_prob >= 0.5 else row.raw["away_team_name"]
        predictions.append(
            {
                "game_id": row.raw["game_id"],
                "game_date_utc": row.raw["game_date_utc"],
                "away_team_name": row.raw["away_team_name"],
                "home_team_name": row.raw["home_team_name"],
                "market_home_spread": row.raw.get("market_home_spread", ""),
                "market_total": row.raw.get("market_total", ""),
                "home_win_probability": round(home_prob, 4),
                "away_win_probability": round(away_prob, 4),
                "predicted_winner": predicted_winner,
                "prediction_confidence": round(max(home_prob, away_prob), 4),
            }
        )
    return predictions


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train an NBA outcome model from exported game features and predict unresolved games."
    )
    parser.add_argument("--input-csv", default="outputs_nba/nba_game_features.csv", help="Path to the feature CSV produced by nba_model_builder.py")
    parser.add_argument("--predict-csv", default=None, help="Optional separate feature CSV to score with the trained model.")
    parser.add_argument("--output-dir", default="outputs_nba", help="Directory for predictions, model metadata, and notes.")
    parser.add_argument("--validation-fraction", type=float, default=0.2, help="Fraction of finalized games reserved for validation.")
    parser.add_argument("--learning-rate", type=float, default=0.03, help="Gradient descent learning rate.")
    parser.add_argument("--epochs", type=int, default=3000, help="Training epochs for logistic regression.")
    parser.add_argument("--l2-penalty", type=float, default=0.002, help="L2 regularization strength.")
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
    diff_specs = make_diff_feature_names(feature_names)
    expanded_feature_names = feature_names + [name for name, _, _ in diff_specs]

    train_rows, validation_rows = chronological_split(rows, args.validation_fraction)
    train_matrix = build_matrix(train_rows, feature_names, diff_specs, expanded_feature_names)
    train_targets = [row.target for row in train_rows if row.target is not None]
    model = train_logistic_regression(
        matrix=train_matrix,
        targets=train_targets,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2_penalty=args.l2_penalty,
        seed=args.seed,
    )
    model.feature_names = expanded_feature_names

    validation_matrix = build_matrix(validation_rows, feature_names, diff_specs, expanded_feature_names)
    validation_targets = [row.target for row in validation_rows if row.target is not None]
    validation_probs = [model.predict_proba(row) for row in validation_matrix]
    metrics = {
        "accuracy": accuracy_score(validation_targets, validation_probs),
        "log_loss": log_loss(validation_targets, validation_probs),
        "brier_score": brier_score(validation_targets, validation_probs),
        "train_games": float(len(train_rows)),
        "validation_games": float(len(validation_rows)),
    }

    full_finalized = sorted([row for row in rows if row.target is not None], key=lambda row: row.game_datetime)
    full_matrix = build_matrix(full_finalized, feature_names, diff_specs, expanded_feature_names)
    full_targets = [row.target for row in full_finalized if row.target is not None]
    final_model = train_logistic_regression(
        matrix=full_matrix,
        targets=full_targets,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        l2_penalty=args.l2_penalty,
        seed=args.seed,
    )
    final_model.feature_names = expanded_feature_names

    prediction_rows = rows
    if args.predict_csv:
        predict_csv = Path(args.predict_csv)
        if not predict_csv.exists():
            raise SystemExit(f"Prediction CSV not found: {predict_csv}")
        prediction_rows = load_rows(predict_csv)
    predictions = build_predictions(
        final_model,
        prediction_rows,
        feature_names,
        diff_specs,
        expanded_feature_names,
        prediction_start_date,
    )
    top_features = sorted(zip(final_model.feature_names, final_model.weights), key=lambda item: abs(item[1]), reverse=True)[:20]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_csv = output_dir / "nba_predictions.csv"
    model_json = output_dir / "nba_model.json"
    notes_md = output_dir / "nba_predictions.md"

    write_csv(predictions_csv, predictions)
    model_json.write_text(json.dumps({"metrics": metrics, "model": final_model.to_dict()}, indent=2), encoding="utf-8")
    write_markdown(notes_md, metrics, predictions, top_features, args)

    print(f"Validation accuracy: {metrics['accuracy']:.4f}")
    print(f"Validation log loss: {metrics['log_loss']:.4f}")
    print(f"Wrote predictions to {predictions_csv}")
    print(f"Wrote model metadata to {model_json}")
    print(f"Wrote prediction notes to {notes_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
