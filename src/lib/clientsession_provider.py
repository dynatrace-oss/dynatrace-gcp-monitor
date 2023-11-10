#   Copyright 2021 Dynatrace LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
import asyncio

import aiohttp

from lib.configuration import config
from lib.sfm.api_call_latency import ApiCallLatency


async def on_request_start(session, trace_config_ctx, params):
    trace_config_ctx.start = asyncio.get_event_loop().time()


async def on_request_end(session, trace_config_ctx, params):
    elapsed = asyncio.get_event_loop().time() - trace_config_ctx.start
    ApiCallLatency.update(f"{params.url.scheme}://{params.url.raw_host}/", elapsed)


trace_config = aiohttp.TraceConfig()
trace_config.on_request_start.append(on_request_start)
trace_config.on_request_end.append(on_request_end)


def init_dt_client_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(trace_configs=[trace_config], trust_env=(config.use_proxy() in ["ALL", "DT_ONLY"]))


def init_gcp_client_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(trace_configs=[trace_config], trust_env=(config.use_proxy() in ["ALL", "GCP_ONLY"]))
