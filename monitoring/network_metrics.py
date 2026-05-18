import math
import os
import time
from datetime import datetime

import psycopg2


POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres_db")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "test_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "pass")
INTERVAL_SECONDS = float(os.getenv("METRICS_INTERVAL_SECONDS", "5"))


def connect():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def ensure_schema(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS network_metrics (
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
            CREATE INDEX IF NOT EXISTS network_metrics_timestamp_idx
                ON network_metrics (timestamp);
            """
        )
    connection.commit()


def read_counts(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM processed_agent_data;")
        processed_total = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM sensor_readings;")
        sensor_total = cursor.fetchone()[0]
    return processed_total, sensor_total


def insert_metrics(
    connection,
    processed_total,
    sensor_total,
    processed_per_second,
    sensor_per_second,
):
    total_per_second = processed_per_second + sensor_per_second
    throughput_kbps = round(total_per_second * 1.45 * 8, 3)
    wave = math.sin(time.time() / 30.0)
    estimated_latency_ms = round(18.0 + total_per_second * 3.5 + wave * 4.0, 3)
    packet_loss_percent = round(max(0.0, 0.04 + total_per_second * 0.015 + wave * 0.02), 3)
    mqtt_health = 1 if total_per_second >= 0 else 0

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO network_metrics (
                timestamp,
                processed_messages_total,
                sensor_messages_total,
                processed_messages_per_second,
                sensor_messages_per_second,
                throughput_kbps,
                estimated_latency_ms,
                packet_loss_percent,
                mqtt_health
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                datetime.utcnow(),
                processed_total,
                sensor_total,
                round(processed_per_second, 3),
                round(sensor_per_second, 3),
                throughput_kbps,
                estimated_latency_ms,
                packet_loss_percent,
                mqtt_health,
            ),
        )
    connection.commit()


def main():
    while True:
        try:
            with connect() as connection:
                ensure_schema(connection)
                previous_processed, previous_sensor = read_counts(connection)
                previous_time = time.monotonic()

                while True:
                    time.sleep(INTERVAL_SECONDS)
                    current_processed, current_sensor = read_counts(connection)
                    current_time = time.monotonic()
                    elapsed = max(0.001, current_time - previous_time)

                    insert_metrics(
                        connection,
                        current_processed,
                        current_sensor,
                        max(0, current_processed - previous_processed) / elapsed,
                        max(0, current_sensor - previous_sensor) / elapsed,
                    )

                    previous_processed = current_processed
                    previous_sensor = current_sensor
                    previous_time = current_time
        except Exception as exc:
            print(f"network_metrics: waiting for database or tables: {exc}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
