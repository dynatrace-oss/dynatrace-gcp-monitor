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
from aiohttp import ClientTimeout
from aiohttp.resolver import AsyncResolver

from lib.configuration import config
from lib.sfm.api_call_latency import ApiCallLatency

# Timeouts to prevent hung requests from exceeding Pub/Sub ACK deadlines
# connect: time to establish connection (including DNS resolution)
# total: total time for the entire request
DT_CLIENT_TIMEOUT = ClientTimeout(total=60, connect=30)
GCP_CLIENT_TIMEOUT = ClientTimeout(total=120, connect=30)


async def on_request_start(session, trace_config_ctx, params):
    trace_config_ctx.start = asyncio.get_event_loop().time()


async def on_request_end(session, trace_config_ctx, params):
    elapsed = asyncio.get_event_loop().time() - trace_config_ctx.start
    ApiCallLatency.update(f"{params.url.scheme}://{params.url.raw_host}/", elapsed)


trace_config = aiohttp.TraceConfig()
trace_config.on_request_start.append(on_request_start)
trace_config.on_request_end.append(on_request_end)


def _make_connector() -> aiohttp.TCPConnector:
    """Create a TCP connector with async DNS resolver and caching."""
    return aiohttp.TCPConnector(
        resolver=AsyncResolver(),  # Use async DNS resolver (aiodns)
        ttl_dns_cache=300,         # Cache DNS for 5 minutes
        limit=100,                 # Max 100 total connections
        limit_per_host=30,         # Max 30 connections per host
    )


def init_dt_client_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        trace_configs=[trace_config],
        timeout=DT_CLIENT_TIMEOUT,
        connector=_make_connector(),
        trust_env=(config.use_proxy() in ["ALL", "DT_ONLY"])
    )


def init_gcp_client_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        trace_configs=[trace_config],
        timeout=GCP_CLIENT_TIMEOUT,
        connector=_make_connector(),
        trust_env=(config.use_proxy() in ["ALL", "GCP_ONLY"])
    )
