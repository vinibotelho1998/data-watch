"""Teste HTTP real de ingestão, alerta, retry idempotente, conflito e validação."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def post(url: str, payload: dict) -> tuple[int, dict]:
    request = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        response = urlopen(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        body = json.loads(response.read().decode())
        if not isinstance(body, dict):
            raise AssertionError(f"Esperado objeto JSON, recebido {body!r}")
        return response.status, body


def verify(base_url: str) -> list[dict]:
    url = base_url.rstrip("/") + "/webhook/data-watch-ingest"
    row = {"series_id": "demo-api", "timestamp": datetime.now(timezone.utc).isoformat(),
           "requests": 9000, "error_count": 4000, "latency_ms": 9000.0, "cpu_percent": 99.0}
    results = []
    status, body = post(url, {"rows": [row]})
    assert status == 200, (status, body)
    assert body["inserted"] == 1 and body["duplicates"] == 0, body
    assert body["alert_count"] == len(body["alerts"]) == 1, body
    assert body["alerts"][0]["anomaly_score"] > body["alerts"][0]["threshold"], body
    results.append({"case": "insert_and_alert", "status": status, "inserted": body["inserted"], "alert_count": body["alert_count"]})

    status, body = post(url, {"rows": [row]})
    assert status == 200 and body["inserted"] == 0 and body["duplicates"] == 1, (status, body)
    assert body["alert_count"] == 0 and body["alerts"] == [], body
    results.append({"case": "idempotent_retry", "status": status, "duplicates": 1, "alert_count": 0})

    status, body = post(url, {"rows": [row | {"latency_ms": 8000.0}]})
    assert status == 409 and isinstance(body.get("detail"), str), (status, body)
    results.append({"case": "conflicting_payload", "status": status})

    status, body = post(url, {"rows": [row | {"error_count": 999999}]})
    assert status == 422 and isinstance(body.get("detail"), list), (status, body)
    results.append({"case": "invalid_metric", "status": status})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5678")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "base_url": args.base_url,
              "workflow_id": "portfolioWatch05", "transport": "real HTTP; no mocks", "cases": verify(args.base_url)}
    report["status"] = "passed"
    content = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(content, encoding="utf-8")
    print(content)

