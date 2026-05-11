from app.entities.agent_data import AgentData
from app.entities.processed_agent_data import ProcessedAgentData


NORMAL_GRAVITY_Z = 16500
POTHOLE_Z_THRESHOLD = 12000
BUMP_Z_THRESHOLD = 20000
Y_AXIS_IMPACT_THRESHOLD = 5000


def classify_road_state(agent_data: AgentData) -> str:
    accelerometer = agent_data.accelerometer

    if (
        accelerometer.z <= POTHOLE_Z_THRESHOLD
        or accelerometer.y <= -Y_AXIS_IMPACT_THRESHOLD
    ):
        return "pothole"

    if (
        accelerometer.z >= BUMP_Z_THRESHOLD
        or accelerometer.y >= Y_AXIS_IMPACT_THRESHOLD
    ):
        return "bump"

    z_deviation = abs(accelerometer.z - NORMAL_GRAVITY_Z)
    if z_deviation >= Y_AXIS_IMPACT_THRESHOLD:
        return "bump"

    return "normal"


def process_agent_data(
    agent_data: AgentData,
) -> ProcessedAgentData:
    """
    Process agent data and classify the state of the road surface.
    Parameters:
        agent_data (AgentData): Agent data that containing accelerometer, GPS, and timestamp.
    Returns:
        processed_data_batch (ProcessedAgentData): Processed data containing the classified state of the road surface and agent data.
    """
    return ProcessedAgentData(
        road_state=classify_road_state(agent_data),
        agent_data=agent_data,
    )
