#   Copyright 2021 Dynatrace LLC
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
import os
import socket
from collections import namedtuple
from typing import Optional
from urllib.parse import urljoin, urlparse

import jwt
from aiohttp import ClientSession

from lib.context import LoggingContext

METADATA_URL = os.environ.get('GCP_METADATA_URL', 'http://metadata.google.internal/computeMetadata/v1')

InstanceMetadata = namedtuple('InstanceMetadata', [
    'project_id',
    'container_name',
    'token_scopes',
    'service_account',
    'audience',
    'hostname',
    'zone'
])


class InstanceMetadataCheck:

    def __init__(self, gcp_session: ClientSession(), token: [str], logging_context: LoggingContext):
        self.gcp_session = gcp_session
        self.token = token
        self.logging_context = logging_context

    async def _get_metadata(self, url_path: str, timeout: Optional[int] = 2):
        try:
            response = await self.gcp_session.get(
                urljoin(METADATA_URL, url_path),
                headers={
                    "Authorization": f'Bearer {self.token}',
                    'Metadata-Flavor': 'Google'
                },
                timeout=timeout)
            if response.status != 200:
                self.logging_context.log(f'Http error: {response.status}, url: {response.url}, reason: {response.reason}')
                return None
            return await response.text()
        except Exception as e:
            self.logging_context.log(f'Cannot get instance metadata: {urljoin(METADATA_URL, url_path)}. {e}')
            return None

    async def project_id(self):
        await self._get_metadata('/project/project-id')

    async def running_container(self):
        return await self._get_metadata('/instance/hostname')

    async def token_scopes(self):
        return await self._get_metadata('/instance/service-accounts/default/scopes')

    async def service_accounts(self):
        return await self._get_metadata('/instance/service-accounts')

    async def audience(self):
        return await self._get_metadata('/instance/service-accounts/default/identity?audience=https://accounts.google.com')

    async def zone(self):
        return await self._get_metadata('/instance/zone')

    async def execute(self) -> Optional[InstanceMetadata]:
        if self._gcp_deployment():
            metadata = [
                self.project_id(),
                self.running_container(),
                self.token_scopes(),
                self.service_accounts(),
                self.audience(),
                self.zone()
            ]

            results = await asyncio.gather(*metadata, return_exceptions=True)

            if not all(result is None for result in results):
                audience = jwt.decode(results[4], verify=False) if results[4] else ''
                # zone = "projects/<projectID>/zones/us-central1-c"
                zone = results[5].split("/")[-1] if results[5] else "us-east1"
                metadata = InstanceMetadata(
                    project_id=results[0],
                    container_name=results[1],
                    token_scopes=results[2],
                    service_account=results[3],
                    audience=audience,
                    hostname=os.environ.get("HOSTNAME", ""),
                    zone=zone
                )
                self.logging_context.log(f'GCP instance metadata: {metadata}')
                return metadata
            return None

    def _gcp_deployment(self):
        try:
            hostname = urlparse(METADATA_URL).hostname
            self.logging_context.log(f'Resolved host: {hostname} info: {socket.getaddrinfo(hostname, 80)}')
            return True
        except Exception as e:
            self.logging_context.log(f'Local deployment detected. Skipped instance metadata info, the reason is: {e}')
            return False
