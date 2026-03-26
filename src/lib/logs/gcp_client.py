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
import random
import time
from typing import Any, Dict, List, Callable

from aiohttp import ClientSession, ClientError

from lib.context import LoggingContext
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
    api_token: str
    token_expires_at: float
    context: LoggingContext
    
    # Class-level lock for token refresh operations to prevent thundering herd
    _refresh_lock = asyncio.Lock()

    def __init__(
        self,
        token_info,
        context: LoggingContext = None
    ):
        self.context = context
        # Note: Lock removed based on system reminder - keeping simpler version
        
        # token_info is expected to be dict with access_token and expires_at
        if isinstance(token_info, str):
            # Fallback for backward compatibility - assume 1 hour expiration
            self.api_token = token_info
            self.token_expires_at = time.time() + 3600
        else:
            self.api_token = token_info["access_token"]
            self.token_expires_at = token_info["expires_at"]
            
        self.subscription_path = (
            f"projects/{LOGS_SUBSCRIPTION_PROJECT}/subscriptions/{LOGS_SUBSCRIPTION_ID}"
        )
        self.pull_url = f"https://pubsub.googleapis.com/v1/{SUBSCRIPTION_PATH}:pull"
        self.acknowledge_url = f"https://pubsub.googleapis.com/v1/{SUBSCRIPTION_PATH}:acknowledge"
        self._update_headers()
        json_body = {"maxMessages": PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES}
        json_data = json.dumps(json_body)
        self.body_payload = json_data.encode("utf-8")
        self.update_gcp_client_in_the_next_loop = False
    
    def _update_headers(self):
        # Update headers with current token
        self.headers = {"Authorization": f"Bearer {self.api_token}"}
        
    def update_token(self, token_info):
        """Update token and expiration time with atomic rollback on failure"""
        # Backup current state for rollback
        old_token = self.api_token
        old_expires = self.token_expires_at
        old_headers = self.headers.copy()
        
        try:
            if isinstance(token_info, str):
                self.api_token = token_info
                self.token_expires_at = time.time() + 3600  # Fallback 1 hour
            elif isinstance(token_info, dict):
                if "access_token" not in token_info:
                    raise ValueError("Token info missing required 'access_token' field")
                self.api_token = token_info["access_token"]
                self.token_expires_at = token_info.get("expires_at", time.time() + 3600)
            else:
                raise ValueError(f"Invalid token_info type: {type(token_info)}")
                
            self._update_headers()
            self.update_gcp_client_in_the_next_loop = False
        except Exception as e:
            # Rollback to previous state on any failure
            self.api_token = old_token
            self.token_expires_at = old_expires
            self.headers = old_headers
            self.update_gcp_client_in_the_next_loop = True
            if self.context:
                self.context.log(f"Error updating token, rolled back: {e}")
            raise
    
    def is_token_expired(self) -> bool:
        # Check if token is expired or will expire soon
        return time.time() >= self.token_expires_at
    
    def _get_current_auth_state(self):
        """Atomically capture token state to prevent races"""
        return {
            'expired': self.is_token_expired(),
            'headers': self.headers.copy(),
            'token': self.api_token
        }

    async def pull_messages(
        self, logging_context: LoggingContext, gcp_session) -> Dict[str, List[Any]]:  # type: ignore
        # Atomically capture token state to prevent races
        auth_state = self._get_current_auth_state()
        
        if auth_state['expired']:
            self.update_gcp_client_in_the_next_loop = True

        async with gcp_session.request(
            method="POST", url=self.pull_url, data=self.body_payload, headers=auth_state['headers']
        ) as response:
            response_json = await response.json()
            resp_status = response.status

            if resp_status == 401:
                self.update_gcp_client_in_the_next_loop = True

            if resp_status > 299:
                logging_context.log(
                    f"Pull error: {resp_status}, "
                    f'reason: {response.reason}, url: {self.pull_url}, body: "{response_json}"'
                )
                response.raise_for_status()
            else:
                return response_json

    async def push_ack_ids(
        self,
        ack_ids: List[str],
        gcp_session: ClientSession,
        logging_context: LoggingContext,
        update_gcp_client: Callable[[ClientSession, LoggingContext], None],
    ):
        payload = {"ackIds": ack_ids}
        max_retries = 3
        initial_backoff = 1.0

        for attempt in range(max_retries):
            try:
                # Atomically capture token state to prevent races
                auth_state = self._get_current_auth_state()

                if auth_state['expired']:
                    await update_gcp_client(gcp_session, logging_context)
                    # Refresh auth state after token update
                    auth_state = self._get_current_auth_state()

                async with gcp_session.request(
                    method="POST", url=self.acknowledge_url, json=payload, headers=auth_state['headers']
                ) as response:
                    resp_status = response.status

                    if resp_status == 401:
                        await update_gcp_client(gcp_session, logging_context)
                    
                    if resp_status > 299:
                        # Retry on 5xx errors, 429 (Too Many Requests), or 401 (Unauthorized - token refreshed)
                        if attempt < max_retries - 1 and (resp_status >= 500 or resp_status == 429 or resp_status == 401):
                            backoff = initial_backoff * (2 ** attempt) + random.uniform(0, 0.5)
                            logging_context.log(f"ACK failed with {resp_status}, retrying in {backoff:.1f}s (attempt {attempt + 1}/{max_retries})")
                            await asyncio.sleep(backoff)
                            continue

                        logging_context.log(
                            f"Acknowledge error: {resp_status}, "
                            f'reason: {response.reason}, url: {self.acknowledge_url}, body: "{await response.text()}"'
                        )
                        response.raise_for_status()

                    return

            except (ClientError, asyncio.TimeoutError) as e:
                # Retry on network errors
                if attempt < max_retries - 1:
                    backoff = initial_backoff * (2 ** attempt) + random.uniform(0, 0.5)
                    logging_context.log(f"ACK request failed: {e}, retrying in {backoff:.1f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(backoff)
                else:
                    raise e
