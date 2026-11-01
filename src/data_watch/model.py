import csv
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

from data_watch.schema import FEATURES, Metric, feature_matrix


def read_csv(path: Path) -> tuple[list[Metric], list[dict]]:
    with path.open(encoding="utf-8", newline="") as handle:
        raw = list(csv.DictReader(handle))
    required = set(Metric.model_fields)
    if not raw or not required.issubset(raw[0]):
        raise ValueError(f"CSV vazio ou sem colunas obrigatórias: {sorted(required)}")
    rows = []
    for line, row in enumerate(raw, 2):
        try:
            values = {name: row[name] for name in required}
            for name in ("requests", "error_count"):
                values[name] = int(values[name])
            for name in ("latency_ms", "cpu_percent"):
                values[name] = float(values[name])
            rows.append(Metric.model_validate(values))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Linha {line} inválida: {exc}") from exc
    return rows, raw


def train(history_path: Path, output: Path, seed: int = 42, quantile: float = 0.98) -> dict:
    rows, _ = read_csv(history_path)
    if len(rows) < 100:
        raise ValueError("Histórico deve conter ao menos 100 pontos")
    if not 0.9 <= quantile < 1:
        raise ValueError("quantile deve estar entre 0.9 e 1, exclusivo")
    if len({(row.series_id, row.timestamp) for row in rows}) != len(rows):
        raise ValueError("Histórico contém chaves duplicadas")
    series = {row.series_id for row in rows}
    if len(series) != 1:
        raise ValueError("Este modelo atende uma série por vez")
    matrix = feature_matrix(rows)
    estimator = IsolationForest(n_estimators=200, random_state=seed, contamination="auto", n_jobs=1)
    estimator.fit(matrix)
    scores = -estimator.score_samples(matrix)
    threshold = float(np.quantile(scores, quantile))
    data_hash = hashlib.sha256(history_path.read_bytes()).hexdigest()
    version = hashlib.sha256(f"iforest-v1:{seed}:{quantile}:{data_hash}:{sklearn.__version__}".encode()).hexdigest()[:16]
    bundle = {
        "estimator": estimator, "threshold": threshold, "model_version": version,
        "trained_until": max(row.timestamp for row in rows).isoformat(),
        "trained_from": min(row.timestamp for row in rows).isoformat(), "series_id": next(iter(series)),
        "features": FEATURES, "seed": seed, "threshold_quantile": quantile,
        "history_rows": len(rows), "history_sha256": data_hash, "sklearn_version": sklearn.__version__,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, output)
    return bundle


def score(bundle: dict, rows: list[Metric]):
    scores = -bundle["estimator"].score_samples(feature_matrix(rows))
    return scores, scores > bundle["threshold"]


def require_future(bundle: dict, rows: list[Metric]):
    from datetime import datetime
    cutoff = datetime.fromisoformat(bundle["trained_until"])
    for row in rows:
        if row.series_id != bundle["series_id"]:
            raise ValueError(f"Modelo atende somente a série {bundle['series_id']}")
        if row.timestamp <= cutoff:
            raise ValueError("Novos pontos devem ser posteriores ao histórico de treinamento")


def evaluate(bundle: dict, replay_path: Path, output: Path) -> dict:
    rows, raw = read_csv(replay_path)
    require_future(bundle, rows)
    if len({(row.series_id, row.timestamp) for row in rows}) != len(rows):
        raise ValueError("Replay de avaliação contém chaves duplicadas")
    if any(row.get("is_anomaly") not in ("0", "1") for row in raw):
        raise ValueError("Avaliação requer is_anomaly 0/1; rótulo nunca é usado no treinamento")
    truth = np.array([int(row["is_anomaly"]) for row in raw])
    scores, predicted = score(bundle, rows)
    # Baseline sem aprendizagem, com limites fixados no código antes do replay.
    baseline = np.array([row.latency_ms > 300 or row.error_count / row.requests > 0.1 or row.cpu_percent > 90 for row in rows])
    def metrics(values):
        return {"precision": float(precision_score(truth, values, zero_division=0)),
                "recall": float(recall_score(truth, values, zero_division=0)),
                "f1": float(f1_score(truth, values, zero_division=0)),
                "confusion_matrix": confusion_matrix(truth, values, labels=[0, 1]).tolist()}
    report = {
        "model": {key: value for key, value in bundle.items() if key != "estimator"},
        "replay_sha256": hashlib.sha256(replay_path.read_bytes()).hexdigest(),
        "evaluation_rows": len(rows), "injected_anomalies": int(truth.sum()),
        "isolation_forest": metrics(predicted), "fixed_rule_baseline": metrics(baseline),
        "baseline_rule": "latency_ms > 300 OR error_rate > 0.10 OR cpu_percent > 90",
        "threshold_policy": "Quantil de scores do histórico; replay e seus rótulos não ajustam modelo ou limiar",
        "data_source": "100% sintético, com falhas injetadas explicitamente no replay",
        "limitation": "Métricas não medem incidentes reais; o baseline pode superar o modelo em falhas óbvias.",
        "events": [{"timestamp": row.timestamp.isoformat(), "score": float(value), "is_anomaly": bool(flag),
                    "expected": bool(actual), "injected_kind": original.get("anomaly_kind", "unspecified")}
                   for row, value, flag, actual, original in zip(rows, scores, predicted, truth, raw)],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report

