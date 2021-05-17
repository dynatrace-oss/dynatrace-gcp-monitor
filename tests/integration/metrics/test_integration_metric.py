#     Copyright 2020 Dynatrace LLC
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


import base64
import os
from typing import NewType, Any, Dict

import pytest
from pytest_mock import MockerFixture
from wiremock.constants import Config
from wiremock.resources.near_misses import NearMissMatchPatternRequest
from wiremock.resources.requests import RequestResponseFindResponse, RequestResponseRequest
from wiremock.resources.requests.resource import Requests
from wiremock.server import WireMockServer

import lib.credentials
import lib.entities.extractors.cloud_sql
import lib.entities.extractors.gce_instance
import lib.entities.google_api
import lib.metric_ingest
from lib.clientsession_provider import init_gcp_client_session
from lib.context import LoggingContext
from lib.credentials import fetch_dynatrace_api_key, create_token
from main import async_dynatrace_gcp_extension
from assertpy import assert_that

AUTHORIZATION_KEY = b"Fake secret - Open sesame"
METRIC_MESSAGE_DATA = '{}'
MOCKED_API_PORT = 9182

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)
system_variables: Dict = {
    'DYNATRACE_URL': 'http://localhost:' + str(MOCKED_API_PORT),
    'REQUIRE_VALID_CERTIFICATE': 'False'
    # 'DYNATRACE_ACCESS_KEY': ACCESS_KEY, this one is encoded in mocks files
    # 'GCP_SERVICES': "gce_instance/default,api/default,gce_instance/default,cloudsql_database/default"
}


@pytest.fixture(scope="package", autouse=True)
def setup_test_variables(resource_path_root):
    lib.credentials._CLOUD_RESOURCE_MANAGER_ROOT = f"http://localhost:{MOCKED_API_PORT}/v1"
    lib.credentials._SECRET_ROOT = f"http://localhost:{MOCKED_API_PORT}/v1"
    lib.metric_ingest._MONITORING_ROOT = f"http://localhost:{MOCKED_API_PORT}/v3"
    lib.entities.extractors.cloud_sql._SQL_ENDPOINT = f"http://localhost:{MOCKED_API_PORT}"
    lib.entities.google_api._GCP_COMPUTE_ENDPOINT = f"http://localhost:{MOCKED_API_PORT}"
    lib.entities.extractors.gce_instance._GCP_COMPUTE_ENDPOINT = f"http://localhost:{MOCKED_API_PORT}"

    system_variables.update({
        'GOOGLE_APPLICATION_CREDENTIALS': f"{resource_path_root}/metrics/token_for_tests.json",
    })


@pytest.fixture(scope="function", autouse=True)
def setup_config(resource_path_root, mocker: MockerFixture):
    # change the config dir
    patched = mocker.patch('os.path.dirname')
    patched.return_value = os.path.join(resource_path_root, "metrics")


@pytest.fixture(scope="function", autouse=True)
def setup_env(monkeypatch, resource_path_root):
    for variable_name in system_variables:
        monkeypatch.setenv(variable_name, system_variables[variable_name])


@pytest.fixture(scope="function", autouse=True)
def clean_journal():
    Requests.reset_request_journal()


@pytest.fixture(scope="session", autouse=True)
def setup_wiremock():
    # setup WireMock server

    wiremock = None
    Config.base_url = 'http://localhost:{}/__admin'.format(MOCKED_API_PORT)

    wiremock = WireMockServer(port=MOCKED_API_PORT)
    wiremock.start()

    print("wiremock running")

    # run test
    yield

    # stop WireMock server

    wiremock.stop()


@pytest.mark.asyncio
async def test_metric_authorization_header():
    await async_dynatrace_gcp_extension()

    request = NearMissMatchPatternRequest(url_path_pattern="/api/v2/metrics/ingest",
                                          method="POST")

    matched_request: RequestResponseFindResponse = Requests.get_matching_requests(request)

    assert_that(matched_request).is_not_empty()

    result: RequestResponseRequest = matched_request.requests[0]
    api_key = await get_dynatrace_secret_api_key()

    assert_that(result.headers['Authorization']).is_equal_to(f"Api-Token {api_key}")


async def get_dynatrace_secret_api_key():
    context = LoggingContext(None)
    async with init_gcp_client_session() as gcp_session:
        token = await create_token(context, gcp_session)
        return await fetch_dynatrace_api_key(gcp_session=gcp_session, project_id="dynatrace-gcp-extension",
                                             token=token)


@pytest.mark.asyncio
async def test_ingest_lines_output(resource_path_root):
    await async_dynatrace_gcp_extension()

    request = NearMissMatchPatternRequest(url_path_pattern="/api/v2/metrics/ingest",
                                          method="POST")

    r: RequestResponseFindResponse = Requests.get_matching_requests(request)

    assert_that(r.requests).is_not_empty()
    result: RequestResponseRequest = r.requests[0]

    body = result.body

    with open(os.path.join(resource_path_root, "metrics/ingest_input.dat")) as ingest:
        assert_that(ingest.readlines()).is_length(289)
        ingest.seek(0)
        recorded_ingest = ingest.read()
        assert_that(body).is_equal_to(recorded_ingest)


def create_authorization_payload():
    payload_text = base64.b64encode(AUTHORIZATION_KEY)
    print(payload_text)
