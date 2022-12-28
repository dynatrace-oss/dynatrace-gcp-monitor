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
import asyncio
import os
import threading
import time
from typing import Optional, List, NamedTuple

from aiohttp import ClientSession

from lib.clientsession_provider import init_dt_client_session, init_gcp_client_session
from lib.context import LoggingContext, SfmDashboardsContext, get_query_interval_minutes
from lib.credentials import create_token, get_project_id_from_environment, fetch_dynatrace_url, fetch_dynatrace_api_key

from lib.extensions_fetcher import ExtensionsFetchResult, ExtensionsFetcher
from lib.fast_check import MetricsFastCheck, FastCheckResult, LogsFastCheck
from lib.instance_metadata import InstanceMetadataCheck, InstanceMetadata
from lib.logs.log_forwarder import run_logs
from lib.metrics import GCPService
from lib.sfm.dashboards import import_self_monitoring_dashboard
from lib.utilities import print_dynatrace_logo
from lib.webserver.webserver import run_webserver_on_asyncio_loop_forever
from main import async_dynatrace_gcp_extension
from operation_mode import OperationMode

OPERATION_MODE = OperationMode.from_environment_string(os.environ.get("OPERATION_MODE", None)) or OperationMode.Metrics
QUERY_INTERVAL_SEC = get_query_interval_minutes() * 60
QUERY_TIMEOUT_SEC = (get_query_interval_minutes() + 2) * 60

# USED TO TEST ON WINDOWS MACHINE
# policy = asyncio.WindowsSelectorEventLoopPolicy()
# asyncio.set_event_loop_policy(policy)

loop = asyncio.get_event_loop()

PreLaunchCheckResult = NamedTuple('PreLaunchCheckResult', [('projects', List[str]), ('services', List[GCPService])])

logging_context = LoggingContext(None)


async def metrics_pre_launch_check() -> Optional[PreLaunchCheckResult]:
    async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
        token = await create_token(logging_context, gcp_session)
        if not token:
            logging_context.log(f'Monitoring disabled. Unable to acquire authorization token.')
            return None

        fast_check_result = await metrics_initial_check(gcp_session, dt_session, token)
        if not fast_check_result:
            return None

        extensions_fetch_result = await extensions_fetch(gcp_session, dt_session, token)
        if not extensions_fetch_result:
            return None

    return PreLaunchCheckResult(projects=fast_check_result.projects, services=extensions_fetch_result.services)


async def metrics_initial_check(gcp_session: ClientSession, dt_session: ClientSession, token: str) -> Optional[FastCheckResult]:
    fast_check_result = await MetricsFastCheck(
        gcp_session=gcp_session,
        dt_session=dt_session,
        token=token,
        logging_context=logging_context
    ).execute()
    if fast_check_result.projects:
        logging_context.log(f'Monitoring enabled for the following projects: {fast_check_result.projects}')
        return fast_check_result
    else:
        logging_context.log("Monitoring disabled. Check your project(s) settings.")
        return None


async def extensions_fetch(gcp_session: ClientSession, dt_session: ClientSession, token: str) -> Optional[ExtensionsFetchResult]:
    extension_fetcher_result = await ExtensionsFetcher(
        dt_session=dt_session,
        dynatrace_url=await fetch_dynatrace_url(gcp_session, get_project_id_from_environment(), token),
        dynatrace_access_key=await fetch_dynatrace_api_key(gcp_session, get_project_id_from_environment(), token),
        logging_context=logging_context
    ).execute()

    if extension_fetcher_result.services:
        feature_sets_names = [f"{service.name}/{service.feature_set}" for service in extension_fetcher_result.services]
        logging_context.log(f'Monitoring enabled for the following fetched extensions feature sets: {feature_sets_names}')
        return extension_fetcher_result
    else:
        logging_context.log("Monitoring disabled. Check configured extensions.")
        return None


async def run_instance_metadata_check() -> Optional[InstanceMetadata]:
    async with init_gcp_client_session() as gcp_session:
        token = await create_token(logging_context, gcp_session)
        if token:
            return await InstanceMetadataCheck(gcp_session, token, logging_context).execute()
        else:
            logging_context.log(f'Instance metadata check skipped. Unable to acquire authorization token.')

    return None


async def import_self_monitoring_dashboards(metadata: InstanceMetadata):
    if metadata:
        async with init_gcp_client_session() as gcp_session:
            token = await create_token(logging_context, gcp_session)
            if token:
                sfm_dashboards_context = SfmDashboardsContext(project_id_owner=get_project_id_from_environment(),
                                                              token=token,
                                                              gcp_session=gcp_session,
                                                              operation_mode=OPERATION_MODE,
                                                              scheduled_execution_id=None)
                await import_self_monitoring_dashboard(context=sfm_dashboards_context)


async def run_metrics_fetcher_forever():
    async def run_single_polling_with_timeout(pre_launch_check_result):
        logging_context.log(f'Single polling started, timeout {QUERY_TIMEOUT_SEC}, polling interval {QUERY_INTERVAL_SEC}')

        polling_task = async_dynatrace_gcp_extension(services=pre_launch_check_result.services)

        try:
            await asyncio.wait_for(polling_task, QUERY_TIMEOUT_SEC)
        except asyncio.exceptions.TimeoutError:
            logging_context.error(f'Single polling timed out and was stopped, timeout: {QUERY_TIMEOUT_SEC}s')

    async def sleep_until_next_polling(current_polling_duration_s):
        sleep_time = QUERY_INTERVAL_SEC - current_polling_duration_s
        if sleep_time < 0: sleep_time = 0
        logging_context.log(f'Next polling in {sleep_time}s')
        await asyncio.sleep(sleep_time)

    pre_launch_check_result = await metrics_pre_launch_check()
    if not pre_launch_check_result:
        logging_context.log('Pre_launch_check failed, monitoring loop will not start')
        return

    while True:
        start_time_s = time.time()
        await run_single_polling_with_timeout(pre_launch_check_result)
        end_time_s = time.time()

        polling_duration = end_time_s - start_time_s
        logging_context.log(f"Polling finished after {polling_duration}s")

        await sleep_until_next_polling(polling_duration)


def main():
    threading.Thread(target=run_webserver_on_asyncio_loop_forever,
                     args=(loop,),
                     name="AioHttpLoopWaiterThread",
                     daemon=True).start()

    print_dynatrace_logo()

    logging_context.log("GCP Monitor - Dynatrace integration for Google Cloud Platform monitoring\n")

    instance_metadata = asyncio.run(run_instance_metadata_check())
    asyncio.run(import_self_monitoring_dashboards(instance_metadata))

    logging_context.log(f"Operation mode: {OPERATION_MODE.name}")

    if OPERATION_MODE == OperationMode.Metrics:
        asyncio.run(run_metrics_fetcher_forever())
    elif OPERATION_MODE == OperationMode.Logs:
        LogsFastCheck(logging_context, instance_metadata).execute()
        run_logs(logging_context, instance_metadata, loop)


if __name__ == '__main__':
    main()
