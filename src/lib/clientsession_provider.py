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
from typing import Optional

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


# Reuse sessions across the whole process to avoid repeatedly creating
# connectors, DNS lookups and socket pools on every request.
# Cached sessions bound to the event loop they were created on.
_gcp_session: Optional[aiohttp.ClientSession] = None
_dt_session: Optional[aiohttp.ClientSession] = None
_gcp_session_loop: Optional[asyncio.AbstractEventLoop] = None
_dt_session_loop: Optional[asyncio.AbstractEventLoop] = None


def _make_connector() -> aiohttp.TCPConnector:
    # ttl_dns_cache reduces expensive getaddrinfo calls; keep-alive reduces
    # connection churn. Defaults keep SSL verification behavior to the caller.
    # NOTE: We keep limits default (100) and rely on existing semaphores in code
    # to limit concurrency.
    return aiohttp.TCPConnector(ttl_dns_cache=300)


class _SharedSessionContext:
    """Async context wrapper that returns a shared session and does not close it.

    Using this preserves the existing `async with init_*_client_session()` API
    while ensuring the underlying session is long-lived and reused.
    """

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session

    async def __aenter__(self) -> aiohttp.ClientSession:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        # Do not close the shared session on scope exit
        return False


def _ensure_gcp_session() -> aiohttp.ClientSession:
    global _gcp_session, _gcp_session_loop
    current_loop = asyncio.get_event_loop()
    # Recreate session if none, closed, or bound to a different loop
    if (
        _gcp_session is None
        or _gcp_session.closed
        or _gcp_session_loop is None
        or _gcp_session_loop is not current_loop
    ):
        # Attempt to gracefully close the previous session if it exists and
        # we are switching event loops. Do this best‑effort to avoid noisy
        # "Unclosed client session/connector" warnings.
        old_session = _gcp_session
        old_loop = _gcp_session_loop
        _gcp_session = aiohttp.ClientSession(
            trace_configs=[trace_config],
            trust_env=(config.use_proxy() in ["ALL", "GCP_ONLY"]),
            connector=_make_connector(),
        )
        _gcp_session_loop = current_loop
        if old_session is not None and not getattr(old_session, "closed", True):
            try:
                if old_loop is not None and old_loop.is_running():
                    # Close on the loop that created the session to satisfy aiohttp
                    asyncio.run_coroutine_threadsafe(old_session.close(), old_loop)
                else:
                    # Fall back to closing in the current loop
                    current_loop.create_task(old_session.close())
            except Exception:
                # Best effort: ignore cleanup errors
                pass
    return _gcp_session


def _ensure_dt_session() -> aiohttp.ClientSession:
    global _dt_session, _dt_session_loop
    current_loop = asyncio.get_event_loop()
    if (
        _dt_session is None
        or _dt_session.closed
        or _dt_session_loop is None
        or _dt_session_loop is not current_loop
    ):
        old_session = _dt_session
        old_loop = _dt_session_loop
        _dt_session = aiohttp.ClientSession(
            trace_configs=[trace_config],
            trust_env=(config.use_proxy() in ["ALL", "DT_ONLY"]),
            connector=_make_connector(),
        )
        _dt_session_loop = current_loop
        if old_session is not None and not getattr(old_session, "closed", True):
            try:
                if old_loop is not None and old_loop.is_running():
                    asyncio.run_coroutine_threadsafe(old_session.close(), old_loop)
                else:
                    current_loop.create_task(old_session.close())
            except Exception:
                pass
    return _dt_session


def init_dt_client_session() -> _SharedSessionContext:
    return _SharedSessionContext(_ensure_dt_session())


def init_gcp_client_session() -> _SharedSessionContext:
    return _SharedSessionContext(_ensure_gcp_session())


async def close_shared_sessions():
    """Optional cleanup helper if the process performs a graceful shutdown."""
    global _gcp_session, _dt_session, _gcp_session_loop, _dt_session_loop
    if _gcp_session and not _gcp_session.closed:
        await _gcp_session.close()
    if _dt_session and not _dt_session.closed:
        await _dt_session.close()
    _gcp_session = None
    _dt_session = None
    _gcp_session_loop = None
    _dt_session_loop = None
