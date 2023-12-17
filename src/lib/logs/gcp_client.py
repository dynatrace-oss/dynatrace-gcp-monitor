#     Copyright 2021 Dynatrace LLC
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
import ssl
from typing import List, Tuple

import aiohttp

from lib.configuration import config
from lib.context import LoggingContext
from lib.logs.log_forwarder_variables import PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES, LOGS_SUBSCRIPTION_PROJECT, \
    LOGS_SUBSCRIPTION_ID

SUBSCRIPTION_PATH = f"projects/{LOGS_SUBSCRIPTION_PROJECT}/subscriptions/{LOGS_SUBSCRIPTION_ID}"


async def pull_messages_from_pubsub(gcp_session: aiohttp.ClientSession,
                                    token: str,
                                    logging_context: LoggingContext):
    pull_url = f"https://pubsub.googleapis.com/v1/{SUBSCRIPTION_PATH}:pull"
    try:
        status, reason, response = await _perform_http_request(
            session=gcp_session,
            method="POST",
            url=pull_url,
            json_body={
                "maxMessages": PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES
            },
            headers={
                "Authorization": f"Bearer {token}",
                "x-goog-user-project": f"{config.project_id()}"
            }
        )
        if status > 299:
            logging_context.log(f'Pull error: {status}, '
                                f'reason: {reason}, url: {pull_url}, body: "{str(response)}"')
    except Exception as e:
        logging_context.log(f'Failed to pull messages from pubsub: {pull_url}. {e}')
        raise e
    return response


async def send_ack_ids_to_pubsub(gcp_session: aiohttp.ClientSession,
                                 token: str,
                                 ack_ids: List[str],
                                 logging_context: LoggingContext):
    acknowledge_url = f"https://pubsub.googleapis.com/v1/{SUBSCRIPTION_PATH}:acknowledge"
    try:
        status, reason, response = await _perform_http_request(
            session=gcp_session,
            method="POST",
            url=acknowledge_url,
            json_body={
                "ackIds": ack_ids
            },
            headers={
                "Authorization": f"Bearer {token}",
                "x-goog-user-project": f"{config.project_id()}"
            }
        )
        if status > 299:
            logging_context.log(f'Acknowledgement error: {status}, '
                                f'reason: {reason}, url: {acknowledge_url}, body: "{str(response)}"')
    except Exception as e:
        logging_context.log(f'Failed to send_ack_ids_to_pubsub: {acknowledge_url}. {e}')
        raise e
    return


async def _perform_http_request(session, method, url, json_body, headers) -> Tuple[int, str, str]:
    async with session.request(method=method,
                               url=url,
                               json=json_body,
                               headers=headers,
                               ssl=ssl.create_default_context(),
                               timeout=aiohttp.ClientTimeout(total=30)) as response:
        response_json = await response.json()
        return response.status, response.reason, response_json
