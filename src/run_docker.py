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

from aiohttp import web

from lib.context import LoggingContext
from main import async_dynatrace_gcp_extension


async def scheduling_loop():
    while True:
        loop.create_task(async_dynatrace_gcp_extension())
        await asyncio.sleep(60)


async def health(request):
    return web.Response(status=200)


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

if "GCP_SERVICES" in os.environ:
    services = os.environ.get("GCP_SERVICES", "")
    print(f"Running with configured services: {services}")

logging_context.log("Setting up... \n")
loop = asyncio.get_event_loop()
app = web.Application()
app.add_routes([web.get('/health', health)])

runner = web.AppRunner(app)
loop.run_until_complete(runner.setup())
site = web.TCPSite(runner, '0.0.0.0', 8080)

loop.run_until_complete(site.start())
loop.create_task(scheduling_loop())

try:
    loop.run_forever()
finally:
    loop.run_until_complete(app.shutdown())
    loop.run_until_complete(runner.cleanup())
    loop.run_until_complete(app.cleanup())
    loop.close()
