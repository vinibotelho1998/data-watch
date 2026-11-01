import csv
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from data_watch.api import create_app
from data_watch.generate import generate
from data_watch.model import evaluate, read_csv, score, train
from data_watch.schema import Metric
from data_watch.store import ConflictError, connect, ingest, initialize, list_anomalies


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    root = tmp_path_factory.mktemp("data-watch")
    generate(root / "data")
    bundle = train(root / "data/history.csv", root / "model.joblib")
    rows, _ = read_csv(root / "data/replay.csv")
    return root, bundle, rows


def test_temporal_holdout_and_honest_evaluation(trained):
    root, bundle, _ = trained
    report = evaluate(bundle, root / "data/replay.csv", root / "report.json")
    assert report["evaluation_rows"] == 120
    assert report["injected_anomalies"] == 12
    assert sum(map(sum, report["isolation_forest"]["confusion_matrix"])) == 120
    assert 0 < report["isolation_forest"]["recall"] <= 1
    with pytest.raises(ValueError, match="posteriores"):
        evaluate(bundle, root / "data/history.csv", root / "invalid.json")


def test_labels_do_not_affect_fitted_detector(trained, tmp_path):
    root, bundle, rows = trained
    _, originals = read_csv(root / "data/history.csv")
    for row in originals:
        row["is_anomaly"] = "1"
        row["anomaly_kind"] = "changed-label-only"
    altered = tmp_path / "history.csv"
    with altered.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=originals[0].keys())
        writer.writeheader()
        writer.writerows(originals)
    changed = train(altered, tmp_path / "model.joblib")
    np.testing.assert_array_equal(score(bundle, rows)[0], score(changed, rows)[0])
    assert bundle["threshold"] == changed["threshold"]


def test_evaluation_accepts_csv_without_optional_metadata(trained, tmp_path):
    root, bundle, _ = trained
    _, originals = read_csv(root / "data/replay.csv")
    columns = [*Metric.model_fields, "is_anomaly"]
    minimal = tmp_path / "minimal.csv"
    with minimal.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(originals)
    report = evaluate(bundle, minimal, tmp_path / "minimal-report.json")
    assert report["evaluation_rows"] == 120
    assert {event["injected_kind"] for event in report["events"]} == {"unspecified"}


def test_idempotent_replay(trained, tmp_path):
    _, bundle, rows = trained
    db = tmp_path / "metrics.db"
    initialize(db)
    first = ingest(db, bundle, rows)
    second = ingest(db, bundle, rows)
    assert first["inserted"] == 120
    assert second["inserted"] == 0 and second["duplicates"] == 120
    assert second["new_anomalies"] == []
    assert len(list_anomalies(db)) == len(first["new_anomalies"])


def test_conflict_rolls_back_entire_batch(trained, tmp_path):
    _, bundle, rows = trained
    db = tmp_path / "metrics.db"
    initialize(db)
    ingest(db, bundle, [rows[0]])
    changed = rows[0].model_copy(update={"latency_ms": rows[0].latency_ms + 1})
    with pytest.raises(ConflictError):
        ingest(db, bundle, [rows[1], changed])
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 1


def test_concurrent_retries_insert_once(trained, tmp_path):
    _, bundle, rows = trained
    db = tmp_path / "concurrent.db"
    initialize(db)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ingest(db, bundle, rows[:10]), range(4)))
    assert sum(result["inserted"] for result in results) == 10
    assert sum(result["duplicates"] for result in results) == 30


@pytest.mark.parametrize("changes", [
    {"timestamp": "2025-01-04T00:00:00"}, {"requests": 0}, {"requests": True},
    {"error_count": 10000}, {"latency_ms": "NaN"}, {"cpu_percent": 101}, {"unexpected": "field"},
])
def test_invalid_metrics_rejected(trained, changes):
    payload = trained[2][0].model_dump(mode="json") | changes
    with pytest.raises(ValidationError):
        Metric.model_validate(payload)


def test_api_ingestion_conflict_validation_and_pagination(trained, tmp_path):
    root, _, rows = trained
    payload = {"rows": [row.model_dump(mode="json") for row in rows]}
    with TestClient(create_app(root / "model.joblib", tmp_path / "api.db")) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/model").json()["series_id"] == "demo-api"
        first = client.post("/ingest", json=payload)
        assert first.status_code == 200 and first.json()["inserted"] == 120
        assert client.post("/ingest", json=payload).json()["duplicates"] == 120
        payload["rows"][0]["latency_ms"] += 1
        assert client.post("/ingest", json=payload).status_code == 409
        payload["rows"][0]["error_count"] = 999999
        assert client.post("/ingest", json=payload).status_code == 422
        assert len(client.get("/anomalies?limit=2").json()["items"]) == 2
        assert client.get("/anomalies?limit=0").status_code == 422


def test_unknown_series_rejected_without_inserts(trained, tmp_path):
    _, bundle, rows = trained
    db = tmp_path / "metrics.db"
    initialize(db)
    with pytest.raises(ValueError, match="somente"):
        ingest(db, bundle, [rows[0].model_copy(update={"series_id": "another-service"})])
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 0


def test_missing_model_is_not_ready(tmp_path):
    with TestClient(create_app(tmp_path / "missing.joblib", tmp_path / "metrics.db")) as client:
        assert client.get("/health").status_code == 503


def test_generator_is_reproducible(tmp_path):
    generate(tmp_path / "a")
    generate(tmp_path / "b")
    assert (tmp_path / "a/history.csv").read_bytes() == (tmp_path / "b/history.csv").read_bytes()
    assert (tmp_path / "a/replay.csv").read_bytes() == (tmp_path / "b/replay.csv").read_bytes()

