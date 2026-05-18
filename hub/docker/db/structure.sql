CREATE TABLE processed_agent_data (
    id SERIAL PRIMARY KEY,
    road_state VARCHAR(255) NOT NULL,
    user_id INTEGER NOT NULL,
    x FLOAT,
    y FLOAT,
    z FLOAT,
    latitude FLOAT,
    longitude FLOAT,
    timestamp TIMESTAMP
);

CREATE TABLE sensor_objects (
    id SERIAL PRIMARY KEY,
    object_id VARCHAR(255) NOT NULL UNIQUE,
    object_type VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL,
    object_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX sensor_objects_object_type_idx ON sensor_objects (object_type);

CREATE TABLE sensor_readings (
    id SERIAL PRIMARY KEY,
    object_id VARCHAR(255) NOT NULL REFERENCES sensor_objects(object_id),
    sensor_type VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    source VARCHAR(255) NOT NULL,
    quality VARCHAR(255) NOT NULL
);

CREATE INDEX sensor_readings_object_id_idx ON sensor_readings (object_id);
CREATE INDEX sensor_readings_sensor_type_idx ON sensor_readings (sensor_type);
CREATE INDEX sensor_readings_timestamp_idx ON sensor_readings (timestamp);

CREATE TABLE network_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    processed_messages_total INTEGER NOT NULL,
    sensor_messages_total INTEGER NOT NULL,
    processed_messages_per_second FLOAT NOT NULL,
    sensor_messages_per_second FLOAT NOT NULL,
    throughput_kbps FLOAT NOT NULL,
    estimated_latency_ms FLOAT NOT NULL,
    packet_loss_percent FLOAT NOT NULL,
    mqtt_health INTEGER NOT NULL
);

CREATE INDEX network_metrics_timestamp_idx ON network_metrics (timestamp);
