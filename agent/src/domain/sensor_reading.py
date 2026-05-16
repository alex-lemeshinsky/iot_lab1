from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from domain.sensor_object import SensorObject


@dataclass
class SensorReading:
    sensor_object: SensorObject
    sensor_type: str
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "synthetic_open_dataset_profile"
    quality: str = "ok"
