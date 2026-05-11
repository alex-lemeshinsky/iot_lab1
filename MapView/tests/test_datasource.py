import json
import tempfile
import unittest
from pathlib import Path

from datasource import (
    FileDatasource,
    StoreDatasource,
    classify_road_state,
    map_point_from_store_record,
    normalize_coordinates,
)


class DatasourceTestCase(unittest.TestCase):
    def test_classifies_road_state_like_edge_logic(self):
        self.assertEqual(classify_road_state(0, 0, 16500), "normal")
        self.assertEqual(classify_road_state(0, 6000, 16500), "bump")
        self.assertEqual(classify_road_state(0, -6000, 16500), "pothole")
        self.assertEqual(classify_road_state(0, 0, 21000), "bump")
        self.assertEqual(classify_road_state(0, 0, 11000), "pothole")

    def test_file_datasource_pairs_accelerometer_and_gps_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            accelerometer = tmp_path / "accelerometer.csv"
            gps = tmp_path / "gps.csv"
            accelerometer.write_text("X,Y,Z\n0,0,16500\n0,6000,16500\n", encoding="utf-8")
            gps.write_text(
                "latitude,longitude\n50.45,30.52\n50.46,30.53\n",
                encoding="utf-8",
            )

            datasource = FileDatasource(str(accelerometer), str(gps))
            first, second = datasource.read_many(2)
            datasource.stop_reading()

        self.assertEqual(first.road_state, "normal")
        self.assertEqual((first.latitude, first.longitude), (50.45, 30.52))
        self.assertEqual(second.road_state, "bump")
        self.assertEqual((second.latitude, second.longitude), (50.46, 30.53))

    def test_store_datasource_accepts_flattened_websocket_payload(self):
        datasource = StoreDatasource(user_id=1)
        datasource.handle_received_data(
            json.dumps(
                {
                    "id": 1,
                    "road_state": "pothole",
                    "user_id": 1,
                    "x": 0,
                    "y": -7000,
                    "z": 11000,
                    "latitude": 50.45,
                    "longitude": 30.52,
                    "timestamp": "2026-05-02T16:30:00",
                }
            )
        )

        points = datasource.get_new_points()

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].road_state, "pothole")
        self.assertEqual((points[0].latitude, points[0].longitude), (50.45, 30.52))

    def test_store_record_supports_nested_processed_contract(self):
        point = map_point_from_store_record(
            {
                "road_state": "bump",
                "agent_data": {
                    "user_id": 1,
                    "accelerometer": {"x": 0, "y": 6000, "z": 16500},
                    "gps": {"latitude": 50.45, "longitude": 30.52},
                    "timestamp": "2026-05-02T16:30:00",
                },
            }
        )

        self.assertEqual(point.road_state, "bump")
        self.assertEqual((point.latitude, point.longitude), (50.45, 30.52))

    def test_normalizes_legacy_swapped_kyiv_coordinates(self):
        self.assertEqual(normalize_coordinates(30.52, 50.45), (50.45, 30.52))


if __name__ == "__main__":
    unittest.main()
