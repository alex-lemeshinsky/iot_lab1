from csv import DictReader
from datetime import datetime
from domain.accelerometer import Accelerometer
from domain.gps import Gps
from domain.aggregated_data import AggregatedData
import config


class FileDatasource:
    def __init__(
        self,
        accelerometer_filename: str,
        gps_filename: str,
    ) -> None:
        self.accelerometer_filename = accelerometer_filename
        self.gps_filename = gps_filename
        self.accelerometer_file = None
        self.gps_file = None
        self.accelerometer_reader = None
        self.gps_reader = None

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

        self.accelerometer_file = None
        self.gps_file = None
        self.accelerometer_reader = None
        self.gps_reader = None

    def _open_readers(self):
        self.accelerometer_file = open(
            self.accelerometer_filename, "r", encoding="utf-8", newline=""
        )
        self.gps_file = open(self.gps_filename, "r", encoding="utf-8", newline="")
        self.accelerometer_reader = DictReader(self.accelerometer_file)
        self.gps_reader = DictReader(self.gps_file)

    def _read_next_accelerometer_row(self):
        return self._read_next_row(
            "accelerometer_reader",
            self.accelerometer_file,
            self.accelerometer_filename,
        )

    def _read_next_gps_row(self):
        return self._read_next_row("gps_reader", self.gps_file, self.gps_filename)

    def _read_next_row(self, reader_attr, file_handle, filename):
        try:
            return next(getattr(self, reader_attr))
        except StopIteration:
            file_handle.seek(0)
            setattr(self, reader_attr, DictReader(file_handle))
            return next(getattr(self, reader_attr))
