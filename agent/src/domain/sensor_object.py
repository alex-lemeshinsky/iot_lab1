from dataclasses import dataclass, field
from typing import Any

from domain.gps import Gps


@dataclass
class SensorObject:
    object_id: str
    object_type: str
    name: str
    gps: Gps
    metadata: dict[str, Any] = field(default_factory=dict)
