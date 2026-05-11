# AGENTS.md

This file gives AI coding agents the project context needed to work in this repository without rediscovering the architecture from scratch.

## Project Overview

This repository is a KPI Internet of Things lab project based on `Toolf/project_template`.

Repository remotes:

- `origin`: `git@github.com:alex-lemeshinsky/iot_lab1.git`
- `upstream`: `git@github.com:Toolf/project_template.git`

The system models road-surface monitoring:

1. `agent` reads sensor-like CSV data and publishes raw MQTT messages.
2. `edge` subscribes to raw agent data, classifies road state, and forwards processed data.
3. `hub` accepts processed data through HTTP or MQTT, buffers it in Redis, and flushes batches to Store API.
4. `store` persists processed data in PostgreSQL and exposes CRUD plus WebSocket endpoints.
5. `MapView` is a Kivy client intended to visualize stored road-state data.

Current lab work already implemented parts of labs 1.1, 1.2, 1.3, and 1.4. Generated reports and evidence are intentionally ignored by git.

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
- `agent/src/domain/*`
- `agent/src/schema/*`

Behavior:

- Reads accelerometer, GPS, and parking CSV files.
- Loops back to the beginning when a CSV reaches EOF.
- Publishes aggregated sensor data to `MQTT_TOPIC` (usually `agent_data_topic`).
- Publishes parking data to `PARKING_MQTT_TOPIC` (usually `parking_data_topic`).

Run:

```bash
cd agent/docker
docker compose up --build -d
```

Useful MQTT checks:

```bash
docker compose exec -T mqtt mosquitto_sub -h localhost -t agent_data_topic -C 1
docker compose exec -T mqtt mosquitto_sub -h localhost -t parking_data_topic -C 1
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
- `hub/tests/test_store_api_adapter.py`

Behavior:

- `POST /processed_agent_data/` accepts one `ProcessedAgentData`, pushes it into Redis list `processed_agent_data`, and flushes a batch to Store API when `BATCH_SIZE` is reached.
- `GET /health` returns service status, Redis queue length, batch size, MQTT topic, and Store API base URL.
- MQTT client subscribes to `MQTT_TOPIC` and processes the same `ProcessedAgentData` JSON contract.
- Store API writes are done through `StoreApiAdapter.save_data(batch)`, which posts a JSON list to `/processed_agent_data/`.

Run the full integrated lab stack:

```bash
cd hub/docker
docker compose up --build -d
```

This stack now includes `agent`, `edge`, `hub`, `store`, `redis`, `postgres_db`, `pgadmin4`, and `mqtt`. With `BATCH_SIZE=1`, agent samples can flow end-to-end without manual MQTT publishing:

```text
agent -> agent_data_topic -> edge -> processed_data_topic -> hub -> redis -> store -> postgres_db
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
docker compose exec -T hub python -m unittest tests.test_store_api_adapter
docker compose exec -T mqtt mosquitto_sub -h localhost -t processed_data_topic -C 3
docker compose exec -T postgres_db psql -U user -d test_db -c "select * from processed_agent_data order by id;"
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
- `MapView/lineMapLayer.py`
- `MapView/images/*`

Install/run locally:

```bash
cd MapView
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
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
  - `tmp/`
  - `*.log`
- Be careful with Docker container names. Several compose files use fixed container names like `mqtt`, `postgres_db`, `store`, and `hub`; only one stack with those names can run at a time.
- If a file has user edits unrelated to the task, preserve them.

## Current Known State

- Lab 1.1: Agent CSV reading and parking sensor MQTT publishing were implemented.
- Lab 1.2: Store API and PostgreSQL persistence were implemented.
- Lab 1.3: Hub HTTP/MQTT ingestion, Redis buffering, and Store API batch forwarding were implemented.
- Lab 1.4: Edge MQTT ingestion, road-state classification, MQTT forwarding to Hub, and full Agent -> Edge -> Hub -> Store Docker integration were implemented.
- Edge unit tests live in `edge/tests/test_data_processing.py` and currently cover normal, bump, pothole, and `user_id` preservation cases.
- Hub full test discovery has a stale legacy test; run the focused Store API adapter test or update/remove the stale test before treating all Hub tests as authoritative.
