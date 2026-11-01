import os
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from data_watch.schema import Batch
from data_watch.store import ConflictError, ingest, initialize, list_anomalies


def create_app(model_path: Path | None = None, db_path: Path | None = None):
    model_path = Path(model_path or os.getenv("DATA_WATCH_MODEL_PATH", "var/model.joblib"))
    db_path = Path(db_path or os.getenv("DATA_WATCH_DB_PATH", "var/metrics.sqlite3"))

    @asynccontextmanager
    async def lifespan(app):
        initialize(db_path)
        app.state.model = joblib.load(model_path) if model_path.is_file() else None
        yield

    app = FastAPI(title="Data Watch", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health():
        ready = app.state.model is not None
        return JSONResponse({"status": "ok" if ready else "model_missing"}, status_code=200 if ready else 503)

    @app.post("/ingest")
    def ingest_batch(payload: Batch):
        if app.state.model is None:
            raise HTTPException(503, "Treine o modelo antes de iniciar a API")
        try:
            return ingest(db_path, app.state.model, payload.rows)
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/anomalies")
    def anomalies(limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0)):
        return {"items": list_anomalies(db_path, limit, offset)}

    @app.get("/model")
    def model_card():
        if app.state.model is None:
            raise HTTPException(503, "Modelo ausente")
        return {key: value for key, value in app.state.model.items() if key != "estimator"}

    return app


app = create_app()

