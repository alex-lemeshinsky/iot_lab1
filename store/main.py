from typing import Any, Set, Dict, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    ForeignKey,
    Integer,
    String,
    Float,
    DateTime,
)
from sqlalchemy.dialects.postgresql import JSONB, insert as postgres_insert
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import delete, insert, select, update
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
)

# FastAPI app setup
app = FastAPI()
# SQLAlchemy setup
DATABASE_URL = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
engine = create_engine(DATABASE_URL)
metadata = MetaData()
# Define the ProcessedAgentData table
processed_agent_data = Table(
    "processed_agent_data",
    metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("road_state", String),
    Column("user_id", Integer),
    Column("x", Float),
    Column("y", Float),
    Column("z", Float),
    Column("latitude", Float),
    Column("longitude", Float),
    Column("timestamp", DateTime),
)
sensor_objects = Table(
    "sensor_objects",
    metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("object_id", String, nullable=False, unique=True, index=True),
    Column("object_type", String, nullable=False, index=True),
    Column("name", String, nullable=False),
    Column("latitude", Float, nullable=False),
    Column("longitude", Float, nullable=False),
    Column("object_metadata", JSONB, nullable=False, default=dict),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)
sensor_readings = Table(
    "sensor_readings",
    metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column(
        "object_id",
        String,
        ForeignKey("sensor_objects.object_id"),
        nullable=False,
        index=True,
    ),
    Column("sensor_type", String, nullable=False, index=True),
    Column("timestamp", DateTime, nullable=False, index=True),
    Column("payload", JSONB, nullable=False, default=dict),
    Column("source", String, nullable=False),
    Column("quality", String, nullable=False),
)
SessionLocal = sessionmaker(bind=engine)
metadata.create_all(engine)


# SQLAlchemy model
class ProcessedAgentDataInDB(BaseModel):
    id: int
    road_state: str
    user_id: int
    x: float
    y: float
    z: float
    latitude: float
    longitude: float
    timestamp: datetime


# FastAPI models
class AccelerometerData(BaseModel):
    x: float
    y: float
    z: float


class GpsData(BaseModel):
    latitude: float
    longitude: float


class AgentData(BaseModel):
    user_id: int
    accelerometer: AccelerometerData
    gps: GpsData
    timestamp: datetime

    @field_validator("timestamp", mode="before")
    @classmethod
    def check_timestamp(cls, value):
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError(
                "Invalid timestamp format. Expected ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)."
            )


class ProcessedAgentData(BaseModel):
    road_state: str
    agent_data: AgentData


class SensorObject(BaseModel):
    object_id: str
    object_type: str
    name: str
    gps: GpsData
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SensorReading(BaseModel):
    sensor_object: SensorObject
    sensor_type: str
    timestamp: datetime
    payload: Dict[str, Any] = Field(default_factory=dict)
    source: str = "synthetic_open_dataset_profile"
    quality: str = "ok"

    @field_validator("timestamp", mode="before")
    @classmethod
    def check_timestamp(cls, value):
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError(
                "Invalid timestamp format. Expected ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)."
            )


class SensorObjectInDB(BaseModel):
    id: int
    object_id: str
    object_type: str
    name: str
    latitude: float
    longitude: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SensorReadingInDB(BaseModel):
    id: int
    object_id: str
    object_type: str
    name: str
    latitude: float
    longitude: float
    sensor_type: str
    timestamp: datetime
    payload: Dict[str, Any]
    source: str
    quality: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


# WebSocket subscriptions
subscriptions: Dict[int, Set[WebSocket]] = {}


# FastAPI WebSocket endpoint
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await websocket.accept()
    if user_id not in subscriptions:
        subscriptions[user_id] = set()
    subscriptions[user_id].add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        subscriptions[user_id].discard(websocket)


# Function to send data to subscribed users
async def send_data_to_subscribers(user_id: int, data):
    if user_id in subscriptions:
        disconnected_websockets = []
        for websocket in subscriptions[user_id]:
            try:
                await websocket.send_json(data)
            except WebSocketDisconnect:
                disconnected_websockets.append(websocket)

        for websocket in disconnected_websockets:
            subscriptions[user_id].discard(websocket)


# FastAPI CRUDL endpoints


@app.post("/processed_agent_data/", response_model=list[ProcessedAgentDataInDB])
async def create_processed_agent_data(
    data: List[ProcessedAgentData],
) -> list[ProcessedAgentDataInDB]:
    created_items = []
    with SessionLocal() as session:
        for item in data:
            values = _processed_agent_data_to_record(item)
            result = session.execute(
                insert(processed_agent_data)
                .values(**values)
                .returning(processed_agent_data)
            )
            created_items.append(_row_to_model(result.mappings().one()))

        session.commit()

    for item in created_items:
        await send_data_to_subscribers(item.user_id, item.model_dump(mode="json"))

    return created_items


@app.get(
    "/processed_agent_data/{processed_agent_data_id}",
    response_model=ProcessedAgentDataInDB,
)
def read_processed_agent_data(processed_agent_data_id: int):
    with SessionLocal() as session:
        row = session.execute(
            select(processed_agent_data).where(
                processed_agent_data.c.id == processed_agent_data_id
            )
        ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="ProcessedAgentData not found")

    return _row_to_model(row)


@app.get("/processed_agent_data/", response_model=list[ProcessedAgentDataInDB])
def list_processed_agent_data():
    with SessionLocal() as session:
        rows = session.execute(
            select(processed_agent_data).order_by(processed_agent_data.c.id)
        ).mappings().all()

    return [_row_to_model(row) for row in rows]


@app.put(
    "/processed_agent_data/{processed_agent_data_id}",
    response_model=ProcessedAgentDataInDB,
)
def update_processed_agent_data(processed_agent_data_id: int, data: ProcessedAgentData):
    with SessionLocal() as session:
        existing_row = session.execute(
            select(processed_agent_data).where(
                processed_agent_data.c.id == processed_agent_data_id
            )
        ).mappings().first()
        if existing_row is None:
            raise HTTPException(status_code=404, detail="ProcessedAgentData not found")

        result = session.execute(
            update(processed_agent_data)
            .where(processed_agent_data.c.id == processed_agent_data_id)
            .values(**_processed_agent_data_to_record(data))
            .returning(processed_agent_data)
        )
        session.commit()
        updated_item = _row_to_model(result.mappings().one())

    return updated_item


@app.delete(
    "/processed_agent_data/{processed_agent_data_id}",
    response_model=ProcessedAgentDataInDB,
)
def delete_processed_agent_data(processed_agent_data_id: int):
    with SessionLocal() as session:
        result = session.execute(
            delete(processed_agent_data)
            .where(processed_agent_data.c.id == processed_agent_data_id)
            .returning(processed_agent_data)
        )
        row = result.mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="ProcessedAgentData not found")
        session.commit()

    return _row_to_model(row)


@app.post("/sensor_readings/", response_model=list[SensorReadingInDB])
async def create_sensor_readings(
    data: List[SensorReading],
) -> list[SensorReadingInDB]:
    created_items = []
    with SessionLocal() as session:
        for item in data:
            _upsert_sensor_object(session, item.sensor_object)
            result = session.execute(
                insert(sensor_readings)
                .values(**_sensor_reading_to_record(item))
                .returning(sensor_readings)
            )
            created_items.append(
                _sensor_reading_row_to_model(
                    result.mappings().one(),
                    item.sensor_object,
                )
            )

        session.commit()

    return created_items


@app.get("/sensor_objects/", response_model=list[SensorObjectInDB])
def list_sensor_objects():
    with SessionLocal() as session:
        rows = session.execute(
            select(sensor_objects).order_by(sensor_objects.c.object_id)
        ).mappings().all()

    return [_sensor_object_row_to_model(row) for row in rows]


@app.get("/sensor_readings/", response_model=list[SensorReadingInDB])
def list_sensor_readings(limit: int = 100):
    with SessionLocal() as session:
        rows = session.execute(
            _sensor_reading_select()
            .order_by(sensor_readings.c.id.desc())
            .limit(max(1, min(limit, 1000)))
        ).mappings().all()

    return [_joined_sensor_reading_row_to_model(row) for row in rows]


@app.get("/sensor_readings/{sensor_reading_id}", response_model=SensorReadingInDB)
def read_sensor_reading(sensor_reading_id: int):
    with SessionLocal() as session:
        row = session.execute(
            _sensor_reading_select().where(sensor_readings.c.id == sensor_reading_id)
        ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="SensorReading not found")

    return _joined_sensor_reading_row_to_model(row)


def _processed_agent_data_to_record(data: ProcessedAgentData):
    return {
        "road_state": data.road_state,
        "user_id": data.agent_data.user_id,
        "x": data.agent_data.accelerometer.x,
        "y": data.agent_data.accelerometer.y,
        "z": data.agent_data.accelerometer.z,
        "latitude": data.agent_data.gps.latitude,
        "longitude": data.agent_data.gps.longitude,
        "timestamp": data.agent_data.timestamp,
    }


def _row_to_model(row) -> ProcessedAgentDataInDB:
    return ProcessedAgentDataInDB(
        id=row["id"],
        road_state=row["road_state"],
        user_id=row["user_id"],
        x=row["x"],
        y=row["y"],
        z=row["z"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        timestamp=row["timestamp"],
    )


def _upsert_sensor_object(session, sensor_object: SensorObject):
    values = _sensor_object_to_record(sensor_object)
    statement = postgres_insert(sensor_objects).values(**values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[sensor_objects.c.object_id],
            set_={
                "object_type": statement.excluded.object_type,
                "name": statement.excluded.name,
                "latitude": statement.excluded.latitude,
                "longitude": statement.excluded.longitude,
                "object_metadata": statement.excluded.object_metadata,
            },
        )
    )


def _sensor_object_to_record(sensor_object: SensorObject):
    return {
        "object_id": sensor_object.object_id,
        "object_type": sensor_object.object_type,
        "name": sensor_object.name,
        "latitude": sensor_object.gps.latitude,
        "longitude": sensor_object.gps.longitude,
        "object_metadata": sensor_object.metadata,
    }


def _sensor_reading_to_record(sensor_reading: SensorReading):
    return {
        "object_id": sensor_reading.sensor_object.object_id,
        "sensor_type": sensor_reading.sensor_type,
        "timestamp": sensor_reading.timestamp,
        "payload": sensor_reading.payload,
        "source": sensor_reading.source,
        "quality": sensor_reading.quality,
    }


def _sensor_object_row_to_model(row) -> SensorObjectInDB:
    return SensorObjectInDB(
        id=row["id"],
        object_id=row["object_id"],
        object_type=row["object_type"],
        name=row["name"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        metadata=row["object_metadata"],
        created_at=row["created_at"],
    )


def _sensor_reading_row_to_model(
    row,
    sensor_object: SensorObject,
) -> SensorReadingInDB:
    return SensorReadingInDB(
        id=row["id"],
        object_id=row["object_id"],
        object_type=sensor_object.object_type,
        name=sensor_object.name,
        latitude=sensor_object.gps.latitude,
        longitude=sensor_object.gps.longitude,
        sensor_type=row["sensor_type"],
        timestamp=row["timestamp"],
        payload=row["payload"],
        source=row["source"],
        quality=row["quality"],
        metadata=sensor_object.metadata,
    )


def _sensor_reading_select():
    return select(
        sensor_readings.c.id,
        sensor_readings.c.object_id,
        sensor_objects.c.object_type,
        sensor_objects.c.name,
        sensor_objects.c.latitude,
        sensor_objects.c.longitude,
        sensor_readings.c.sensor_type,
        sensor_readings.c.timestamp,
        sensor_readings.c.payload,
        sensor_readings.c.source,
        sensor_readings.c.quality,
        sensor_objects.c.object_metadata,
    ).join(
        sensor_objects,
        sensor_readings.c.object_id == sensor_objects.c.object_id,
    )


def _joined_sensor_reading_row_to_model(row) -> SensorReadingInDB:
    return SensorReadingInDB(
        id=row["id"],
        object_id=row["object_id"],
        object_type=row["object_type"],
        name=row["name"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        sensor_type=row["sensor_type"],
        timestamp=row["timestamp"],
        payload=row["payload"],
        source=row["source"],
        quality=row["quality"],
        metadata=row["object_metadata"],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
