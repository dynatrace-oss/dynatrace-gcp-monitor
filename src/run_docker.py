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
from typing import Optional, List

from aiohttp import web

from lib.clientsession_provider import init_dt_client_session, init_gcp_client_session
from lib.configure_dynatrace import ConfigureDynatrace
from lib.context import LoggingContext, get_int_environment_value
from lib.credentials import create_token
from lib.fast_check import FastCheck
from lib.instance_metadata import InstanceMetadata
from lib.logs.log_forwarder import run_logs
from main import async_dynatrace_gcp_extension
from operation_mode import OperationMode

OPERATION_MODE = OperationMode.from_environment_string(os.environ.get("OPERATION_MODE", None)) or OperationMode.Metrics
HEALTH_CHECK_PORT = get_int_environment_value("HEALTH_CHECK_PORT", 8080)

loop = asyncio.get_event_loop()


async def scheduling_loop(project_ids: Optional[List[str]] = None):
    while True:
        loop.create_task(async_dynatrace_gcp_extension(project_ids))
        await asyncio.sleep(60)


async def initial_check():
    async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
        token = await create_token(logging_context, gcp_session)
        if token:
            fast_check_result = await FastCheck(gcp_session=gcp_session, dt_session=dt_session, token=token, logging_context=logging_context)
            if fast_check_result.projects:
                logging_context.log(f'Monitoring enabled for the following projects: {fast_check_result}')
                instance_metadata = await InstanceMetadata(gcp_session, token, logging_context)
                if instance_metadata:
                    logging_context.log(f'GCP: {instance_metadata}')
                loop.create_task(scheduling_loop(fast_check_result.projects))
            else:
                logging_context.log("Monitoring disabled. Check your project(s) settings.")
        else:
            logging_context.log(f'Monitoring disabled. Unable to acquire authorization token.')
    await gcp_session.close()
    await dt_session.close()


async def try_configure_dynatrace():
    async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
        dashboards_result = await ConfigureDynatrace(gcp_session=gcp_session, dt_session=dt_session, logging_context=logging_context)


async def health(request):
    return web.Response(status=200)


def run_metrics():
    if "GCP_SERVICES" in os.environ:
        services = os.environ.get("GCP_SERVICES", "")
        logging_context.log(f"Running with configured services: {services}")
    loop.run_until_complete(try_configure_dynatrace())
    loop.run_until_complete(initial_check())

    run_loop_forever()


def run_loop_forever():
    try:
        loop.run_forever()
    finally:
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

logging_context.log(f"Operation mode: {OPERATION_MODE.name}")

if OPERATION_MODE == OperationMode.Metrics:
    run_metrics()

elif OPERATION_MODE == OperationMode.Logs:
    threading.Thread(target=run_loop_forever, name="AioHttpLoopWaiterThread", daemon=True).start()
    run_logs(logging_context)
