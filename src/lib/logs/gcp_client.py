#   Copyright 2024 Dynatrace LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import asyncio
import json
from typing import Any, Dict, List, Callable

from lib.clientsession_provider import init_gcp_client_session
from lib.context import LoggingContext
from lib.credentials import create_token
from lib.logs.log_forwarder_variables import (
    LOGS_SUBSCRIPTION_ID,
    LOGS_SUBSCRIPTION_PROJECT,
    PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES,
)

SUBSCRIPTION_PATH = f"projects/{LOGS_SUBSCRIPTION_PROJECT}/subscriptions/{LOGS_SUBSCRIPTION_ID}"


class GCPClient:
    subscription_path: str
    pull_url: str
    acknowledge_url: str
    body_payload: bytes
    headers: Dict[str, Any]

    def __init__(
        self,
        api_token: str,
    ):
        self.subscription_path = (
            f"projects/{LOGS_SUBSCRIPTION_PROJECT}/subscriptions/{LOGS_SUBSCRIPTION_ID}"
        )
        self.pull_url = f"https://pubsub.googleapis.com/v1/{SUBSCRIPTION_PATH}:pull"
        self.acknowledge_url = f"https://pubsub.googleapis.com/v1/{SUBSCRIPTION_PATH}:acknowledge"
        self.headers = {"Authorization": f"Bearer {api_token}"}
        json_body = {"maxMessages": PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES}
        json_data = json.dumps(json_body)
        self.body_payload = json_data.encode("utf-8")

    async def pull_messages(
        self, logging_context: LoggingContext, gcp_session, update_gcp_client: Callable[[LoggingContext], None]
    ) -> Dict[str, List[Any]]:  # type: ignore
        async with gcp_session.request(
            method="POST", url=self.pull_url, data=self.body_payload, headers=self.headers
        ) as response:
            response_json = await response.json()
            resp_status = response.status

            if resp_status == 401:
                await update_gcp_client(logging_context)

            if resp_status > 299:
                logging_context.log(
                    f"Pull error: {resp_status}, "
                    f'reason: {response.reason}, url: {self.pull_url}, body: "{response_json}"'
                )
                response.raise_for_status()
            else:
                return response_json

    async def push_ack_ids(self, ack_ids: List[str], gcp_session, logging_context: LoggingContext):
        payload = {"ackIds": ack_ids}

        async with gcp_session.request(
            method="POST", url=self.acknowledge_url, json=payload, headers=self.headers
        ) as response:
            resp_status = response.status

            if resp_status > 299:
                logging_context.log(
                    f"Pull error: {resp_status}, "
                    f'reason: {response.reason}, url: {self.acknowledge_url}, body: "{await response.json()}"'
                )
                response.raise_for_status()
