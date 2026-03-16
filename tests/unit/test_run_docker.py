import asyncio
from asyncio.exceptions import TimeoutError
from unittest import mock
from unittest.mock import AsyncMock, Mock

import run_docker


def asyncio_run_with_timeout(coro, timeout_s):
    asyncio.run(asyncio.wait_for(coro, timeout_s))


@mock.patch('run_docker.sfm_send_loop_timeouts')
@mock.patch('run_docker.async_dynatrace_gcp_extension')
@mock.patch('run_docker.metrics_pre_launch_check')
def test_query_loop_correct_interval(
        mock_metrics_pre_launch_check,
        mock_async_dynatrace_gcp_extension: AsyncMock,
        mock_sfm_send_loop_timeouts: AsyncMock,
    ):
    mock_metrics_pre_launch_check.return_value = run_docker.PreLaunchCheckResult(services=[], extension_versions={})

    run_docker.SFM_ENABLED = True
    run_docker.QUERY_INTERVAL_SEC = 3
    run_loop_for = 7
    # run 7 seconds, should start query 3 times (0s, 3s, 6s)

    try:
        asyncio_run_with_timeout(run_docker.run_metrics_fetcher_forever(), run_loop_for)
    except TimeoutError:
        pass

    assert mock_async_dynatrace_gcp_extension.call_count == 3
    mock_sfm_send_loop_timeouts.assert_called_with(True)


@mock.patch('run_docker.sfm_send_loop_timeouts')
@mock.patch('run_docker.metrics_pre_launch_check')
def test_query_loop_timeout(
        mock_metrics_pre_launch_check,
        mock_sfm_send_loop_timeouts: AsyncMock,
    ):
    mock_metrics_pre_launch_check.return_value = run_docker.PreLaunchCheckResult(services=[], extension_versions={})

    run_docker.SFM_ENABLED = True
    run_docker.QUERY_INTERVAL_SEC = 1
    run_docker.QUERY_TIMEOUT_SEC = 3
    query_length_sec = 4
    run_loop_for_sec = 5

    # should timeout after 3s; so we should get 2 executions: 0s and 3s
    # if timeout does not happen then it would be 5 executions or more

    async def async_dynatrace_gcp_extension_long_worker_mock(services):
        await asyncio.sleep(query_length_sec)

    with mock.patch('run_docker.async_dynatrace_gcp_extension', wraps=async_dynatrace_gcp_extension_long_worker_mock) as mock_async_dynatrace_gcp_extension:
        try:
            asyncio_run_with_timeout(run_docker.run_metrics_fetcher_forever(), run_loop_for_sec)
        except TimeoutError:
            pass

        assert mock_async_dynatrace_gcp_extension.call_count == 2

    mock_sfm_send_loop_timeouts.assert_called_with(False)


@mock.patch('run_docker.async_dynatrace_gcp_extension')
@mock.patch('run_docker.AutodiscoveryTaskExecutor')
@mock.patch('run_docker.AutodiscoveryContext', new=Mock())
@mock.patch('run_docker.config')
@mock.patch('run_docker.metrics_pre_launch_check')
def test_query_loop_services_dont_accumulate_with_autodiscovery(
        mock_metrics_pre_launch_check,
        mock_config,
        mock_autodiscovery_task_executor_cls,
        mock_async_dynatrace_gcp_extension: AsyncMock,
):
    base_services = [Mock(), Mock()]
    mock_metrics_pre_launch_check.return_value = run_docker.PreLaunchCheckResult(
        services=base_services, extension_versions={}
    )

    mock_config.metric_autodiscovery.return_value = True
    mock_config.keep_refreshing_extensions_config.return_value = False

    autodiscovery_service = Mock()

    mock_task_executor = Mock()
    mock_task_executor.process_autodiscovery_result = AsyncMock(
        side_effect=lambda services, extension_versions: list(services) + [autodiscovery_service]
    )
    mock_autodiscovery_task_executor_cls.create = AsyncMock(return_value=mock_task_executor)

    run_docker.SFM_ENABLED = False
    run_docker.QUERY_INTERVAL_SEC = 1
    run_docker.QUERY_TIMEOUT_SEC = 10
    run_loop_for_sec = 3.5  # expect ~3 iterations: at 0s, 1s, 2s

    try:
        asyncio_run_with_timeout(run_docker.run_metrics_fetcher_forever(), run_loop_for_sec)
    except TimeoutError:
        pass

    assert mock_async_dynatrace_gcp_extension.call_count >= 2
    for call in mock_async_dynatrace_gcp_extension.call_args_list:
        called_services = call.kwargs['services']
        # Must always be 3 (2 base + 1 autodiscovery), never growing across iterations
        assert len(called_services) == 3

