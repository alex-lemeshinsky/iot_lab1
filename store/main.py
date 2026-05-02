from typing import Set, Dict, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Float,
    DateTime,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import delete, insert, select, update
from datetime import datetime
from pydantic import BaseModel, field_validator
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
