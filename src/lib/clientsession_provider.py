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
from lib.logs.log_forwarder_variables import (
    NUMBER_OF_CONCURRENT_LOG_FORWARDING_LOOPS,
    NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES,
    NUMBER_OF_CONCURRENT_ACK_COROUTINES,
    NUMBER_OF_CONCURRENT_PUSH_COROUTINES,
)


def _calculate_pull_pool_size() -> int:
    """
    Calculate connection pool size for GCP pull operations.

    Pull coroutines run independently per worker (no global semaphore).
    Pool size must accommodate all concurrent pulls to avoid queueing.

    Returns:
        Connection pool size (no upper cap, scales with configuration)
    """
    workers = NUMBER_OF_CONCURRENT_LOG_FORWARDING_LOOPS
    pull_coroutines = NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES

    demand = workers * pull_coroutines
    pool_size = int(demand * 1.2)  # 20% headroom for bursts

    # Minimum bound only (no maximum cap)
    pool_size = max(50, pool_size)

    # Warn if configuration seems extreme (likely misconfiguration)
    if pool_size > 2000:
        print(
            f"[WARNING] GCP pull connection pool size is {pool_size}. "
            f"Configuration: workers={workers}, pull_coroutines={pull_coroutines}. "
            f"This is very high. Verify configuration is correct and ensure "
            f"system ulimit and memory are sufficient for {pool_size} connections."
        )

    return pool_size


def _calculate_ack_pool_size() -> int:
    """
    Calculate connection pool size for GCP ACK operations.

    ACK coroutines are limited by a GLOBAL semaphore (not per-worker).
    Only NUMBER_OF_CONCURRENT_ACK_COROUTINES can be in-flight at once,
    regardless of worker count.

    Pool size is independent of worker count and stays small.

    Returns:
        Connection pool size (no upper cap, scales with ack_coroutines config)
    """
    ack_coroutines = NUMBER_OF_CONCURRENT_ACK_COROUTINES  # Global semaphore

    # Generous headroom (100%) for priority path - ACKs must never queue
    pool_size = int(ack_coroutines * 2.0)

    # Minimum bound only (no maximum cap)
    pool_size = max(10, pool_size)

    # Warn if unusually high (>100 ACKs is rare)
    if pool_size > 100:
        print(
            f"[WARNING] GCP ACK connection pool size is {pool_size}. "
            f"Configuration: ack_coroutines={ack_coroutines}. "
            f"This is unusually high. Verify configuration is correct."
        )

    return pool_size


def _calculate_dt_pool_size() -> int:
    """
    Calculate connection pool size for Dynatrace push operations.

    Push coroutines are limited by a GLOBAL semaphore (not per-worker).
    Only NUMBER_OF_CONCURRENT_PUSH_COROUTINES can be in-flight at once.

    Returns:
        Connection pool size (no upper cap, scales with push_coroutines config)
    """
    push_coroutines = NUMBER_OF_CONCURRENT_PUSH_COROUTINES  # Global semaphore

    # 50% headroom
    pool_size = int(push_coroutines * 1.5)

    # Minimum bound only
    pool_size = max(20, pool_size)

    # Warn if unusually high
    if pool_size > 100:
        print(
            f"[WARNING] Dynatrace connection pool size is {pool_size}. "
            f"Configuration: push_coroutines={push_coroutines}. "
            f"This is unusually high. Verify configuration is correct."
        )

    return pool_size


# Timeouts to prevent hung requests from exceeding Pub/Sub ACK deadlines
# connect: time to establish connection (including DNS resolution)
# total: total time for the entire request
DT_CLIENT_TIMEOUT = ClientTimeout(total=60, connect=30)
GCP_CLIENT_TIMEOUT = ClientTimeout(total=120, connect=30)

# Operation-specific timeouts for GCP operations
GCP_PULL_TIMEOUT = ClientTimeout(total=120, connect=30)  # Pull operations
GCP_ACK_TIMEOUT = ClientTimeout(total=30, connect=10)    # ACK operations (fail fast)


async def on_request_start(session, trace_config_ctx, params):
    trace_config_ctx.start = asyncio.get_event_loop().time()


async def on_request_end(session, trace_config_ctx, params):
    elapsed = asyncio.get_event_loop().time() - trace_config_ctx.start
    ApiCallLatency.update(f"{params.url.scheme}://{params.url.raw_host}/", elapsed)


trace_config = aiohttp.TraceConfig()
trace_config.on_request_start.append(on_request_start)
trace_config.on_request_end.append(on_request_end)


def _make_pull_connector() -> aiohttp.TCPConnector:
    """
    Connector for GCP pull operations.
    Sized dynamically based on configured worker and pull coroutine counts.
    """
    pool_size = _calculate_pull_pool_size()
    return aiohttp.TCPConnector(
        resolver=AsyncResolver(),    # Async DNS resolver (aiodns)
        ttl_dns_cache=300,           # Cache DNS for 5 minutes
        limit=pool_size,             # Total connection limit
        limit_per_host=pool_size,    # Per-host limit (all requests → same host)
    )


def _make_ack_connector() -> aiohttp.TCPConnector:
    """
    Connector for GCP ACK operations - priority path.
    Sized based on global ACK semaphore limit (independent of worker count).
    Ensures ACKs never wait behind pulls.
    """
    pool_size = _calculate_ack_pool_size()
    return aiohttp.TCPConnector(
        resolver=AsyncResolver(),    # Async DNS resolver (aiodns)
        ttl_dns_cache=300,           # Cache DNS for 5 minutes
        limit=pool_size,             # Total connection limit
        limit_per_host=pool_size,    # Per-host limit (all requests → same host)
    )


def _make_dt_connector() -> aiohttp.TCPConnector:
    """
    Connector for Dynatrace push operations.
    Sized based on global push semaphore limit.
    """
    pool_size = _calculate_dt_pool_size()
    return aiohttp.TCPConnector(
        resolver=AsyncResolver(),    # Async DNS resolver (aiodns)
        ttl_dns_cache=300,           # Cache DNS for 5 minutes
        limit=pool_size,             # Total connection limit
        limit_per_host=pool_size,    # Per-host limit (all requests → same host)
    )


def init_gcp_pull_session() -> aiohttp.ClientSession:
    """
    Session for GCP Pub/Sub pull operations.
    Uses dedicated pull connector sized to worker × pull_coroutines.
    """
    return aiohttp.ClientSession(
        trace_configs=[trace_config],
        timeout=GCP_PULL_TIMEOUT,
        connector=_make_pull_connector(),
        trust_env=(config.use_proxy() in ["ALL", "GCP_ONLY"])
    )


def init_gcp_ack_session() -> aiohttp.ClientSession:
    """
    Session for GCP Pub/Sub ACK operations - priority path.
    Uses dedicated ACK connector sized to global semaphore limit.
    Ensures ACKs never compete with pulls for connections.
    """
    return aiohttp.ClientSession(
        trace_configs=[trace_config],
        timeout=GCP_ACK_TIMEOUT,
        connector=_make_ack_connector(),
        trust_env=(config.use_proxy() in ["ALL", "GCP_ONLY"])
    )


def init_dt_client_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        trace_configs=[trace_config],
        timeout=DT_CLIENT_TIMEOUT,
        connector=_make_dt_connector(),
        trust_env=(config.use_proxy() in ["ALL", "DT_ONLY"])
    )


def init_gcp_client_session() -> aiohttp.ClientSession:
    """
    Generic GCP session for config fetching and token operations.
    Uses pull connector configuration (backward compatibility).
    """
    return aiohttp.ClientSession(
        trace_configs=[trace_config],
        timeout=GCP_CLIENT_TIMEOUT,
        connector=_make_pull_connector(),
        trust_env=(config.use_proxy() in ["ALL", "GCP_ONLY"])
    )
