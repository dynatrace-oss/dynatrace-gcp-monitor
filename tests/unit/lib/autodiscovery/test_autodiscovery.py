import asyncio
from unittest.mock import AsyncMock, Mock, patch
import pytest

from lib.autodiscovery.autodiscovery import AutodiscoveryContext
from lib.autodiscovery.autodiscovery_task_executor import AutodiscoveryTaskExecutor

from lib.autodiscovery.autodiscovery_utils import (
    get_metric_descriptors,
)
from lib.autodiscovery.models import AutodiscoveryResourceLinking, ServiceStub
from lib.autodiscovery.models import GCPMetricDescriptor
from lib.metrics import AutodiscoveryGCPService, GCPService

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
            "name": "projects/test_project/metricDescriptors/custom_google.googleapis.com/function/next_metric",
            "labels": [{"key": "key2", "description": "description2"}],
            "metricKind": "GAUGE",
            "valueType": "INT64",
            "displayName": "Metric 2",
            "unit": "1",
            "description": "Description Metric 2",
            "type": "custom_google.googleapis.com/function/next_metric",
            "metadata": {"launchStage": "GA", "samplePeriod": "60s", "ingestDelay": "240s"},
            "launchStage": "GA",
            "monitoredResourceTypes": ["cloud_function"],
        },
        {
            "name": "projects/test_project/metricDescriptors/cloudiot.googleapis.com/device/sample_other_metric",
            "labels": [{"key": "key3", "description": "description2"}],
            "metricKind": "GAUGE",
            "valueType": "INT64",
            "displayName": "Metric 3",
            "unit": "1",
            "description": "Description Metric 3",
            "type": "cloudiot.googleapis.com/device/active_devices",
            "metadata": {"launchStage": "GA", "samplePeriod": "60s", "ingestDelay": "240s"},
            "launchStage": "GA",
            "monitoredResourceTypes": ["cloudiot_device_registry"],
        },
    ]
}


def test_gcp_metric_descriptor_cumulative_distribution_maps_to_gauge():
    descriptor = GCPMetricDescriptor.create(
        name="projects/test_project/metricDescriptors/kubernetes.io/gcsfusecsi/fs_ops_latencies",
        labels=[{"key": "fs_op", "description": "Filesystem operation type."}],
        metricKind="CUMULATIVE",
        valueType="DISTRIBUTION",
        displayName="File system operation latencies",
        unit="us",
        description="The cumulative distribution of filesystem operation latencies.",
        type="kubernetes.io/gcsfusecsi/fs_ops_latencies",
        metadata={"launchStage": "BETA", "samplePeriod": "10s", "ingestDelay": "0s"},
        launchStage="BETA",
        monitoredResourceTypes=["k8s_pod"],
    )

    assert descriptor.type == "gauge"
    assert descriptor.key == "cloud.gcp.kubernetes_io.gcsfusecsi.fs_ops_latencies"


@pytest.mark.asyncio
@patch("lib.autodiscovery.autodiscovery_utils.fetch_resource_descriptors")
@patch("lib.autodiscovery.autodiscovery_utils.config")
@patch("lib.autodiscovery.autodiscovery_utils.get_project_ids")
async def test_get_metric_descriptors(get_project_ids_mock, config_mock, fetch_resource_mock):
    token_mock = "test_token"
    config_mock.project_id.return_value = "test_project_id"
    get_project_ids_mock.return_value = ["test_project_id", "other_project_id"]
    fetch_resource_mock.return_value = {}

    response_mock = AsyncMock()
    response_mock.json.return_value = response_json

    gcp_session_mock = AsyncMock()
    gcp_session_mock.request.return_value = response_mock

    metric_context = AsyncMock()

    ad_resources_to_services_mock = {"cloud_function": AutodiscoveryResourceLinking([], [])}

    autodiscovery_metric_block_list = ["custom_google.googleapis.com"]
    result, _ = await get_metric_descriptors(
        metric_context,
        gcp_session_mock,
        token_mock,
        ad_resources_to_services_mock,
        autodiscovery_metric_block_list,
    )
    result = list(result.items())

    assert len(result) == 1
    assert sorted(result[0][1], reverse=True) == ["test_project_id", "other_project_id"]
    assert result[0][0].value == "cloudfunctions.googleapis.com/function/sample_metric"
    assert result[0][0].type == "gauge"
    assert result[0][0].gcpOptions.unit == "Count"
    assert len(result[0][0].dimensions) == 1

    assert result[0][0].dimensions[0].key == "key1"
    assert result[0][0].dimensions[0].value == "label:metric.labels.key1"


@pytest.mark.asyncio
@patch("lib.autodiscovery.autodiscovery.AutodiscoveryContext")
async def test_create_with_mocked_autodiscovery_manager_timeout(mock_autodiscovery_context):
    async def get_autodiscovery_service(service):
        await asyncio.sleep(1)
        return service

    mock_autodiscovery_context.get_autodiscovery_service = get_autodiscovery_service
    timeout_seconds = 5

    try:
        await asyncio.wait_for(
            AutodiscoveryTaskExecutor.create(
                services=[],
                autodiscovery_manager=mock_autodiscovery_context,
                current_extension_versions={},
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        pytest.fail(
            f"AutodiscoveryTaskExecutor.create did not complete within {timeout_seconds} seconds"
        )


@pytest.mark.asyncio
@patch("lib.autodiscovery.autodiscovery.AutodiscoveryContext")
async def test_resuming_with_notify_event(mock_autodiscovery_context):
    mock_observer_function = Mock()

    get_autodiscovery_service = AsyncMock()
    mock_autodiscovery_context.get_autodiscovery_service = get_autodiscovery_service

    task_executor = await AutodiscoveryTaskExecutor.create(
        services=[],
        autodiscovery_manager=mock_autodiscovery_context,
        current_extension_versions={},
    )

    await task_executor.add_observer(mock_observer_function)

    task_executor.notify_event.set()

    await asyncio.sleep(2)

    assert get_autodiscovery_service.call_count == 2

    mock_observer_function.assert_called_once()


@pytest.mark.asyncio
@patch("lib.autodiscovery.autodiscovery.AutodiscoveryContext")
async def test_process_autodiscovery_result(mock_autodiscovery_context):
    async def get_autodiscovery_service(service):
        return Mock(spec=AutodiscoveryGCPService)

    mock_autodiscovery_context.get_autodiscovery_service = get_autodiscovery_service

    services = [Mock(spec=GCPService), Mock(spec=GCPService)]

    task_executor = await AutodiscoveryTaskExecutor.create(
        services=services,
        autodiscovery_manager=mock_autodiscovery_context,
        current_extension_versions={},
    )

    await asyncio.sleep(2)

    new_extension_versions = {"extension1": "version1", "extension2": "version2"}

    result = await task_executor.process_autodiscovery_result(services, new_extension_versions)

    assert len(result) == 3
    assert isinstance(result[2], AutodiscoveryGCPService)


@pytest.mark.asyncio
@patch("lib.autodiscovery.autodiscovery.AutodiscoveryContext")
async def test_process_autodiscovery_result_with_none(mock_autodiscovery_context):
    async def get_autodiscovery_service(service):
        return None

    mock_autodiscovery_context.get_autodiscovery_service = get_autodiscovery_service

    services = [Mock(spec=GCPService), Mock(spec=GCPService)]

    task_executor = await AutodiscoveryTaskExecutor.create(
        services=services,
        autodiscovery_manager=mock_autodiscovery_context,
        current_extension_versions={},
    )

    await asyncio.sleep(2)

    new_extension_versions = {"extension1": "version1", "extension2": "version2"}

    result = await task_executor.process_autodiscovery_result(services, new_extension_versions)

    assert len(result) == 2


@pytest.mark.asyncio
@patch("lib.autodiscovery.autodiscovery.read_autodiscovery_block_list_yaml")
@patch("lib.autodiscovery.autodiscovery.get_resources_mapping")
@patch("lib.autodiscovery.autodiscovery.read_autodiscovery_config_yaml")
@patch("lib.autodiscovery.autodiscovery.get_services_to_resources")
async def test_autodiscovery_check_resources_to_discover(
    mock_get_services_to_resources,
    mock_read_autodiscovery_config_yaml,
    mock_get_resources_mapping,
    mock_read_autodiscovery_block_list_yaml,
):
    s_stub_1 = ServiceStub("extension1", "service1", "feature_set1")
    s_stub_2 = ServiceStub("extension1", "service2", "feature_set1")
    s_stub_3 = ServiceStub("extension2", "service1", "feature_set1")

    mock_get_services_to_resources.return_value = {
        s_stub_1: ["resource1_1", "resource1_2"],
        s_stub_2: ["resource1_2"],
        s_stub_3: ["resource1_2", "resourse1_3", "resourse1_4"],
    }

    mock_get_resources_mapping.return_value = {
        "resource1_1": [s_stub_1],
        "resource1_2": [s_stub_1, s_stub_2],
        "resourse1_3": [s_stub_3],
    }

    mock_read_autodiscovery_config_yaml.return_value = {
        "autodicovery_config": {"searched_resources": ["resource_1_1", "resource_3"]}
    }

    mock_read_autodiscovery_block_list_yaml.return_value = {"block_list": []}

    autodiscovery_context = AutodiscoveryContext()

    service_1 = GCPService(
        extension_name="dynatrace.extension1",
        service="service1",
        featureSet="feature_set1",
        autodiscovery_enabled=True,
    )
    service_2 = GCPService(
        extension_name="dynatrace.extension1",
        service="service2",
        featureSet="feature_set1",
        autodiscovery_enabled=True,
    )
    service_3 = GCPService(
        extension_name="dynatrace.extension2",
        service="service1",
        featureSet="feature_set1",
        autodiscovery_enabled=False,
    )

    services_list = [service_1, service_2, service_3]
    resources = await autodiscovery_context._check_resources_to_discover(services_list)

    assert autodiscovery_context.autodiscovery_enabled is True
    assert len(resources) == 4
    assert "resource1_2" in resources
    assert len(resources["resource1_2"].possible_service_linking) == 2
