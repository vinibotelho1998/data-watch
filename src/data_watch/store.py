import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from data_watch.model import require_future, score
from data_watch.schema import Metric


class ConflictError(ValueError):
    """Uma chave existente foi reutilizada com conteúdo diferente."""


@contextmanager
def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path: Path):
    with connect(path) as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS metrics (
            series_id TEXT NOT NULL, timestamp TEXT NOT NULL, requests INTEGER NOT NULL,
            error_count INTEGER NOT NULL, latency_ms REAL NOT NULL, cpu_percent REAL NOT NULL,
            payload_sha256 TEXT NOT NULL, score REAL NOT NULL, is_anomaly INTEGER NOT NULL,
            model_version TEXT NOT NULL, PRIMARY KEY (series_id, timestamp)
        );
        CREATE INDEX IF NOT EXISTS idx_anomalies ON metrics(is_anomaly, timestamp DESC);
        """)


def ingest(path: Path, bundle: dict, rows: list[Metric]) -> dict:
    if not rows:
        raise ValueError("Lote vazio")
    if len(rows) > 1000:
        raise ValueError("Lote limitado a 1000 linhas")
    require_future(bundle, rows)
    scores, flags = score(bundle, rows)
    inserted, duplicates, anomalies = 0, 0, []
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        for row, anomaly_score, flag in zip(rows, scores, flags):
            payload = row.model_dump(mode="json")
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            previous = connection.execute("SELECT payload_sha256 FROM metrics WHERE series_id=? AND timestamp=?", (row.series_id, payload["timestamp"])).fetchone()
            if previous:
                if previous["payload_sha256"] != digest:
                    raise ConflictError(f"Chave {row.series_id}/{payload['timestamp']} já existe com outros valores")
                duplicates += 1
                continue
            connection.execute("INSERT INTO metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (row.series_id, payload["timestamp"], row.requests, row.error_count, row.latency_ms,
                                row.cpu_percent, digest, float(anomaly_score), int(flag), bundle["model_version"]))
            inserted += 1
            if flag:
                anomalies.append({**payload, "score": float(anomaly_score), "model_version": bundle["model_version"]})
    return {"inserted": inserted, "duplicates": duplicates, "new_anomalies": anomalies,
            "threshold": bundle["threshold"], "model_version": bundle["model_version"]}


def list_anomalies(path: Path, limit: int = 100, offset: int = 0) -> list[dict]:
    with connect(path) as connection:
        rows = connection.execute("SELECT * FROM metrics WHERE is_anomaly=1 ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [dict(row) for row in rows]

