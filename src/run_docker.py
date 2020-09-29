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

from main import async_dynatrace_gcp_extension


async def scheduling_loop():
    while True:
        loop.create_task(async_dynatrace_gcp_extension())
        await asyncio.sleep(60)


print("Setting up")
loop = asyncio.get_event_loop()
loop.create_task(scheduling_loop())
loop.run_forever()
