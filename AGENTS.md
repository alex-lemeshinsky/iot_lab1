# AGENTS.md

This file gives AI coding agents the project context needed to work in this repository without rediscovering the architecture from scratch.

## Project Overview

This repository is a KPI Internet of Things lab project based on `Toolf/project_template`.

Repository remotes:

- `origin`: `git@github.com:alex-lemeshinsky/iot_lab1.git`
- `upstream`: `git@github.com:Toolf/project_template.git`

The system models road-surface monitoring plus a universal sensor-object pipeline:

1. `agent` reads sensor-like CSV data and publishes raw MQTT messages.
2. `edge` subscribes to raw agent data, classifies road state, and forwards processed data.
3. `hub` accepts processed data through HTTP or MQTT, buffers it in Redis, and flushes batches to Store API.
4. `store` persists processed data in PostgreSQL and exposes CRUD plus WebSocket endpoints.
5. `MapView` is a Kivy client that visualizes road-state data from CSV and Store on a map.
6. Lab 2 adds a scalable sensor-object contract for new objects such as parking lots and traffic lights.

Current lab work already implemented labs 1.1, 1.2, 1.3, 1.4, 1.5, and 2. Generated reports and evidence are intentionally ignored by git.

## Repository Layout

```text
.
├── agent/      # Fake IoT device: CSV datasource -> MQTT
├── edge/       # Raw MQTT -> road-state processing -> Hub gateway
├── hub/        # Processed HTTP/MQTT ingestion -> Redis batch -> Store API
├── store/      # FastAPI + PostgreSQL persistence + WebSocket subscriptions
├── MapView/    # Kivy map visualization client
├── tasks/      # Lab assignment PDFs
├── report*/    # Generated DOCX/PDF reports, screenshots, evidence; ignored
└── tmp/        # Temporary extracted/rendered files; ignored
```

## Main Data Contracts

Raw agent MQTT payload, published by `agent` to `agent_data_topic`:

```json
{
  "accelerometer": {"x": 1, "y": 2, "z": 3},
  "gps": {"longitude": 30.5251, "latitude": 50.4511},
  "timestamp": "2026-05-02T16:30:00",
  "user_id": 1
}
```

Parking payload, published by `agent` to `parking_data_topic`:

```json
{
  "empty_count": 5,
  "gps": {"longitude": 30.5251, "latitude": 50.4511}
}
```

Universal sensor reading payload, published by `agent` to `sensor_data_topic` and accepted by `hub` and `store`:

```json
{
  "sensor_object": {
    "object_id": "parking_kyiv_podil_001",
    "object_type": "parking",
    "name": "Synthetic Podil Parking",
    "gps": {"latitude": 50.4525, "longitude": 30.5246},
    "metadata": {
      "capacity": 80,
      "city": "Kyiv",
      "open_dataset_basis": "urban parking occupancy profiles"
    }
  },
  "sensor_type": "parking_occupancy",
  "timestamp": "2026-05-14T12:00:00",
  "payload": {
    "capacity": 80,
    "empty_count": 20,
    "occupied_count": 60,
    "occupancy_percent": 75.0
  },
  "source": "synthetic_open_dataset_profile",
  "quality": "ok"
}
```

Traffic-light universal readings use the same envelope with:

- `object_type`: `traffic_light`
- `sensor_type`: `traffic_signal_state`
- `payload.phase`: one of `red`, `yellow`, `green`
- `payload.cycle_seconds`
- `payload.remaining_seconds`
- `payload.vehicle_queue_length`
- `payload.pedestrian_request`

Processed data payload, accepted by `hub` and `store`:

```json
{
  "road_state": "normal",
  "agent_data": {
    "user_id": 1,
    "accelerometer": {"x": 0.3, "y": 0.2, "z": 9.6},
    "gps": {"latitude": 50.4511, "longitude": 30.5251},
    "timestamp": "2026-05-02T16:30:00"
  }
}
```

`store` persists processed data in the `processed_agent_data` table with flattened columns:

- `id`
- `road_state`
- `user_id`
- `x`, `y`, `z`
- `latitude`, `longitude`
- `timestamp`

`store` persists universal sensor data in two tables:

- `sensor_objects`: stable catalog records keyed by `object_id`, with `object_type`, `name`, coordinates, and JSONB `object_metadata`.
- `sensor_readings`: time-series records linked to `sensor_objects`, with `sensor_type`, `timestamp`, JSONB `payload`, `source`, and `quality`.

## Services

### agent

Purpose: emulate a device.

Important files:

- `agent/src/main.py`
- `agent/src/file_datasource.py`
- `agent/src/config.py`
- `agent/src/data/accelerometer.csv`
- `agent/src/data/gps.csv`
- `agent/src/data/parking.csv`
- `agent/src/domain/sensor_object.py`
- `agent/src/domain/sensor_reading.py`
- `agent/src/schema/sensor_object_schema.py`
- `agent/src/schema/sensor_reading_schema.py`
- `agent/src/domain/*`
- `agent/src/schema/*`

Behavior:

- Reads accelerometer, GPS, and parking CSV files.
- Loops back to the beginning when a CSV reaches EOF.
- Publishes aggregated sensor data to `MQTT_TOPIC` (usually `agent_data_topic`).
- Publishes parking data to `PARKING_MQTT_TOPIC` (usually `parking_data_topic`).
- Publishes Lab 2 universal sensor readings to `SENSOR_MQTT_TOPIC` (usually `sensor_data_topic`).
- Generates universal readings for:
  - parking occupancy object `parking_kyiv_podil_001`;
  - traffic-light state object `traffic_light_kyiv_sahaidachnoho_001`.
- Parking capacity is controlled by `PARKING_CAPACITY` and defaults to `80`.

Run:

```bash
cd agent/docker
docker compose up --build -d
```

Useful MQTT checks:

```bash
docker compose exec -T mqtt mosquitto_sub -h localhost -t agent_data_topic -C 1
docker compose exec -T mqtt mosquitto_sub -h localhost -t parking_data_topic -C 1
docker compose exec -T mqtt mosquitto_sub -h localhost -t sensor_data_topic -C 2
```

### edge

Purpose: subscribe to raw agent MQTT data, process it, and forward processed data to Hub.

Important files:

- `edge/main.py`
- `edge/config.py`
- `edge/app/adapters/agent_mqtt_adapter.py`
- `edge/app/adapters/hub_mqtt_adapter.py`
- `edge/app/adapters/hub_http_adapter.py`
- `edge/app/usecases/data_processing.py`
- `edge/tests/test_data_processing.py`

Behavior:

- Subscribes to raw agent MQTT payloads from `agent_data_topic`.
- Validates incoming JSON as `AgentData`, including `user_id`, accelerometer, GPS, and timestamp.
- Classifies `road_state` as `normal`, `bump`, or `pothole` in `edge/app/usecases/data_processing.py`.
- Publishes processed data to Hub through `HubMqttAdapter` on `processed_data_topic` by default.
- `HubHttpAdapter` is also available for HTTP forwarding, but the current Docker integration uses MQTT.

Classification rules:

- `pothole`: `z <= 12000` or `y <= -5000`
- `bump`: `z >= 20000` or `y >= 5000`
- `bump`: `abs(z - 16500) >= 5000`
- `normal`: all other samples

Run Edge only:

```bash
cd edge/docker
docker compose up --build -d
```

Run Edge unit tests from the repository root:

```bash
PYTHONPATH=edge python -m unittest discover -s edge/tests
```

### hub

Purpose: receive processed road data, buffer in Redis, and write batches to Store API.

Important files:

- `hub/main.py`
- `hub/config.py`
- `hub/app/adapters/store_api_adapter.py`
- `hub/app/interfaces/store_gateway.py`
- `hub/app/entities/agent_data.py`
- `hub/app/entities/processed_agent_data.py`
- `hub/app/entities/sensor_data.py`
- `hub/tests/test_store_api_adapter.py`

Behavior:

- `POST /processed_agent_data/` accepts one `ProcessedAgentData`, pushes it into Redis list `processed_agent_data`, and flushes a batch to Store API when `BATCH_SIZE` is reached.
- `POST /sensor_readings/` accepts one universal `SensorReading`, pushes it into Redis list `sensor_readings`, and flushes a batch to Store API when `BATCH_SIZE` is reached.
- `GET /health` returns service status, Redis queue lengths, batch size, MQTT topics, and Store API base URL.
- MQTT client subscribes to `MQTT_TOPIC` for processed road data and `SENSOR_MQTT_TOPIC` for universal sensor data.
- Store API writes are done through `StoreApiAdapter.save_data(batch)`, which posts a JSON list to `/processed_agent_data/`.
- Universal sensor writes are done through `StoreApiAdapter.save_sensor_data(batch)`, which posts a JSON list to `/sensor_readings/`.

Run the full integrated lab stack:

```bash
cd hub/docker
docker compose up --build -d
```

This stack now includes `agent`, `edge`, `hub`, `store`, `redis`, `postgres_db`, `pgadmin4`, and `mqtt`. With `BATCH_SIZE=1`, agent samples can flow end-to-end without manual MQTT publishing:

```text
agent -> agent_data_topic -> edge -> processed_data_topic -> hub -> redis -> store -> postgres_db
agent -> sensor_data_topic -> hub -> redis -> store -> postgres_db
```

Ports in this stack:

- Hub Swagger: `http://127.0.0.1:9000/docs`
- Store Swagger: `http://127.0.0.1:8000/docs`
- PgAdmin: `http://127.0.0.1:5050`
- PostgreSQL: `127.0.0.1:5432`
- Redis: `127.0.0.1:6379`
- MQTT: `127.0.0.1:1883`

Default PgAdmin credentials:

- Email: `admin@admin.com`
- Password: `root`

PostgreSQL credentials:

- Host in Docker network: `postgres_db`
- Host from macOS: `127.0.0.1`
- User: `user`
- Password: `pass`
- Database: `test_db`

Smoke checks:

```bash
curl -s http://127.0.0.1:9000/health
docker compose exec -T redis redis-cli LLEN processed_agent_data
docker compose exec -T redis redis-cli LLEN sensor_readings
docker compose exec -T hub python -m unittest tests.test_store_api_adapter
docker compose exec -T mqtt mosquitto_sub -h localhost -t processed_data_topic -C 3
docker compose exec -T mqtt mosquitto_sub -h localhost -t sensor_data_topic -C 2
docker compose exec -T postgres_db psql -U user -d test_db -c "select * from processed_agent_data order by id;"
docker compose exec -T postgres_db psql -U user -d test_db -c "select object_type, sensor_type, count(*) from sensor_readings join sensor_objects using (object_id) group by object_type, sensor_type order by object_type, sensor_type;"
```

Known test caveat:

- `docker compose exec -T hub python -m unittest discover tests` currently fails because `hub/tests/test_agent_mqtt_adapter.py` imports stale modules that do not exist in the current Hub implementation.
- The current relevant Hub test is `tests.test_store_api_adapter`.

### store

Purpose: persist processed road-state data.

Important files:

- `store/main.py`
- `store/config.py`
- `store/docker/db/structure.sql`
- `store/docker/docker-compose.yaml`

Endpoints:

- `POST /processed_agent_data/` accepts a list of processed records.
- `GET /processed_agent_data/` lists all records.
- `GET /processed_agent_data/{id}` reads one record.
- `PUT /processed_agent_data/{id}` updates one record.
- `DELETE /processed_agent_data/{id}` deletes one record.
- `POST /sensor_readings/` accepts a list of universal sensor readings and upserts referenced sensor objects.
- `GET /sensor_objects/` lists known universal sensor objects.
- `GET /sensor_readings/?limit=100` lists recent universal sensor readings.
- `GET /sensor_readings/{id}` reads one universal sensor reading.
- `WS /ws/{user_id}` streams newly created records for a user.

Run Store only:

```bash
cd store/docker
docker compose up --build -d
```

The Hub stack also builds and runs Store, so avoid running both stacks simultaneously unless you change ports/container names.

### MapView

Purpose: Kivy-based visualization for road quality on a map.

Important files:

- `MapView/main.py`
- `MapView/datasource.py`
- `MapView/config.py`
- `MapView/lineMapLayer.py`
- `MapView/images/*`
- `MapView/tests/test_datasource.py`

Behavior:

- Supports `MAPVIEW_SOURCE=csv`, `MAPVIEW_SOURCE=file`, `MAPVIEW_SOURCE=store`, and `MAPVIEW_SOURCE=both`; default is `both`.
- `FileDatasource` reads accelerometer and GPS CSV data, loops at EOF, classifies each point as `normal`, `bump`, or `pothole`, and normalizes older Kyiv CSV rows where latitude/longitude labels were swapped.
- `StoreDatasource` preloads recent persisted records from `GET /processed_agent_data/` and subscribes to live Store updates through `WS /ws/{user_id}`.
- Store payload parsing supports both the nested `ProcessedAgentData` contract and the flattened PostgreSQL row shape returned by Store.
- The UI shows a status bar with source mode, total point counts, CSV/Store counts, and WebSocket connection status.
- The map renders a route layer, current car marker, and defect markers for `bump` and `pothole`.

Install/run locally:

```bash
cd MapView
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
MAPVIEW_SOURCE=both python main.py
```

Useful environment variables:

- `STORE_HOST` defaults to `localhost`.
- `STORE_PORT` defaults to `8000`.
- `MAPVIEW_USER_ID` defaults to `1`.
- `MAPVIEW_SOURCE` defaults to `both`.
- `MAPVIEW_UPDATE_INTERVAL` defaults to `0.4`.
- `MAPVIEW_INITIAL_CSV_POINTS` defaults to `20`.
- `MAPVIEW_STORE_PRELOAD_LIMIT` defaults to `80`.

Run MapView datasource tests from the repository root:

```bash
PYTHONPATH=MapView python -m unittest discover -s MapView/tests -v
```

## Common Workflows

### Run Full Agent + Edge + Hub + Store Stack

```bash
cd hub/docker
docker compose up --build -d
docker compose ps
curl -s http://127.0.0.1:9000/health
```

### Verify Edge Processing Over MQTT

```bash
cd hub/docker
docker compose exec -T mqtt mosquitto_sub -h localhost -t processed_data_topic -C 3
docker compose logs --tail=20 edge
```

The `processed_data_topic` messages should contain a top-level `road_state` field and the original `agent_data`.

### Verify Universal Sensor Data Over MQTT

```bash
cd hub/docker
docker compose exec -T mqtt mosquitto_sub -h localhost -t sensor_data_topic -C 2
docker compose logs --tail=20 hub
```

The `sensor_data_topic` messages should use the universal `sensor_object`, `sensor_type`, `timestamp`, `payload`, `source`, and `quality` envelope.

### Send processed data to Hub over HTTP

```bash
curl -s -X POST http://127.0.0.1:9000/processed_agent_data/ \
  -H 'Content-Type: application/json' \
  -d '{
    "road_state": "normal",
    "agent_data": {
      "user_id": 131,
      "accelerometer": {"x": 0.3, "y": 0.2, "z": 9.6},
      "gps": {"latitude": 50.4511, "longitude": 30.5251},
      "timestamp": "2026-05-02T16:30:00"
    }
  }'
```

Expected with `BATCH_SIZE=1`:

```json
{"status":"ok","queued_before_flush":1,"flushed":1}
```

### Send processed data to Hub over MQTT

```bash
cd hub/docker
docker compose exec -T mqtt mosquitto_pub -h localhost -t processed_data_topic -m '{
  "road_state": "bump",
  "agent_data": {
    "user_id": 131,
    "accelerometer": {"x": 2.6, "y": 1.8, "z": 12.9},
    "gps": {"latitude": 50.4514, "longitude": 30.5256},
    "timestamp": "2026-05-02T16:30:05"
  }
}'
```

### Send universal sensor data to Hub over HTTP

```bash
curl -s -X POST http://127.0.0.1:9000/sensor_readings/ \
  -H 'Content-Type: application/json' \
  -d '{
    "sensor_object": {
      "object_id": "parking_kyiv_test_001",
      "object_type": "parking",
      "name": "Synthetic Test Parking",
      "gps": {"latitude": 50.4511, "longitude": 30.5251},
      "metadata": {"capacity": 40, "city": "Kyiv"}
    },
    "sensor_type": "parking_occupancy",
    "timestamp": "2026-05-14T12:00:00",
    "payload": {
      "capacity": 40,
      "empty_count": 8,
      "occupied_count": 32,
      "occupancy_percent": 80.0
    },
    "source": "manual_smoke_test",
    "quality": "ok"
  }'
```

Expected with `BATCH_SIZE=1`:

```json
{"status":"ok","queued_before_flush":1,"flushed":1}
```

### Inspect persisted data

```bash
cd hub/docker
docker compose exec -T postgres_db psql -U user -d test_db -c \
  "select id, road_state, user_id, x, y, z, latitude, longitude, timestamp from processed_agent_data order by id;"
```

Useful aggregate check:

```bash
cd hub/docker
docker compose exec -T postgres_db psql -U user -d test_db -c \
  "select road_state, count(*) from processed_agent_data group by road_state order by road_state;"
```

Universal sensor aggregate check:

```bash
cd hub/docker
docker compose exec -T postgres_db psql -U user -d test_db -c \
  "select object_type, sensor_type, count(*) from sensor_readings join sensor_objects using (object_id) group by object_type, sensor_type order by object_type, sensor_type;"
```

### Run MapView Against the Full Stack

Start the integrated stack first:

```bash
cd hub/docker
docker compose up --build -d
curl -s http://127.0.0.1:9000/health
```

Then run MapView locally from another shell:

```bash
cd MapView
source .venv/bin/activate
MAPVIEW_SOURCE=both python main.py
```

The top MapView status bar should show `WS: Connected`, increasing Store counts, and CSV counts. If no WebSocket data appears, check Store on `http://127.0.0.1:8000/docs` and confirm the full stack is writing rows into PostgreSQL.

### Stop containers

```bash
cd hub/docker
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete PostgreSQL/PgAdmin volumes.

## Coding Notes

- Python versions in Docker are Python 3.11 slim for Hub and Store.
- Hub and Store use FastAPI/Pydantic v2.
- Agent uses Marshmallow dataclass serialization.
- Keep API payloads compatible across services; small schema mismatches break the pipeline quickly.
- Prefer adding focused tests near the service being changed.
- Do not commit generated report folders unless explicitly requested. `.gitignore` already excludes:
  - `report/`
  - `report_lab12/`
  - `report_lab13/`
  - `report_lab14/`
  - `report_lab15/`
  - `report_lab2/`
  - `tmp/`
  - `*.log`
- Be careful with Docker container names. Several compose files use fixed container names like `mqtt`, `postgres_db`, `store`, and `hub`; only one stack with those names can run at a time.
- If a file has user edits unrelated to the task, preserve them.

## Current Known State

- Lab 1.1: Agent CSV reading and parking sensor MQTT publishing were implemented.
- Lab 1.2: Store API and PostgreSQL persistence were implemented.
- Lab 1.3: Hub HTTP/MQTT ingestion, Redis buffering, and Store API batch forwarding were implemented.
- Lab 1.4: Edge MQTT ingestion, road-state classification, MQTT forwarding to Hub, and full Agent -> Edge -> Hub -> Store Docker integration were implemented.
- Lab 1.5: MapView CSV + Store visualization was implemented, including `FileDatasource`, `StoreDatasource`, route rendering, defect markers, status bar, WebSocket subscription to Store, and datasource unit tests.
- Lab 2: Universal sensor-object data structure was implemented for parking and traffic-light objects, including `sensor_data_topic`, Hub ingestion, Redis buffering, Store persistence, and PostgreSQL tables `sensor_objects` and `sensor_readings`.
- The Lab 1.5 report was generated in `report_lab15/Лабораторна_робота_1.5.docx` with screenshots of MapView and Store Swagger; `report_lab15/` is ignored by git.
- The Lab 2 report was generated in `report_lab2/Лабораторна_робота_2.docx` with screenshots of Store Swagger, Hub health, sensor objects, and sensor readings; `report_lab2/` is ignored by git.
- Edge unit tests live in `edge/tests/test_data_processing.py` and currently cover normal, bump, pothole, and `user_id` preservation cases.
- MapView datasource tests live in `MapView/tests/test_datasource.py` and cover Edge-compatible classification, CSV pairing, Store flattened payloads, nested processed payloads, and legacy swapped Kyiv coordinate normalization.
- Hub Store API adapter tests live in `hub/tests/test_store_api_adapter.py` and cover processed-data saves plus Lab 2 `save_sensor_data()`.
- Hub full test discovery may still include stale legacy tests in older checkouts; run the focused Store API adapter test or update/remove stale tests before treating all Hub tests as authoritative.
