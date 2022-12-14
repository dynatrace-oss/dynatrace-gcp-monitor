import asyncio
from asyncio.exceptions import TimeoutError
from unittest import mock
from unittest.mock import AsyncMock

import run_docker


def asyncio_run_with_timeout(coro, timeout_s):
    async def task_wrapper():
        task = asyncio.create_task(coro)
        await asyncio.wait_for(task, timeout_s)

    asyncio.run(task_wrapper())


@mock.patch('run_docker.async_dynatrace_gcp_extension')
@mock.patch('run_docker.metrics_pre_launch_check')
def test_query_loop_correct_interval(mock_metrics_pre_launch_check, mock_async_dynatrace_gcp_extension: AsyncMock):
    mock_metrics_pre_launch_check.return_value = run_docker.PreLaunchCheckResult(projects=[], services=[])

    run_docker.QUERY_INTERVAL_SEC = 3
    run_loop_for = 7
    # run 7 seconds, should start query 3 times (0s, 3s, 6s)

    try:
        asyncio_run_with_timeout(run_docker.run_metrics_fetcher_forever(), run_loop_for)
    except TimeoutError:
        pass

    assert mock_async_dynatrace_gcp_extension.call_count == 3


@mock.patch('run_docker.metrics_pre_launch_check')
def test_query_loop_timeout(mock_metrics_pre_launch_check):
    mock_metrics_pre_launch_check.return_value = run_docker.PreLaunchCheckResult(projects=[], services=[])

    run_docker.QUERY_INTERVAL_SEC = 1
    run_docker.QUERY_TIMEOUT_SEC = 3
    run_loop_for = 5

    # should timeout after 3s; so we should get executions: 0s and 3s

    async def async_dynatrace_gcp_extension_long_worker_mock(project_ids, services):
        await asyncio.sleep(run_docker.QUERY_TIMEOUT_SEC + 1)

    with mock.patch('run_docker.async_dynatrace_gcp_extension', wraps=async_dynatrace_gcp_extension_long_worker_mock) as mock_async_dynatrace_gcp_extension:
            try:
                asyncio_run_with_timeout(run_docker.run_metrics_fetcher_forever(), run_loop_for)
            except TimeoutError:
                pass

            assert mock_async_dynatrace_gcp_extension.call_count == 2

