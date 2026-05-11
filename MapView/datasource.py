from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import websockets

from config import STORE_HOST, STORE_PORT

try:
    from kivy import Logger
except ImportError:
    class Logger:
        @staticmethod
        def debug(message):
            print(message)

        @staticmethod
        def warning(message):
            print(message)


NORMAL_GRAVITY_Z = 16500
POTHOLE_Z_THRESHOLD = 12000
BUMP_Z_THRESHOLD = 20000
Y_AXIS_IMPACT_THRESHOLD = 5000


@dataclass(frozen=True)
class MapPoint:
    latitude: float
    longitude: float
    road_state: str
    timestamp: datetime | None = None
    source: str = "store"


def classify_road_state(x: float, y: float, z: float) -> str:
    if z <= POTHOLE_Z_THRESHOLD or y <= -Y_AXIS_IMPACT_THRESHOLD:
        return "pothole"

    if z >= BUMP_Z_THRESHOLD or y >= Y_AXIS_IMPACT_THRESHOLD:
        return "bump"

    if abs(z - NORMAL_GRAVITY_Z) >= Y_AXIS_IMPACT_THRESHOLD:
        return "bump"

    return "normal"


def parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    return None


def normalize_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    # Early lab CSV rows stored Kyiv coordinates with latitude/longitude labels swapped.
    if 20 <= latitude <= 40 and 45 <= longitude <= 55:
        return longitude, latitude

    return latitude, longitude


def _float_value(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return float(row[key])
    return None


def map_point_from_store_record(record: dict[str, Any], source: str = "store") -> MapPoint:
    if "agent_data" in record:
        agent_data = record["agent_data"]
        accelerometer = agent_data["accelerometer"]
        gps = agent_data["gps"]
        latitude = float(gps["latitude"])
        longitude = float(gps["longitude"])
        timestamp = parse_timestamp(agent_data.get("timestamp"))
        road_state = record["road_state"]
    else:
        latitude = float(record["latitude"])
        longitude = float(record["longitude"])
        timestamp = parse_timestamp(record.get("timestamp"))
        road_state = record["road_state"]
        accelerometer = {
            "x": record.get("x", 0),
            "y": record.get("y", 0),
            "z": record.get("z", NORMAL_GRAVITY_Z),
        }

    latitude, longitude = normalize_coordinates(latitude, longitude)
    if not road_state:
        road_state = classify_road_state(
            float(accelerometer["x"]),
            float(accelerometer["y"]),
            float(accelerometer["z"]),
        )

    return MapPoint(
        latitude=latitude,
        longitude=longitude,
        road_state=road_state,
        timestamp=timestamp,
        source=source,
    )


def user_id_from_store_record(record: dict[str, Any], fallback: int) -> int:
    if "agent_data" in record:
        return int(record["agent_data"].get("user_id", fallback))

    return int(record.get("user_id", fallback))


class FileDatasource:
    def __init__(self, accelerometer_filename: str, gps_filename: str | None = None):
        self.accelerometer_filename = Path(accelerometer_filename)
        self.gps_filename = Path(gps_filename) if gps_filename else None
        self.accelerometer_file = None
        self.gps_file = None
        self.accelerometer_reader = None
        self.gps_reader = None

    def start_reading(self):
        self.stop_reading()
        self.accelerometer_file = self.accelerometer_filename.open(
            "r", encoding="utf-8-sig", newline=""
        )
        self.accelerometer_reader = csv.DictReader(self.accelerometer_file)

        if self.gps_filename is not None:
            self.gps_file = self.gps_filename.open("r", encoding="utf-8-sig", newline="")
            self.gps_reader = csv.DictReader(self.gps_file)

    def stop_reading(self):
        for file_handle in (self.accelerometer_file, self.gps_file):
            if file_handle is not None:
                file_handle.close()

        self.accelerometer_file = None
        self.gps_file = None
        self.accelerometer_reader = None
        self.gps_reader = None

    def read_many(self, count: int) -> list[MapPoint]:
        return [self.read_next() for _ in range(count)]

    def read_next(self) -> MapPoint:
        if self.accelerometer_reader is None:
            self.start_reading()

        row = self._read_next_row("accelerometer_reader", self.accelerometer_file)
        if _float_value(row, "latitude", "lat") is not None:
            return self._map_point_from_processed_csv_row(row)

        gps_row = self._read_next_row("gps_reader", self.gps_file)
        x = _float_value(row, "x", "X")
        y = _float_value(row, "y", "Y")
        z = _float_value(row, "z", "Z")
        latitude = _float_value(gps_row, "latitude", "lat")
        longitude = _float_value(gps_row, "longitude", "lon", "lng")

        if None in (x, y, z, latitude, longitude):
            raise ValueError("CSV rows must contain accelerometer and GPS values")

        latitude, longitude = normalize_coordinates(latitude, longitude)
        return MapPoint(
            latitude=latitude,
            longitude=longitude,
            road_state=classify_road_state(x, y, z),
            timestamp=datetime.now(),
            source="csv",
        )

    def _map_point_from_processed_csv_row(self, row: dict[str, Any]) -> MapPoint:
        latitude = _float_value(row, "latitude", "lat")
        longitude = _float_value(row, "longitude", "lon", "lng")
        if latitude is None or longitude is None:
            raise ValueError("CSV row must contain latitude and longitude")

        x = _float_value(row, "x", "X") or 0
        y = _float_value(row, "y", "Y") or 0
        z = _float_value(row, "z", "Z") or NORMAL_GRAVITY_Z
        road_state = row.get("road_state") or classify_road_state(x, y, z)
        latitude, longitude = normalize_coordinates(latitude, longitude)

        return MapPoint(
            latitude=latitude,
            longitude=longitude,
            road_state=road_state,
            timestamp=parse_timestamp(row.get("timestamp")),
            source="csv",
        )

    def _read_next_row(self, reader_attr: str, file_handle):
        reader = getattr(self, reader_attr)
        if reader is None or file_handle is None:
            raise ValueError("Datasource reader was not initialized")

        try:
            return next(reader)
        except StopIteration:
            file_handle.seek(0)
            setattr(self, reader_attr, csv.DictReader(file_handle))
            return next(getattr(self, reader_attr))


class StoreDatasource:
    def __init__(
        self,
        user_id: int,
        host: str = STORE_HOST,
        port: int = STORE_PORT,
        preload_limit: int = 80,
        reconnect_delay: float = 2.0,
    ):
        self.user_id = user_id
        self.host = host
        self.port = int(port)
        self.preload_limit = preload_limit
        self.reconnect_delay = reconnect_delay
        self.connection_status = "Disconnected"
        self._new_points: list[MapPoint] = []
        self._task: asyncio.Task | None = None

    def start(self):
        self.preload_existing_points()
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self.connect_to_server())

    def get_new_points(self) -> list[MapPoint]:
        points = self._new_points
        self._new_points = []
        return points

    def preload_existing_points(self):
        try:
            response = requests.get(
                f"http://{self.host}:{self.port}/processed_agent_data/",
                timeout=3,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            Logger.warning(f"Store preload failed: {exc}")
            return

        records = [
            record
            for record in response.json()
            if int(record.get("user_id", self.user_id)) == self.user_id
        ]
        records = sorted(records, key=lambda item: item.get("timestamp") or "")[
            -self.preload_limit :
        ]
        self._new_points.extend(
            map_point_from_store_record(record, source="store-preload")
            for record in records
        )

    async def connect_to_server(self):
        uri = f"ws://{self.host}:{self.port}/ws/{self.user_id}"
        while True:
            try:
                Logger.debug(f"Connect to Store websocket: {uri}")
                async with websockets.connect(uri) as websocket:
                    self.connection_status = "Connected"
                    while True:
                        data = await websocket.recv()
                        self.handle_received_data(data)
            except asyncio.CancelledError:
                self.connection_status = "Disconnected"
                raise
            except Exception as exc:
                self.connection_status = "Disconnected"
                Logger.warning(f"Store websocket disconnected: {exc}")
                await asyncio.sleep(self.reconnect_delay)

    def handle_received_data(self, data):
        Logger.debug(f"Received Store data: {data}")
        records = self._decode_records(data)
        points = [
            map_point_from_store_record(record, source="store-live")
            for record in records
            if user_id_from_store_record(record, self.user_id) == self.user_id
        ]
        points.sort(key=lambda point: point.timestamp or datetime.min)
        self._new_points.extend(points)

    def _decode_records(self, data) -> list[dict[str, Any]]:
        if isinstance(data, str):
            data = json.loads(data)

        if isinstance(data, dict):
            return [data]

        if isinstance(data, list):
            return data

        raise ValueError(f"Unsupported Store payload: {type(data)!r}")


Datasource = StoreDatasource
