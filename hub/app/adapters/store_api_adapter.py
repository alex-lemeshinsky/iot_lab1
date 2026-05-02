import logging
from typing import List

import requests

from app.entities.processed_agent_data import ProcessedAgentData
from app.interfaces.store_gateway import StoreGateway


class StoreApiAdapter(StoreGateway):
    def __init__(self, api_base_url):
        self.api_base_url = api_base_url

    def save_data(self, processed_agent_data_batch: List[ProcessedAgentData]) -> bool:
        """
        Save the processed road data to the Store API.
        Parameters:
            processed_agent_data_batch (dict): Processed road data batch to be saved.
        Returns:
            bool: True if the data is successfully saved, False otherwise.
        """
        if not processed_agent_data_batch:
            return True

        url = f"{self.api_base_url}/processed_agent_data/"
        payload = [
            processed_agent_data.model_dump(mode="json")
            for processed_agent_data in processed_agent_data_batch
        ]

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code not in (200, 201):
                logging.info(
                    "Invalid Store API response. Data: %s. Response: %s %s",
                    payload,
                    response.status_code,
                    response.text,
                )
                return False
            logging.info("Saved %s records to Store API", len(payload))
            return True
        except requests.RequestException as exc:
            logging.info("Store API request failed: %s", exc)
            return False
