from datetime import datetime, timezone

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FEATURES = ["requests", "error_rate", "latency_ms", "cpu_percent"]


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    series_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    timestamp: datetime
    requests: int = Field(ge=1, le=1_000_000_000, strict=True)
    error_count: int = Field(ge=0, strict=True)
    latency_ms: float = Field(gt=0, le=1_000_000)
    cpu_percent: float = Field(ge=0, le=100)

    @field_validator("timestamp")
    @classmethod
    def timezone_required(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp deve incluir timezone, por exemplo 2025-01-04T00:00:00Z")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def errors_cannot_exceed_requests(self):
        if self.error_count > self.requests:
            raise ValueError("error_count não pode ser maior que requests")
        return self


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[Metric] = Field(min_length=1, max_length=1000)


def feature_matrix(rows: list[Metric]):
    return np.array([[row.requests, row.error_count / row.requests, row.latency_ms, row.cpu_percent] for row in rows], dtype=float)

