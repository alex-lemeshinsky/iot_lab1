from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.entities.agent_data import GpsData


class SensorObject(BaseModel):
    object_id: str
    object_type: str
    name: str
    gps: GpsData
    metadata: dict[str, Any] = Field(default_factory=dict)


class SensorReading(BaseModel):
    sensor_object: SensorObject
    sensor_type: str
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "synthetic_open_dataset_profile"
    quality: str = "ok"

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value):
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError(
                "Invalid timestamp format. Expected ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)."
            )
