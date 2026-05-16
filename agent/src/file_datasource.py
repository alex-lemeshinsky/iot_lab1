from csv import DictReader
from datetime import datetime
from domain.accelerometer import Accelerometer
from domain.gps import Gps
from domain.aggregated_data import AggregatedData
from domain.parking import Parking
from domain.sensor_object import SensorObject
from domain.sensor_reading import SensorReading
import config


class FileDatasource:
    def __init__(
        self,
        accelerometer_filename: str,
        gps_filename: str,
        parking_filename: str,
    ) -> None:
        self.accelerometer_filename = accelerometer_filename
        self.gps_filename = gps_filename
        self.parking_filename = parking_filename
        self.accelerometer_file = None
        self.gps_file = None
        self.parking_file = None
        self.accelerometer_reader = None
        self.gps_reader = None
        self.parking_reader = None
        self.sensor_sequence_index = 0

    def read(self) -> AggregatedData:
        """Метод повертає дані отримані з датчиків"""
        if self.accelerometer_reader is None or self.gps_reader is None:
            self.startReading()

        accelerometer_row = self._read_next_accelerometer_row()
        gps_row = self._read_next_gps_row()

        return AggregatedData(
            Accelerometer(
                int(accelerometer_row["x"]),
                int(accelerometer_row["y"]),
                int(accelerometer_row["z"]),
            ),
            Gps(
                float(gps_row["longitude"]),
                float(gps_row["latitude"]),
            ),
            datetime.now(),
            config.USER_ID,
        )

    def read_parking(self) -> Parking:
        """Метод повертає дані про кількість вільних паркомісць"""
        if self.parking_reader is None:
            self.startReading()

        parking_row = self._read_next_parking_row()

        return Parking(
            int(parking_row["empty_count"]),
            Gps(
                float(parking_row["longitude"]),
                float(parking_row["latitude"]),
            ),
        )

    def read_sensor_readings(self, parking: Parking | None = None) -> list[SensorReading]:
        """Повертає універсальні записи сенсорних об'єктів для лабораторної 2."""
        if parking is None:
            parking = self.read_parking()

        timestamp = datetime.now()
        traffic_light_reading = self._build_traffic_light_reading(timestamp)
        parking_reading = self._build_parking_reading(parking, timestamp)
        self.sensor_sequence_index += 1
        return [parking_reading, traffic_light_reading]

    def startReading(self, *args, **kwargs):
        """Метод повинен викликатись перед початком читання даних"""
        self.stopReading()
        self._open_readers()

    def stopReading(self, *args, **kwargs):
        """Метод повинен викликатись для закінчення читання даних"""
        if self.accelerometer_file is not None:
            self.accelerometer_file.close()

        if self.gps_file is not None:
            self.gps_file.close()

        if self.parking_file is not None:
            self.parking_file.close()

        self.accelerometer_file = None
        self.gps_file = None
        self.parking_file = None
        self.accelerometer_reader = None
        self.gps_reader = None
        self.parking_reader = None

    def _open_readers(self):
        self.accelerometer_file = open(
            self.accelerometer_filename, "r", encoding="utf-8", newline=""
        )
        self.gps_file = open(self.gps_filename, "r", encoding="utf-8", newline="")
        self.parking_file = open(
            self.parking_filename, "r", encoding="utf-8", newline=""
        )
        self.accelerometer_reader = DictReader(self.accelerometer_file)
        self.gps_reader = DictReader(self.gps_file)
        self.parking_reader = DictReader(self.parking_file)

    def _read_next_accelerometer_row(self):
        return self._read_next_row(
            "accelerometer_reader",
            self.accelerometer_file,
            self.accelerometer_filename,
        )

    def _read_next_gps_row(self):
        return self._read_next_row("gps_reader", self.gps_file, self.gps_filename)

    def _read_next_parking_row(self):
        return self._read_next_row(
            "parking_reader",
            self.parking_file,
            self.parking_filename,
        )

    def _read_next_row(self, reader_attr, file_handle, filename):
        try:
            return next(getattr(self, reader_attr))
        except StopIteration:
            file_handle.seek(0)
            setattr(self, reader_attr, DictReader(file_handle))
            return next(getattr(self, reader_attr))

    def _build_parking_reading(
        self, parking: Parking, timestamp: datetime
    ) -> SensorReading:
        capacity = config.PARKING_CAPACITY
        empty_count = max(0, min(capacity, parking.empty_count))
        occupied_count = capacity - empty_count
        occupancy_percent = round((occupied_count / capacity) * 100, 2)

        sensor_object = SensorObject(
            object_id="parking_kyiv_podil_001",
            object_type="parking",
            name="Synthetic Podil Parking",
            gps=parking.gps,
            metadata={
                "city": "Kyiv",
                "capacity": capacity,
                "open_dataset_basis": "urban parking occupancy profiles",
                "lab": "2",
            },
        )

        return SensorReading(
            sensor_object=sensor_object,
            sensor_type="parking_occupancy",
            timestamp=timestamp,
            payload={
                "capacity": capacity,
                "empty_count": empty_count,
                "occupied_count": occupied_count,
                "occupancy_percent": occupancy_percent,
            },
        )

    def _build_traffic_light_reading(self, timestamp: datetime) -> SensorReading:
        phases = [
            ("green", 35),
            ("yellow", 5),
            ("red", 40),
        ]
        cycle_length = sum(duration for _, duration in phases)
        position = (self.sensor_sequence_index * 7) % cycle_length
        phase = phases[0][0]
        remaining_seconds = phases[0][1]
        offset = position
        for phase_name, duration in phases:
            if offset < duration:
                phase = phase_name
                remaining_seconds = duration - offset
                break
            offset -= duration

        if phase == "red":
            queue_length = min(18, 5 + self.sensor_sequence_index % 14)
        elif phase == "yellow":
            queue_length = 3 + self.sensor_sequence_index % 5
        else:
            queue_length = max(0, 6 - self.sensor_sequence_index % 7)

        sensor_object = SensorObject(
            object_id="traffic_light_kyiv_sahaidachnoho_001",
            object_type="traffic_light",
            name="Synthetic Sahaidachnoho Traffic Light",
            gps=Gps(longitude=30.5229, latitude=50.4598),
            metadata={
                "city": "Kyiv",
                "intersection": "Sahaidachnoho / Kontraktova",
                "cycle_seconds": cycle_length,
                "open_dataset_basis": "traffic signal phase and vehicle queue profiles",
                "lab": "2",
            },
        )

        return SensorReading(
            sensor_object=sensor_object,
            sensor_type="traffic_signal_state",
            timestamp=timestamp,
            payload={
                "phase": phase,
                "cycle_seconds": cycle_length,
                "remaining_seconds": remaining_seconds,
                "vehicle_queue_length": queue_length,
                "pedestrian_request": self.sensor_sequence_index % 4 == 0,
            },
        )
