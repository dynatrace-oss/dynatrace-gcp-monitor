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
import platform
import threading
import time
from datetime import datetime
from typing import Optional, List, NamedTuple

from lib import credentials
from lib.clientsession_provider import init_dt_client_session, init_gcp_client_session
from lib.configuration import config
from lib.context import LoggingContext, SfmDashboardsContext, get_query_interval_minutes, SfmContext
from lib.credentials import create_token
from lib.dt_extensions.dt_extensions import extensions_fetch, prepare_services_config_for_next_polling
from lib.fast_check import LogsFastCheck
from lib.instance_metadata import InstanceMetadataCheck, InstanceMetadata
from lib.logs.log_forwarder import run_logs
from lib.metrics import GCPService
from lib.self_monitoring import sfm_push_metrics
from lib.sfm.dashboards import import_self_monitoring_dashboard
from lib.sfm.for_other.loop_timeout_metric import SFMMetricLoopTimeouts
from lib.webserver.webserver import run_webserver_on_asyncio_loop_forever
from main import async_dynatrace_gcp_extension
from operation_mode import OperationMode

OPERATION_MODE = OperationMode.from_environment_string(config.operation_mode()) or OperationMode.Metrics
QUERY_INTERVAL_SEC = get_query_interval_minutes() * 60
QUERY_TIMEOUT_SEC = (get_query_interval_minutes() + 2) * 60

# USED TO TEST ON WINDOWS MACHINE
if platform.system() == 'Windows':
    policy = asyncio.WindowsSelectorEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)

loop = asyncio.get_event_loop()

PreLaunchCheckResult = NamedTuple('PreLaunchCheckResult', [('services', List[GCPService])])

logging_context = LoggingContext(None)


async def metrics_pre_launch_check() -> Optional[PreLaunchCheckResult]:
    async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
        token = await create_token(logging_context, gcp_session)
        if not token:
            logging_context.log(f'Monitoring disabled. Unable to acquire authorization token.')
            return None

        extensions_fetch_result = await extensions_fetch(gcp_session, dt_session, token)
        if not extensions_fetch_result:
            return None

    return PreLaunchCheckResult(services=extensions_fetch_result.services)


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
                sfm_dashboards_context = SfmDashboardsContext(project_id_owner=config.project_id(),
                                                              token=token,
                                                              gcp_session=gcp_session,
                                                              operation_mode=OPERATION_MODE,
                                                              scheduled_execution_id=None)
                await import_self_monitoring_dashboard(context=sfm_dashboards_context)


async def sfm_send_loop_timeouts(finished_before_timeout: bool):
    async with init_gcp_client_session() as gcp_session:
        token = await create_token(logging_context, gcp_session)
        context = SfmContext(
            project_id_owner=config.project_id(),
            dynatrace_api_key=await credentials.fetch_dynatrace_api_key(gcp_session, config.project_id(), token),
            dynatrace_url=await credentials.fetch_dynatrace_url(gcp_session, config.project_id(), token),
            token=token,
            scheduled_execution_id=None,
            self_monitoring_enabled=config.self_monitoring_enabled(),
            sfm_metric_map={},
            gcp_session=gcp_session,
        )
        timeouts_metric = SFMMetricLoopTimeouts()
        timeouts_metric.update(finished_before_timeout)
        await sfm_push_metrics([timeouts_metric], context, datetime.utcnow())


async def run_metrics_fetcher_forever():
    async def run_single_polling_with_timeout(services):
        logging_context.log('MAIN_LOOP', f'Single polling started, timeout {QUERY_TIMEOUT_SEC}, polling interval {QUERY_INTERVAL_SEC}')
        polling_task = async_dynatrace_gcp_extension(services=services)

        try:
            await asyncio.wait_for(polling_task, QUERY_TIMEOUT_SEC)
            if config.self_monitoring_enabled():
                await sfm_send_loop_timeouts(True)
        except asyncio.exceptions.TimeoutError:
            logging_context.error('MAIN_LOOP', f'Single polling timed out and was stopped, timeout: {QUERY_TIMEOUT_SEC}s')
            if config.self_monitoring_enabled():
                await sfm_send_loop_timeouts(False)

    pre_launch_check_result = await metrics_pre_launch_check()
    if not pre_launch_check_result:
        logging_context.log('MAIN_LOOP', 'Pre_launch_check failed, monitoring loop will not start')
        return

    services = pre_launch_check_result.services
    new_services_from_extensions_task = None

    while True:
        start_time_s = time.time()

        if config.keep_refreshing_extensions_config():
            new_services_from_extensions_task = asyncio.create_task(prepare_services_config_for_next_polling(services))

        await run_single_polling_with_timeout(services)

        if config.keep_refreshing_extensions_config():
            logging_context.log('MAIN_LOOP', 'Refreshing services config')
            services = await new_services_from_extensions_task

        end_time_s = time.time()

        polling_duration = end_time_s - start_time_s
        logging_context.log('MAIN_LOOP', f"Polling finished after {round(polling_duration, 2)}s")

        await sleep_until_next_polling(polling_duration)


async def sleep_until_next_polling(current_polling_duration_s):
    sleep_time = QUERY_INTERVAL_SEC - current_polling_duration_s
    if sleep_time < 0: sleep_time = 0
    logging_context.log('MAIN_LOOP', f'Next polling in {round(sleep_time, 2)}s')
    await asyncio.sleep(sleep_time)


def main():
    threading.Thread(target=run_webserver_on_asyncio_loop_forever,
                     name="WebserverThread",
                     daemon=True).start()

    logging_context.log("Dynatrace GCP Monitor startup")
    logging_context.log("GCP Monitor - Dynatrace integration for Google Cloud Platform monitoring\n")
    logging_context.log(f"Release version: {config.release_tag()}")

    instance_metadata = asyncio.run(run_instance_metadata_check())
    asyncio.run(import_self_monitoring_dashboards(instance_metadata))

    logging_context.log(f"Operation mode: {OPERATION_MODE.name}")

    if OPERATION_MODE == OperationMode.Metrics:
        asyncio.run(run_metrics_fetcher_forever())
    elif OPERATION_MODE == OperationMode.Logs:
        LogsFastCheck(logging_context, instance_metadata).execute()
        run_logs(logging_context, instance_metadata)


if __name__ == '__main__':
    main()
