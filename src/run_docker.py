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
from typing import Optional, List, NamedTuple

from aiohttp import web, ClientSession

from lib.clientsession_provider import init_dt_client_session, init_gcp_client_session
from lib.context import LoggingContext, get_int_environment_value, SfmDashboardsContext, get_query_interval_minutes
from lib.credentials import create_token, get_project_id_from_environment, fetch_dynatrace_url, fetch_dynatrace_api_key

from lib.extensions_fetcher import ExtensionsFetchResult, ExtensionsFetcher
from lib.fast_check import MetricsFastCheck, FastCheckResult, LogsFastCheck
from lib.instance_metadata import InstanceMetadataCheck, InstanceMetadata
from lib.logs.log_forwarder import run_logs
from lib.self_monitoring import import_self_monitoring_dashboard
from main import async_dynatrace_gcp_extension
from operation_mode import OperationMode

OPERATION_MODE = OperationMode.from_environment_string(os.environ.get("OPERATION_MODE", None)) or OperationMode.Metrics
HEALTH_CHECK_PORT = get_int_environment_value("HEALTH_CHECK_PORT", 8080)
QUERY_INTERVAL_MIN = get_query_interval_minutes()

# USED TO TEST ON WINDOWS MACHINE
# policy = asyncio.WindowsSelectorEventLoopPolicy()
# asyncio.set_event_loop_policy(policy)

loop = asyncio.get_event_loop()

PreLaunchCheckResult = NamedTuple('PreLaunchCheckResult', [('projects', List[str]), ('services', List[str])])


async def scheduling_loop(pre_launch_check_result: PreLaunchCheckResult):
    while True:
        loop.create_task(async_dynatrace_gcp_extension(project_ids=pre_launch_check_result.projects,
                                                       services=pre_launch_check_result.services))
        await asyncio.sleep(60 * QUERY_INTERVAL_MIN)


async def metrics_pre_launch_check() -> Optional[PreLaunchCheckResult]:
    async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
        token = await create_token(logging_context, gcp_session)
        if not token:
            logging_context.log(f'Monitoring disabled. Unable to acquire authorization token.')
        fast_check_result = await metrics_initial_check(gcp_session, dt_session, token) if token else None
        extensions_fetch_result = await extensions_fetch(gcp_session, dt_session, token) if fast_check_result else None
    return PreLaunchCheckResult(projects=fast_check_result.projects,
                                services=extensions_fetch_result.services) if fast_check_result and extensions_fetch_result else None


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


async def health(request):
    return web.Response(status=200)


def run_metrics():
    pre_launch_check_result = loop.run_until_complete(metrics_pre_launch_check())
    if pre_launch_check_result:
        loop.create_task(scheduling_loop(pre_launch_check_result))
        run_loop_forever()


def run_loop_forever():
    try:
        loop.run_forever()
    finally:
        print("Closing AsyncIO loop...")
        loop.run_until_complete(app.shutdown())
        loop.run_until_complete(runner.cleanup())
        loop.run_until_complete(app.cleanup())
        loop.close()


print("                      ,,,,,..")
print("                  ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,.")
print("               ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,")
print("            .,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,     ,,")
print("          ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,    .,,,,")
print("       ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,     ,,,,,,,.")
print("    .,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,.    ,,,,,,,,,,,")
print("  ,,,,,,,,,,,,,,,,,......  ......,,,,,,,    .,,,,,,,,,,,,,")
print(",,                                        ,,,,,,,,,,,,,,,,")
print(",,,,,,,,,,,,,,,,,                        .,,,,,,,,,,,,,,,,")
print(",,,,,,,,,,,,,,,,,                        .,,,,,,,,,,,,,,,,.")
print(",,,,,,,,,,,,,,,,,       Dynatrace        .,,,,,,,,,,,,,,,,.")
print(",,,,,,,,,,,,,,,,, dynatrace-gcp-function .,,,,,,,,,,,,,,,,,")
print(",,,,,,,,,,,,,,,,,                        .,,,,,,,,,,,,,,,,,")
print(",,,,,,,,,,,,,,,,,                        ,,,,,,,,,,,,,,,,,,")
print(",,,,,,,,,,,,,,,,,                        ,,,,,,,,,,,,,,,,,,")
print(".,,,,,,,,,,,,,,,                         ,,,,,,,,,,,,,,,,,")
print(".,,,,,,,,,,,,,    .,,,,,,,,,,,,,,,,,,.   ,,,,,,,,,,,,,,,")
print(" ,,,,,,,,,,     ,,,,,,,,,,,,,,,,,,,,,,  .,,,,,,,,,,,,.")
print(" ,,,,,,,     ,,,,,,,,,,,,,,,,,,,,,,,,,  ,,,,,,,,,,,")
print(" ,,,,,    .,,,,,,,,,,,,,,,,,,,,,,,,,,.  ,,,,,,,,")
print("  ,     ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,  ,,,,,,,")
print("     ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,  ,,,,")
print("")

logging_context = LoggingContext(None)

logging_context.log("Dynatrace function for Google Cloud Platform monitoring\n")

logging_context.log("Setting up... \n")
app = web.Application()
app.add_routes([web.get('/health', health)])

# setup webapp
runner = web.AppRunner(app)
loop.run_until_complete(runner.setup())
site = web.TCPSite(runner, '0.0.0.0', HEALTH_CHECK_PORT)
loop.run_until_complete(site.start())

instance_metadata = loop.run_until_complete(run_instance_metadata_check())
loop.run_until_complete(import_self_monitoring_dashboards(instance_metadata))

logging_context.log(f"Operation mode: {OPERATION_MODE.name}")

if OPERATION_MODE == OperationMode.Metrics:
    run_metrics()

elif OPERATION_MODE == OperationMode.Logs:
    threading.Thread(target=run_loop_forever, name="AioHttpLoopWaiterThread", daemon=True).start()
    LogsFastCheck(logging_context, instance_metadata).execute()
    run_logs(logging_context, instance_metadata, loop)
