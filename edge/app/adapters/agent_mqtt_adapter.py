import paho.mqtt.client as mqtt
from app.interfaces.agent_gateway import AgentGateway
from app.entities.agent_data import AgentData
from app.usecases.data_processing import process_agent_data
from app.interfaces.hub_gateway import HubGateway
import logging


class AgentMQTTAdapter(AgentGateway):
    def __init__(
        self,
        broker_host,
        broker_port,
        topic,
        hub_gateway: HubGateway,
        batch_size=10,
    ):
        self.batch_size = batch_size
        # MQTT
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic = topic
        self.client = mqtt.Client()
        # Hub
        self.hub_gateway = hub_gateway

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info("Connected to MQTT broker")
            self.client.subscribe(self.topic)
        else:
            logging.info(f"Failed to connect to MQTT broker with code: {rc}")

    def on_message(self, client, userdata, msg):
        """Process agent data and send it to the Hub gateway."""
        try:
            payload: str = msg.payload.decode("utf-8")
            agent_data = AgentData.model_validate_json(payload, strict=True)
            processed_data = process_agent_data(agent_data)
            if not self.hub_gateway.save_data(processed_data):
                logging.error("Hub is not available")
                return
            logging.info(
                "Forwarded processed road data: user_id=%s road_state=%s topic=%s",
                processed_data.agent_data.user_id,
                processed_data.road_state,
                msg.topic,
            )
        except Exception as e:
            logging.exception("Error processing MQTT message: %s", e)

    def connect(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(self.broker_host, self.broker_port, 60)

    def start(self):
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()

