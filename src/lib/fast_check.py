import asyncio
import json
import os
import re
from datetime import datetime
from queue import Queue
from typing import NamedTuple, List, Optional
from urllib.parse import urljoin

from aiohttp import ClientSession

from lib.context import LoggingContext, get_should_require_valid_certificate
from lib.credentials import get_all_accessible_projects, fetch_dynatrace_url, fetch_dynatrace_api_key, \
    get_project_id_from_environment
from lib.instance_metadata import InstanceMetadata
from lib.logs.dynatrace_client import send_logs
from lib.logs.log_forwarder import create_logs_context

service_name_pattern = re.compile(r"^projects\/([\w,-]*)\/services\/([\w,-.]*)$")

METRICS_CONFIGURATION_FLAGS = [
    "PRINT_METRIC_INGEST_INPUT",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "MAXIMUM_METRIC_DATA_POINTS_PER_MINUTE",
    "METRIC_INGEST_BATCH_SIZE",
    "REQUIRE_VALID_CERTIFICATE",
    "SERVICE_USAGE_BOOKING",
    "USE_PROXY",
    "IMPORT_DASHBOARDS",
    "IMPORT_ALERTS",
    "SELF_MONITORING_ENABLED"
]

LOGS_CONFIGURATION_FLAGS = [
    "REQUIRE_VALID_CERTIFICATE",
    "DYNATRACE_LOG_INGEST_CONTENT_MAX_LENGTH",
    "DYNATRACE_LOG_INGEST_ATTRIBUTE_VALUE_MAX_LENGTH",
    "DYNATRACE_LOG_INGEST_REQUEST_MAX_EVENTS",
    "DYNATRACE_LOG_INGEST_REQUEST_MAX_SIZE",
    "DYNATRACE_TIMEOUT_SECONDS",
    "DYNATRACE_LOG_INGEST_EVENT_MAX_AGE_SECONDS",
    "LOGS_SUBSCRIPTION_PROJECT",
    "LOGS_SUBSCRIPTION_ID",
    "DYNATRACE_LOG_INGEST_SENDING_WORKER_EXECUTION_PERIOD",
    "SELF_MONITORING_ENABLED"
]

GCP_SERVICE_USAGE_URL = 'https://serviceusage.googleapis.com/v1/projects/'

REQUIRED_SERVICES = [
    'monitoring.googleapis.com',
    'cloudresourcemanager.googleapis.com'
]

DYNATRACE_REQUIRED_TOKEN_SCOPES = [
    'metrics.ingest',
]

FastCheckResult = NamedTuple('FastCheckResult', [('projects', List[str])])


def find_service_name(service):
    return service_name_pattern.match(service).group(2) if service_name_pattern.match(service) else None


def valid_dynatrace_scopes(token_metadata: dict):
    """Check whether Dynatrace token metadata has required scopes to start ingest metrics"""
    token_scopes = token_metadata.get('scopes', [])
    return all(scope in token_scopes for scope in DYNATRACE_REQUIRED_TOKEN_SCOPES) if token_scopes else False


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


class MetricsFastCheck:

    def __init__(self, gcp_session: ClientSession, dt_session: ClientSession, token: str, logging_context: LoggingContext):
        self.gcp_session = gcp_session
        self.dt_session = dt_session
        self.logging_context = logging_context
        self.token = token

    async def list_services(self, project_id: str, timeout: Optional[int] = 2):
        try:
            response = await self.gcp_session.get(
                urljoin(GCP_SERVICE_USAGE_URL, f'{project_id}/services'),
                headers={
                    "Authorization": f'Bearer {self.token}'
                },
                params={
                    "filter": "state:ENABLED"
                },
                timeout=timeout)
            if response.status != 200:
                self.logging_context.log(f'Http error: {response.status}, url: {response.url}, reason: {response.reason}')
                return {}

            return await response.json()
        except Exception as e:
            self.logging_context.log(f'Unable to get project: {project_id} services list. Error details: {e}')
            return {}

    async def _check_services(self, project_id):
        list_services_result = await self.list_services(project_id)
        service_names = [find_service_name(service['name']) for service in list_services_result.get('services', [])]
        if not all(name in service_names for name in REQUIRED_SERVICES):
            self.logging_context.log(f'Cannot monitor project: \'{project_id}\'. '
                                     f'Enable required services: {REQUIRED_SERVICES}')
            return None
        return service_names

    async def _check_dynatrace(self, project_id):
        try:
            dynatrace_url = await fetch_dynatrace_url(self.gcp_session, project_id, self.token)
            dynatrace_access_key = await fetch_dynatrace_api_key(self.gcp_session, project_id, self.token)
            if not dynatrace_url or not dynatrace_access_key:
                self.logging_context.log(f'No Dynatrace secrets: DYNATRACE_URL, DYNATRACE_ACCESS_KEY for project: {project_id}.'
                                         f'Add required secrets to Secret Manager.')
                return None

            token_metadata = await get_dynatrace_token_metadata(self.dt_session, self.logging_context, dynatrace_url, dynatrace_access_key)
            if token_metadata.get('revoked', None) or not valid_dynatrace_scopes(token_metadata):
                self.logging_context.log(f'Dynatrace API Token for project: \'{project_id}\'is not valid. '
                                         f'Check expiration time and required token scopes: {DYNATRACE_REQUIRED_TOKEN_SCOPES}')
                return None
        except Exception as e:
            self.logging_context.log(f'Unable to get Dynatrace Secrets for project: {project_id}. Error details: {e}')
            return None

        return dynatrace_url, token_metadata

    async def execute(self) -> FastCheckResult:
        _check_configuration_flags(self.logging_context, METRICS_CONFIGURATION_FLAGS)
        _check_version(self.logging_context)

        project_list = await get_all_accessible_projects(self.logging_context, self.gcp_session, self.token)

        ready_to_monitor = []
        for project_id in project_list:
            tasks = [self._check_services(project_id)]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            if all(result is not None for result in results):
                ready_to_monitor.append(project_id)

        await self._check_dynatrace(get_project_id_from_environment())

        return FastCheckResult(projects=ready_to_monitor)


class LogsFastCheck:
    def __init__(self, logging_context: LoggingContext, instance_metadata: InstanceMetadata):
        self.instance_metadata = instance_metadata
        self.logging_context = logging_context

    def execute(self):
        _check_configuration_flags(self.logging_context, LOGS_CONFIGURATION_FLAGS)
        _check_version(self.logging_context)
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


def _check_version(logging_context: LoggingContext):
    script_directory = os.path.dirname(os.path.realpath(__file__))
    version_file_path = os.path.join(script_directory, "./../version.txt")
    with open(version_file_path) as version_file:
        _version = version_file.readline()
        logging_context.log(f"Found version: {_version}")
