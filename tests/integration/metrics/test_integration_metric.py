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


import os
from typing import NewType, Any, Dict

import pytest
from assertpy import assert_that
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
import lib.gcp_apis
import lib.metric_ingest
from main import async_dynatrace_gcp_extension

AUTHORIZATION_KEY = "Fake secret - Open sesame"
METRIC_MESSAGE_DATA = '{}'
MOCKED_API_PORT = 9182

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)
system_variables: Dict = {
    'DYNATRACE_URL': 'http://localhost:' + str(MOCKED_API_PORT),
    'REQUIRE_VALID_CERTIFICATE': 'False',
    'GCP_SERVICES': "gce_instance/default,api/default,gce_instance/default,cloudsql_database/default,apigee.googleapis.com/Environment/default",
    'GCP_PROJECT': 'dynatrace-gcp-extension'
    # 'DYNATRACE_ACCESS_KEY': ACCESS_KEY, this one is encoded in mocks files
}


@pytest.fixture(scope="package", autouse=True)
def setup_test_variables(resource_path_root):
    lib.credentials._CLOUD_RESOURCE_MANAGER_ROOT = f"http://localhost:{MOCKED_API_PORT}/v1"
    lib.credentials._SECRET_ROOT = f"http://localhost:{MOCKED_API_PORT}/v1"
    lib.metric_ingest._MONITORING_ROOT = f"http://localhost:{MOCKED_API_PORT}/v3"
    lib.gcp_apis.GCP_SERVICE_USAGE_URL = f"http://localhost:{MOCKED_API_PORT}/v4/"
    lib.entities.extractors.cloud_sql._SQL_ENDPOINT = f"http://localhost:{MOCKED_API_PORT}"
    lib.entities.google_api._GCP_COMPUTE_ENDPOINT = f"http://localhost:{MOCKED_API_PORT}"
    lib.entities.extractors.gce_instance._GCP_COMPUTE_ENDPOINT = f"http://localhost:{MOCKED_API_PORT}"
    system_variables["GOOGLE_APPLICATION_CREDENTIALS"] = f"{resource_path_root}/metrics/token_for_tests.json"


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

    assert_that(matched_request.requests).is_not_empty()

    result: RequestResponseRequest = matched_request.requests[0]

    assert_that(result.headers['Authorization']).is_equal_to(f"Api-Token {AUTHORIZATION_KEY}")


@pytest.mark.asyncio
async def test_ingest_lines_output(resource_path_root):
    await async_dynatrace_gcp_extension()

    sent_requests = Requests.get_all_received_requests().get_json_data().get('requests')
    urls = {sent_request["request"]["url"] for sent_request in sent_requests}
    apigee_url_prefix = "/v3/projects/dynatrace-gcp-extension/timeSeries?filter=metric.type+%3D+%22apigee.googleapis.com/environment/anomaly_count"
    request_for_apigee_metric_was_sent = any(url.startswith(apigee_url_prefix) for url in urls)
    assert not request_for_apigee_metric_was_sent

    request = NearMissMatchPatternRequest(url_path_pattern="/api/v2/metrics/ingest",
                                          method="POST")

    r: RequestResponseFindResponse = Requests.get_matching_requests(request)

    assert_that(r.requests).is_not_empty()
    result: RequestResponseRequest = r.requests[0]

    body = result.body

    with open(os.path.join(resource_path_root, "metrics/ingest_input.dat")) as ingest:
        recorded_ingest = ingest.read()

        assert_that(body.split("\n")).is_length(289)
        assert_that(body_response).is_equal_to(recorded_ingest)
