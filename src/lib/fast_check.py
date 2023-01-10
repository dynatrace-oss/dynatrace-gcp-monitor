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
import json
import os
import re
from datetime import datetime
from queue import Queue
from typing import NamedTuple, List, Optional

from aiohttp import ClientSession

from lib.context import LoggingContext, get_should_require_valid_certificate
from lib.credentials import get_all_accessible_projects, fetch_dynatrace_url, fetch_dynatrace_api_key, \
    get_project_id_from_environment
from lib.instance_metadata import InstanceMetadata
from lib.logs.dynatrace_client import send_logs
from lib.logs.log_forwarder import create_logs_context
from lib.utilities import is_deployment_running_inside_cloud_function

service_name_pattern = re.compile(r"^projects\/([\w,-]*)\/services\/([\w,-.]*)$")

METRICS_CONFIGURATION_FLAGS = [
    "PRINT_METRIC_INGEST_INPUT",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "MAXIMUM_METRIC_DATA_POINTS_PER_MINUTE",
    "METRIC_INGEST_BATCH_SIZE",
    "GCP_PROJECT",
    "REQUIRE_VALID_CERTIFICATE",
    "SERVICE_USAGE_BOOKING",
    "USE_PROXY",
    "SELF_MONITORING_ENABLED",
    "QUERY_INTERVAL_MIN",
    "SCOPING_PROJECT_SUPPORT_ENABLED"
]

LOGS_CONFIGURATION_FLAGS = [
    "REQUIRE_VALID_CERTIFICATE",
    "DYNATRACE_LOG_INGEST_CONTENT_MAX_LENGTH",
    "DYNATRACE_LOG_INGEST_ATTRIBUTE_VALUE_MAX_LENGTH",
    "DYNATRACE_LOG_INGEST_REQUEST_MAX_EVENTS",
    "DYNATRACE_LOG_INGEST_REQUEST_MAX_SIZE",
    "DYNATRACE_TIMEOUT_SECONDS",
    "DYNATRACE_LOG_INGEST_EVENT_MAX_AGE_SECONDS",
    "GCP_PROJECT",
    "LOGS_SUBSCRIPTION_PROJECT",
    "LOGS_SUBSCRIPTION_ID",
    "DYNATRACE_LOG_INGEST_SENDING_WORKER_EXECUTION_PERIOD",
    "SELF_MONITORING_ENABLED",
    "USE_EXISTING_ACTIVE_GATE",
    "USE_PROXY"
]

REQUIRED_SERVICES = [
    'monitoring.googleapis.com',
    'cloudresourcemanager.googleapis.com'
]

DYNATRACE_REQUIRED_TOKEN_SCOPES = [
    'metrics.ingest',
    'extensions.read'
]

FastCheckResult = NamedTuple('FastCheckResult', [('projects', List[str])])


def find_service_name(service):
    return service_name_pattern.match(service).group(2) if service_name_pattern.match(service) else None


def valid_dynatrace_scopes(token_metadata: dict):
    """Check whether Dynatrace token metadata has required scopes to start ingest metrics"""
    token_scopes = token_metadata.get('scopes', [])
    return all(scope in token_scopes for scope in DYNATRACE_REQUIRED_TOKEN_SCOPES) if token_scopes else False


def check_version(logging_context: LoggingContext):
    script_directory = os.path.dirname(os.path.realpath(__file__))
    version_file_path = os.path.join(script_directory, "./../version.txt")
    with open(version_file_path) as version_file:
        _version = version_file.readline()
        logging_context.log(f"Found version: {_version}")


async def get_dynatrace_token_metadata(dt_session: ClientSession, context: LoggingContext, dynatrace_url: str, dynatrace_api_key: str, timeout: Optional[int] = 2) -> dict:
    try:
        response = await dt_session.post(
            url=f"{dynatrace_url.rstrip('/')}/api/v1/tokens/lookup",
            headers={
                "Authorization": f"Api-Token {dynatrace_api_key}",
                "Content-Type": "application/json; charset=utf-8"
            },
            json={
                "token": dynatrace_api_key
            },
            verify_ssl=get_should_require_valid_certificate(),
            timeout=timeout)
        if response.status != 200:
            context.log(f'Unable to get Dynatrace token metadata: {response.status}, url: {response.url}, reason: {response.reason}')
            return {}

        return await response.json()
    except Exception as e:
        context.log(f'Unable to get Dynatrace token metadata. Error details: {e}')
        return {}


def obfuscate_dynatrace_access_key(dynatrace_access_key: str):
    if len(dynatrace_access_key) >= 7:
        is_new_token = dynatrace_access_key.startswith("dt0c01.") and len(dynatrace_access_key) == 96
        if is_new_token:
            # characters between dots are the public part of the token
            return 'dt0c01.' + dynatrace_access_key.split('.')[1]
        else:
            return dynatrace_access_key[:3] + '*' * (len(dynatrace_access_key) - 6) + dynatrace_access_key[-3:]
    else:
        return "Invalid Token"


async def check_dynatrace(logging_context: LoggingContext, project_id: str, dt_session: ClientSession,
                          dynatrace_url: str, dynatrace_access_key: str) -> bool:
    try:
        if not dynatrace_url or not dynatrace_access_key:
            logging_context.log(f'ERROR No Dynatrace secrets: DYNATRACE_URL, DYNATRACE_ACCESS_KEY for project: {project_id}.'
                                     f'Add required secrets to Secret Manager.')
            return False
        logging_context.log(f"Using [DYNATRACE_URL] Dynatrace endpoint: {dynatrace_url}")
        logging_context.log(f'Using [DYNATRACE_ACCESS_KEY]: {obfuscate_dynatrace_access_key(dynatrace_access_key)}.')
        token_metadata = await get_dynatrace_token_metadata(dt_session, logging_context, dynatrace_url, dynatrace_access_key)
        if token_metadata.get('name', None):
            logging_context.log(f"Token name: {token_metadata.get('name')}.")
            if token_metadata.get('revoked', None) or not valid_dynatrace_scopes(token_metadata):
                logging_context.log(f'Dynatrace API Token for project: \'{project_id}\' is not valid. '
                                    f'Check expiration time and required token scopes: {DYNATRACE_REQUIRED_TOKEN_SCOPES}')
                return False
            return True
        return False
    except Exception as e:
        logging_context.log(f'Unable to get Dynatrace Secrets for project: {project_id}. Error details: {e}')
        return False


class MetricsFastCheck:

    def __init__(self, gcp_session: ClientSession, dt_session: ClientSession, token: str, logging_context: LoggingContext):
        self.gcp_session = gcp_session
        self.dt_session = dt_session
        self.logging_context = logging_context
        self.token = token

    async def is_project_ready_to_monitor(self, project_id):
        try:
            if is_deployment_running_inside_cloud_function():
                dynatrace_url = await fetch_dynatrace_url(self.gcp_session, project_id, self.token)
                dynatrace_access_key = await fetch_dynatrace_api_key(self.gcp_session, project_id, self.token)
                await check_dynatrace(logging_context=self.logging_context,
                                      project_id=get_project_id_from_environment(),
                                      dt_session=self.dt_session,
                                      dynatrace_url=dynatrace_url,
                                      dynatrace_access_key=dynatrace_access_key)
        except Exception as e:
            self.logging_context.log(f'Unable to get Dynatrace Secrets for project: {project_id}. Error details: {e}')
            return project_id, False
        return project_id, True

    async def execute(self) -> FastCheckResult:
        _check_configuration_flags(self.logging_context, METRICS_CONFIGURATION_FLAGS)

        project_list = await get_all_accessible_projects(self.logging_context, self.gcp_session, self.token)

        projects_ready_to_monitor = []
        tasks_to_find_ready_projects = []
        for project_id in project_list:
            tasks_to_find_ready_projects.append(self.is_project_ready_to_monitor(project_id))

        ready_project_task_results = await asyncio.gather(*tasks_to_find_ready_projects)
        for project_id, is_project_ready in ready_project_task_results:
            if is_project_ready:
                projects_ready_to_monitor.append(project_id)

        return FastCheckResult(projects=projects_ready_to_monitor)


class LogsFastCheck:
    def __init__(self, logging_context: LoggingContext, instance_metadata: InstanceMetadata):
        self.instance_metadata = instance_metadata
        self.logging_context = logging_context

    def execute(self):
        _check_configuration_flags(self.logging_context, LOGS_CONFIGURATION_FLAGS)
        check_version(self.logging_context)
        self.logging_context.log("Sending the startup message")
        container_name = self.instance_metadata.hostname if self.instance_metadata else "local deployment"
        fast_check_event = {
            'timestamp': datetime.utcnow().isoformat(" "),
            'cloud.provider': 'gcp',
            'content': f'GCP Log Forwarder has started at {container_name}',
            'severity': 'INFO'
        }
        send_logs(create_logs_context(Queue()), [], json.dumps([fast_check_event]))


def _check_configuration_flags(logging_context: LoggingContext, flags_to_check: List[str]):
    configuration_flag_values = []
    for key in flags_to_check:
        value = os.environ.get(key, None)
        if value is None:
            configuration_flag_values.append(f"{key} is None")
        else:
            configuration_flag_values.append(f"{key} = '{value}'")
    logging_context.log(f"Found configuration flags: {', '.join(configuration_flag_values)}")
