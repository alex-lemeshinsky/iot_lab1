import asyncio
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy_garden.mapview import MapMarker, MapView

import config
from datasource import FileDatasource, StoreDatasource, MapPoint
from lineMapLayer import LineMapLayer


IMAGE_DIR = Path(__file__).resolve().parent / "images"
ROAD_STATE_LABELS = {
    "normal": "норма",
    "bump": "перешкода",
    "pothole": "яма",
}


class MapViewApp(App):
    def __init__(self, **kwargs):
        super().__init__()
        self.mapview = None
        self.status_label = None
        self.route_layer = None
        self.file_datasource = None
        self.store_datasource = None
        self.car_marker = None
        self.defect_markers = set()
        self.total_points = 0
        self.total_store_points = 0
        self.total_csv_points = 0
        self.source_mode = config.MAPVIEW_SOURCE.lower()

    def on_start(self):
        """
        Встановлює необхідні маркери, викликає функцію для оновлення мапи
        """
        self.route_layer = LineMapLayer(coordinates=[], color=[0.08, 0.42, 0.78, 0.9], width=3)
        self.mapview.add_layer(self.route_layer, mode="scatter")

        if self.source_mode in ("file", "csv", "both"):
            self.file_datasource = FileDatasource(
                config.CSV_ACCELEROMETER_FILE,
                config.CSV_GPS_FILE,
            )
            for point in self.file_datasource.read_many(config.INITIAL_CSV_POINTS):
                self.add_point(point)

        if self.source_mode in ("store", "both"):
            self.store_datasource = StoreDatasource(
                user_id=config.USER_ID,
                host=config.STORE_HOST,
                port=config.STORE_PORT,
                preload_limit=config.STORE_PRELOAD_LIMIT,
            )
            self.store_datasource.start()

        Clock.schedule_interval(self.update, config.UPDATE_INTERVAL)
        self.update_status()

    def update(self, *args):
        """
        Викликається регулярно для оновлення мапи
        """
        points = []
        if self.file_datasource is not None:
            points.append(self.file_datasource.read_next())

        if self.store_datasource is not None:
            points.extend(self.store_datasource.get_new_points())

        for point in points:
            self.add_point(point)

        self.update_status()

    def update_car_marker(self, point):
        """
        Оновлює відображення маркера машини на мапі
        :param point: GPS координати
        """
        if self.car_marker is None:
            self.car_marker = MapMarker(
                lat=point.latitude,
                lon=point.longitude,
                source=str(IMAGE_DIR / "car.png"),
            )
            self.mapview.add_marker(self.car_marker)
        else:
            self.car_marker.lat = point.latitude
            self.car_marker.lon = point.longitude

        self.mapview.center_on(point.latitude, point.longitude)

    def set_pothole_marker(self, point):
        """
        Встановлює маркер для ями
        :param point: GPS координати
        """
        self.set_defect_marker(point, "pothole.png")

    def set_bump_marker(self, point):
        """
        Встановлює маркер для лежачого поліцейського
        :param point: GPS координати
        """
        self.set_defect_marker(point, "bump.png")

    def set_defect_marker(self, point: MapPoint, image_name: str):
        key = (point.road_state, round(point.latitude, 5), round(point.longitude, 5))
        if key in self.defect_markers:
            return

        marker = MapMarker(
            lat=point.latitude,
            lon=point.longitude,
            source=str(IMAGE_DIR / image_name),
        )
        self.mapview.add_marker(marker)
        self.defect_markers.add(key)

    def add_point(self, point: MapPoint):
        if not (-90 <= point.latitude <= 90 and -180 <= point.longitude <= 180):
            return

        self.route_layer.add_point((point.latitude, point.longitude))
        self.update_car_marker(point)
        self.total_points += 1
        if point.source.startswith("store"):
            self.total_store_points += 1
        if point.source == "csv":
            self.total_csv_points += 1

        if point.road_state == "pothole":
            self.set_pothole_marker(point)
        elif point.road_state == "bump":
            self.set_bump_marker(point)

    def update_status(self):
        if self.status_label is None:
            return

        store_status = (
            self.store_datasource.connection_status
            if self.store_datasource is not None
            else "off"
        )
        self.status_label.text = (
            f"MapView | джерело: {self.source_mode} | "
            f"точок: {self.total_points} | CSV: {self.total_csv_points} | "
            f"Store: {self.total_store_points} | WS: {store_status}"
        )

    def build(self):
        """
        Ініціалізує мапу MapView(zoom, lat, lon)
        :return: мапу
        """
        root = BoxLayout(orientation="vertical")
        self.status_label = Label(
            text="MapView",
            size_hint_y=None,
            height=34,
            color=(1, 1, 1, 1),
            bold=True,
        )
        self.mapview = MapView(zoom=15, lat=50.450386085935094, lon=30.524547100067142)
        root.add_widget(self.status_label)
        root.add_widget(self.mapview)
        return root


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(MapViewApp().async_run(async_lib="asyncio"))
    loop.close()
