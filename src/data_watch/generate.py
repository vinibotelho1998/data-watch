"""Métricas e incidentes artificiais para demonstrar o fluxo completo."""

import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np


def generate(directory: Path, seed: int = 42):
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    history, replay = [], []
    injected_indices = {8, 19, 27, 34, 48, 59, 68, 79, 88, 98, 107, 116}
    kinds = ["latency_spike", "error_burst", "traffic_spike", "cpu_saturation"]
    for index in range(720):
        daily = np.sin(2 * np.pi * index / 288)
        requests = max(50, int(rng.normal(220 + 35 * daily, 18)))
        row = {
            "series_id": "demo-api", "timestamp": (start + timedelta(minutes=5 * index)).isoformat(),
            "requests": requests, "error_count": int(rng.binomial(requests, 0.015)),
            "latency_ms": round(max(10, rng.normal(130 + 8 * daily, 12)), 3),
            "cpu_percent": round(float(np.clip(rng.normal(42 + 5 * daily, 4), 1, 95)), 3),
            "is_anomaly": 0, "anomaly_kind": "none", "source": "synthetic-generator-v1",
        }
        replay_index = index - 600
        if index >= 600 and replay_index in injected_indices:
            kind = kinds[sorted(injected_indices).index(replay_index) % len(kinds)]
            row["is_anomaly"], row["anomaly_kind"] = 1, kind
            if kind == "latency_spike":
                row["latency_ms"] = round(row["latency_ms"] * 5, 3)
            elif kind == "error_burst":
                row["error_count"] = int(requests * 0.4)
            elif kind == "traffic_spike":
                row["requests"] = requests * 7
            else:
                row["cpu_percent"] = 99.0
        (history if index < 600 else replay).append(row)
    for filename, rows in (("history.csv", history), ("replay.csv", replay)):
        with (directory / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    return {"history_rows": len(history), "replay_rows": len(replay), "injected_anomalies": len(injected_indices)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(generate(args.output, args.seed))

