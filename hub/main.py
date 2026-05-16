import logging
from typing import List

from fastapi import FastAPI
from redis import Redis
import paho.mqtt.client as mqtt

from app.adapters.store_api_adapter import StoreApiAdapter
from app.entities.processed_agent_data import ProcessedAgentData
from app.entities.sensor_data import SensorReading
from config import (
    STORE_API_BASE_URL,
    REDIS_HOST,
    REDIS_PORT,
    BATCH_SIZE,
    MQTT_TOPIC,
    SENSOR_MQTT_TOPIC,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
)

# Configure logging settings
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO (you can use logging.DEBUG for more detailed logs)
    format="[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # Output log messages to the console
        logging.FileHandler("app.log"),  # Save log messages to a file
    ],
)
# Create an instance of the Redis using the configuration
redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT)
# Create an instance of the StoreApiAdapter using the configuration
store_adapter = StoreApiAdapter(api_base_url=STORE_API_BASE_URL)
# Create an instance of the AgentMQTTAdapter using the configuration

# FastAPI
app = FastAPI()

PROCESSED_DATA_QUEUE = "processed_agent_data"
SENSOR_DATA_QUEUE = "sensor_readings"


def save_to_queue(processed_agent_data: ProcessedAgentData) -> int:
    redis_client.rpush(PROCESSED_DATA_QUEUE, processed_agent_data.model_dump_json())
    return redis_client.llen(PROCESSED_DATA_QUEUE)


def pop_batch_if_ready() -> List[ProcessedAgentData]:
    processed_agent_data_batch: List[ProcessedAgentData] = []
    if redis_client.llen(PROCESSED_DATA_QUEUE) < BATCH_SIZE:
        return processed_agent_data_batch

    for _ in range(BATCH_SIZE):
        raw_data = redis_client.lpop(PROCESSED_DATA_QUEUE)
        if raw_data is None:
            break
        processed_agent_data_batch.append(
            ProcessedAgentData.model_validate_json(raw_data)
        )

    return processed_agent_data_batch


def save_sensor_to_queue(sensor_reading: SensorReading) -> int:
    redis_client.rpush(SENSOR_DATA_QUEUE, sensor_reading.model_dump_json())
    return redis_client.llen(SENSOR_DATA_QUEUE)


def pop_sensor_batch_if_ready() -> List[SensorReading]:
    sensor_reading_batch: List[SensorReading] = []
    if redis_client.llen(SENSOR_DATA_QUEUE) < BATCH_SIZE:
        return sensor_reading_batch

    for _ in range(BATCH_SIZE):
        raw_data = redis_client.lpop(SENSOR_DATA_QUEUE)
        if raw_data is None:
            break
        sensor_reading_batch.append(SensorReading.model_validate_json(raw_data))

    return sensor_reading_batch


@app.post("/processed_agent_data/")
async def save_processed_agent_data(processed_agent_data: ProcessedAgentData):
    queue_size = save_to_queue(processed_agent_data)
    processed_agent_data_batch = pop_batch_if_ready()
    is_saved = store_adapter.save_data(processed_agent_data_batch)
    return {
        "status": "ok" if is_saved else "store_api_error",
        "queued_before_flush": queue_size,
        "flushed": len(processed_agent_data_batch),
    }


@app.post("/sensor_readings/")
async def save_sensor_reading(sensor_reading: SensorReading):
    queue_size = save_sensor_to_queue(sensor_reading)
    sensor_reading_batch = pop_sensor_batch_if_ready()
    is_saved = store_adapter.save_sensor_data(sensor_reading_batch)
    return {
        "status": "ok" if is_saved else "store_api_error",
        "queued_before_flush": queue_size,
        "flushed": len(sensor_reading_batch),
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "queue_size": redis_client.llen(PROCESSED_DATA_QUEUE),
        "sensor_queue_size": redis_client.llen(SENSOR_DATA_QUEUE),
        "batch_size": BATCH_SIZE,
        "mqtt_topic": MQTT_TOPIC,
        "sensor_mqtt_topic": SENSOR_MQTT_TOPIC,
        "store_api_base_url": STORE_API_BASE_URL,
    }


# MQTT
client = mqtt.Client()


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT broker")
        client.subscribe(MQTT_TOPIC)
        client.subscribe(SENSOR_MQTT_TOPIC)
    else:
        logging.info(f"Failed to connect to MQTT broker with code: {rc}")


def on_message(client, userdata, msg):
    payload: str = msg.payload.decode("utf-8")
    try:
        if msg.topic == SENSOR_MQTT_TOPIC:
            sensor_reading = SensorReading.model_validate_json(payload, strict=True)
            queue_size = save_sensor_to_queue(sensor_reading)
            sensor_reading_batch = pop_sensor_batch_if_ready()
            if sensor_reading_batch:
                store_adapter.save_sensor_data(sensor_reading_batch)
            logging.info(
                "Processed sensor MQTT message. Queue size before flush: %s. Flushed: %s",
                queue_size,
                len(sensor_reading_batch),
            )
            return

        processed_agent_data = ProcessedAgentData.model_validate_json(
            payload, strict=True
        )

        queue_size = save_to_queue(processed_agent_data)
        processed_agent_data_batch = pop_batch_if_ready()
        if processed_agent_data_batch:
            store_adapter.save_data(processed_agent_data_batch)
        logging.info(
            "Processed MQTT message. Queue size before flush: %s. Flushed: %s",
            queue_size,
            len(processed_agent_data_batch),
        )
    except Exception as e:
        logging.info(f"Error processing MQTT message: {e}")


# Connect
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT)

# Start
client.loop_start()
