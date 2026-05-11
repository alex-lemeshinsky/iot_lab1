from datetime import datetime
import unittest

from app.entities.agent_data import AccelerometerData, AgentData, GpsData
from app.usecases.data_processing import process_agent_data


def make_agent_data(x=0, y=0, z=16500):
    return AgentData(
        user_id=1,
        accelerometer=AccelerometerData(x=x, y=y, z=z),
        gps=GpsData(latitude=50.4511, longitude=30.5251),
        timestamp=datetime.fromisoformat("2026-05-02T16:30:00"),
    )


class DataProcessingTest(unittest.TestCase):
    def test_normal_road_state(self):
        processed_data = process_agent_data(make_agent_data())

        self.assertEqual(processed_data.road_state, "normal")
        self.assertEqual(processed_data.agent_data.user_id, 1)

    def test_pothole_for_low_z_axis_value(self):
        processed_data = process_agent_data(make_agent_data(z=9000))

        self.assertEqual(processed_data.road_state, "pothole")

    def test_pothole_for_negative_y_axis_impact(self):
        processed_data = process_agent_data(make_agent_data(y=-7000))

        self.assertEqual(processed_data.road_state, "pothole")

    def test_bump_for_high_z_axis_value(self):
        processed_data = process_agent_data(make_agent_data(z=23000))

        self.assertEqual(processed_data.road_state, "bump")

    def test_bump_for_positive_y_axis_impact(self):
        processed_data = process_agent_data(make_agent_data(y=7000))

        self.assertEqual(processed_data.road_state, "bump")


if __name__ == "__main__":
    unittest.main()
