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
from lib.configuration.config import get_int_environment_value
from lib.sfm.api_call_latency import ApiCallLatency


async def on_request_start(session, trace_config_ctx, params):
    trace_config_ctx.start = asyncio.get_event_loop().time()


async def on_request_end(session, trace_config_ctx, params):
    elapsed = asyncio.get_event_loop().time() - trace_config_ctx.start
    ApiCallLatency.update(f"{params.url.scheme}://{params.url.raw_host}/", elapsed)


trace_config = aiohttp.TraceConfig()
trace_config.on_request_start.append(on_request_start)
trace_config.on_request_end.append(on_request_end)


_REQUEST_TIMEOUT_TOTAL = get_int_environment_value("REQUEST_TIMEOUT_TOTAL", 120)
_REQUEST_TIMEOUT_SOCK_CONNECT = get_int_environment_value("REQUEST_TIMEOUT_SOCK_CONNECT", 30)
_REQUEST_TIMEOUT_SOCK_READ = get_int_environment_value("REQUEST_TIMEOUT_SOCK_READ", 60)
_GCP_CONNECTOR_LIMIT = get_int_environment_value("GCP_CONNECTOR_LIMIT", 500)

_default_timeout = aiohttp.ClientTimeout(
    total=_REQUEST_TIMEOUT_TOTAL,
    connect=None,
    sock_connect=_REQUEST_TIMEOUT_SOCK_CONNECT,
    sock_read=_REQUEST_TIMEOUT_SOCK_READ,
)


def init_dt_client_session() -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(enable_cleanup_closed=True)
    return aiohttp.ClientSession(
        connector=connector,
        timeout=_default_timeout,
        trace_configs=[trace_config],
        trust_env=(config.use_proxy() in ["ALL", "DT_ONLY"]),
    )


def init_gcp_client_session() -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(enable_cleanup_closed=True, limit=_GCP_CONNECTOR_LIMIT)
    return aiohttp.ClientSession(
        connector=connector,
        timeout=_default_timeout,
        trace_configs=[trace_config],
        trust_env=(config.use_proxy() in ["ALL", "GCP_ONLY"]),
    )
