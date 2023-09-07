from unittest.mock import AsyncMock, patch

import pytest

from lib.autodiscovery.autodiscovery import (
    AutodiscoveryResourceLinking,
    get_metric_descriptors,
)

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

    metric_context = AsyncMock()

    ad_resources_to_services_mock = {"cloud_function": AutodiscoveryResourceLinking(None,None)}

    result = await get_metric_descriptors(metric_context, gcp_session_mock, token_mock,ad_resources_to_services_mock)
    result = list(result.items())

    assert len(result) == 1
    assert sorted(result[0][1], reverse=True) == ["test_project_id", "other_project_id"]
    assert result[0][0].value == "cloudfunctions.googleapis.com/function/sample_metric"
    assert result[0][0].type == "gauge"
    assert result[0][0].gcpOptions.unit == "Count"
    assert len(result[0][0].dimensions) == 1

    assert result[0][0].dimensions[0].key == "key1"
    assert result[0][0].dimensions[0].value == "label:metric.labels.key1"
