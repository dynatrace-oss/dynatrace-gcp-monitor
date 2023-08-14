from unittest.mock import AsyncMock, patch

import pytest

from lib.autodiscovery.autodiscovery import get_metric_descriptors, get_project_ids
from lib.credentials import _CLOUD_RESOURCE_MANAGER_ROOT

response_json = {
    "metricDescriptors": [
        {
            "name": "projects/test_project/metricDescriptors/cloudfunctions.googleapis.com/function/sample_metric",
            "labels": [{"key": "key1", "description": "description1"}],
            "metricKind": "GAUGE",
            "valueType": "INT64",
            "displayName": "Metric 1",
            "unit": "1",
            "description": "Description Metric 1",
            "type": "cloudfunctions.googleapis.com/function/sample_metric",
            "metadata": {"launchStage": "GA", "samplePeriod": "60s", "ingestDelay": "240s"},
            "launchStage": "GA",
            "monitoredResourceTypes": ["cloud_function"],
        },
        {
            "name": "projects/test_project/metricDescriptors/cloudiot.googleapis.com/device/sample_other_metric",
            "labels": [{"key": "key2", "description": "description2"}],
            "metricKind": "GAUGE",
            "valueType": "INT64",
            "displayName": "Metric 2",
            "unit": "1",
            "description": "Description Metric 2",
            "type": "cloudiot.googleapis.com/device/active_devices",
            "metadata": {"launchStage": "GA", "samplePeriod": "60s", "ingestDelay": "240s"},
            "launchStage": "GA",
            "monitoredResourceTypes": ["cloudiot_device_registry"],
        },
    ]
}


@pytest.mark.asyncio
@patch("lib.autodiscovery.autodiscovery.fetch_dynatrace_api_key", return_value="test_api_key")
@patch("lib.autodiscovery.autodiscovery.fetch_dynatrace_url", return_value="test_project_id")
@patch(
    "lib.autodiscovery.autodiscovery.get_project_id_from_environment",
    return_value="test_project_id",
)
async def test_get_project_ids(fetch_url_mock, fetch_api_key_mock, get_project_id_mock):
    async def mocked_gcp_get(url, headers, params):
        response_mock = AsyncMock()
        if url == _CLOUD_RESOURCE_MANAGER_ROOT + "/projects":
            response_mock.json.return_value = {
                "projects": [{"projectId": "test_project_id"}, {"projectId": "other_project_id"}],
                "nextPageToken": "",
            }
        return response_mock

    gcp_session_mock = AsyncMock()
    dt_session_mock = AsyncMock()
    token_mock = "test_token"

    gcp_session_mock.get = mocked_gcp_get

    result = await get_project_ids(gcp_session_mock, dt_session_mock, token_mock)

    assert sorted(result, reverse=True) == ["test_project_id", "other_project_id"]


@pytest.mark.asyncio
@patch("lib.autodiscovery.autodiscovery.config")
@patch("lib.autodiscovery.autodiscovery.get_project_ids")
@patch("lib.autodiscovery.autodiscovery.discovered_resource_type", "cloud_function")
async def test_get_metric_descriptors(get_project_ids_mock, config_mock):
    token_mock = "test_token"
    config_mock.project_id.return_value = "test_project_id"
    get_project_ids_mock.return_value = ["test_project_id", "other_project_id"]

    response_mock = AsyncMock()
    response_mock.json.return_value = response_json

    gcp_session_mock = AsyncMock()
    gcp_session_mock.request.return_value = response_mock

    dt_session_mock = AsyncMock()

    result = await get_metric_descriptors(gcp_session_mock, dt_session_mock, token_mock)
    result = list(result.items())

    assert len(result) == 1
    assert sorted(result[0][1], reverse=True) == ["test_project_id", "other_project_id"]
    assert result[0][0].value == "cloudfunctions.googleapis.com/function/sample_metric"
    assert result[0][0].type == "gauge"
    assert result[0][0].gcpOptions.unit == "Count"
    assert len(result[0][0].dimensions) == 1

    assert result[0][0].dimensions[0].key == "key1"
    assert result[0][0].dimensions[0].value == "label:metric.labels.key1"
