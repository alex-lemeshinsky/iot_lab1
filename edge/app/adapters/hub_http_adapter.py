import logging

import requests

from app.entities.processed_agent_data import ProcessedAgentData
from app.interfaces.hub_gateway import HubGateway


class HubHttpAdapter(HubGateway):
    def __init__(self, api_base_url):
        self.api_base_url = api_base_url

    def save_data(self, processed_data: ProcessedAgentData):
        """
        Save the processed road data to the Hub.
        Parameters:
            processed_data (ProcessedAgentData): Processed road data to be saved.
        Returns:
            bool: True if the data is successfully saved, False otherwise.
        """
        url = f"{self.api_base_url}/processed_agent_data/"

        payload = processed_data.model_dump(mode="json")
        try:
            response = requests.post(url, json=payload, timeout=10)
        except requests.RequestException as exc:
            logging.info("Hub HTTP request failed: %s", exc)
            return False

        if response.status_code not in (200, 201):
            logging.info(
                "Invalid Hub response. Data: %s. Response: %s %s",
                payload,
                response.status_code,
                response.text,
            )
            return False
        return True
