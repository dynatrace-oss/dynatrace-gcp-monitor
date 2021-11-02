import asyncio
import re
from typing import NewType, Any

import pytest
from aiohttp import ClientSession
from assertpy import assert_that
from pytest_mock import MockerFixture

from lib.context import LoggingContext
from lib.extensions_fetcher import ExtensionsFetcher

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)
ACTIVATION_CONFIG = "{services: [{service: gce_instance, featureSets: [default_metrics, agent], vars: {filter_conditions: ''}},\
 {service: cloudsql_database, featureSets: [default_metrics], vars: {filter_conditions: ''}}]}"

@pytest.fixture(scope="function", autouse=True)
def setup_env(monkeypatch, resource_path_root):
    # NO filestore/default configured
    monkeypatch.setenv("ACTIVATION_CONFIG", ACTIVATION_CONFIG)
    Response.resource_path_root = resource_path_root


class Response:
    resource_path_root = ""

    def __init__(self, extension_name: str = "", version: str = ""):
        self.extension_name = extension_name
        self.version = version
        self.status = 200
        self.url = ""
        self.reason = ""

    async def json(self):
        return {"extensions": [{"extensionName": "com.dynatrace.extension.google-sql", "version": "0.0.3"},
                               {"extensionName": "com.dynatrace.extension.google-filestore", "version": "0.0.3"},
                               {"extensionName": "com.dynatrace.extension.google-compute-engine", "version": "0.0.3"},
                               {"extensionName": "com.dynatrace.extension.google-compute-engine", "version": "0.0.4"}
                               ]}

    async def read(self):
        extension_filename = f"{Response.resource_path_root}/extensions/{self.extension_name}-{self.version}.zip"
        with open(extension_filename, 'rb') as zip_data:
            return zip_data.read()


def mocked_get(url: str, headers={}, params={}, verify_ssl=False):
    returned_future = asyncio.Future()
    if url == "/api/v2/extensions":
        returned_future.set_result(Response())
    else:
        name_version_searcher = re.search("/api/v2/extensions/(.+)/(.+)", url)
        if name_version_searcher:
            returned_future.set_result(Response(extension_name=name_version_searcher.group(1), version=name_version_searcher.group(2)))
        else:
            returned_future.set_result(None)
    return returned_future

@pytest.mark.asyncio
async def test_execute(mocker: MockerFixture):
    dt_session = ClientSession()
    mocker.patch.object(dt_session, 'get', side_effect=mocked_get)

    extensions_fetcher = ExtensionsFetcher(dt_session, "", "", LoggingContext("TEST"))
    result = await extensions_fetcher.execute()
    assert_that(result).is_not_none()
    services_names = [f"{gcp_service_config.name}/{gcp_service_config.feature_set}" for gcp_service_config in result.services]
    assert_that(services_names).contains_only("gce_instance/", "gce_instance/agent", "cloudsql_database/")
