import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientResponseError, ServerDisconnectedError
from lib.context import LoggingContext
from lib.logs import log_forwarder
from lib.logs.log_forwarder_variables import NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES
from lib.logs.log_integration_service import LogIntegrationService

# Total timeout surfaces as a bare TimeoutError with an empty message, not as an aiohttp ClientError
CONNECTION_FAILURES = [ServerDisconnectedError(), asyncio.TimeoutError()]


def _make_logging_context(logged=None) -> LoggingContext:
    ctx = LoggingContext("test")
    if logged is not None:
        ctx.log = logged.append
    return ctx


def _make_gcp_client(pull_side_effect=None):
    client = MagicMock()
    client.api_token = "fake-token"
    client.update_gcp_client_in_the_next_loop = False
    client.refresh_lock = MagicMock(return_value=asyncio.Lock())
    client.is_token_expired = MagicMock(return_value=False)
    client.pull_messages = AsyncMock(side_effect=pull_side_effect)
    client.push_ack_ids = AsyncMock()
    return client


def _make_session_mock() -> MagicMock:
    s = MagicMock()
    s.closed = False
    s.close = AsyncMock()
    return s


def _make_service(gcp_client=None) -> LogIntegrationService:
    """Build a LogIntegrationService bypassing async create()."""
    svc = LogIntegrationService.__new__(LogIntegrationService)
    svc.sfm_queue = asyncio.Queue()
    svc.log_push_semaphore = asyncio.Semaphore(10)
    svc.gcp_client = gcp_client or _make_gcp_client()
    svc.gcp_session = _make_session_mock()
    svc.dt_session = _make_session_mock()
    svc._closed = False
    svc._last_gcp_session_recreated_at = float("-inf")
    svc.dynatrace_client = MagicMock()
    return svc


def _http_error(status: int) -> ClientResponseError:
    return ClientResponseError(request_info=MagicMock(), history=(), status=status)


@pytest.fixture
def init_session():
    with patch("lib.logs.log_integration_service.init_gcp_client_session") as mock_init:
        mock_init.side_effect = lambda: _make_session_mock()
        yield mock_init


@pytest.fixture
def clock():
    with patch("lib.logs.log_integration_service.time") as mock_time:
        mock_time.monotonic.return_value = 1000.0
        yield mock_time.monotonic


# perform_pull

@pytest.mark.asyncio
@pytest.mark.parametrize("error", CONNECTION_FAILURES, ids=lambda e: type(e).__name__)
async def test_perform_pull_all_connection_failures_recreate_session_and_raise(init_session, error):
    svc = _make_service(_make_gcp_client(pull_side_effect=error))
    old_session = svc.gcp_session

    with pytest.raises(type(error)):
        await svc.perform_pull(_make_logging_context())

    init_session.assert_called_once()
    assert svc.gcp_session is not old_session


@pytest.mark.asyncio
async def test_perform_pull_partial_connection_failure_recreates_without_raising(init_session):
    pulls = [ServerDisconnectedError()] + [{}] * (NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES - 1)
    svc = _make_service(_make_gcp_client(pull_side_effect=pulls))

    assert await svc.perform_pull(_make_logging_context()) == ([], [])
    init_session.assert_called_once()


@pytest.mark.asyncio
async def test_perform_pull_http_error_neither_recreates_nor_raises(init_session):
    """401 must not back off: the next loop refreshes the token immediately."""
    svc = _make_service(_make_gcp_client(pull_side_effect=_http_error(401)))
    old_session = svc.gcp_session

    assert await svc.perform_pull(_make_logging_context()) == ([], [])
    init_session.assert_not_called()
    assert svc.gcp_session is old_session


@pytest.mark.asyncio
async def test_perform_pull_logs_failure_type_even_when_message_is_empty(init_session):
    logged = []
    svc = _make_service(_make_gcp_client(pull_side_effect=asyncio.TimeoutError()))

    with pytest.raises(asyncio.TimeoutError):
        await svc.perform_pull(_make_logging_context(logged))

    assert any("Pub/Sub pull failed" in m and "TimeoutError" in m for m in logged), logged


@pytest.mark.asyncio
async def test_worker_backs_off_instead_of_spinning_on_fast_connection_failures(init_session):
    svc = _make_service(_make_gcp_client(pull_side_effect=ServerDisconnectedError()))

    worker = asyncio.create_task(log_forwarder.pull_and_push_logs_forever(0, 0, svc))
    await asyncio.sleep(0.3)
    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)

    assert svc.gcp_client.pull_messages.await_count == NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES


# _recreate_gcp_session

@pytest.mark.asyncio
async def test_recreate_gcp_session_is_throttled_by_quiet_period(init_session, clock):
    svc = _make_service()
    calls_after = []
    for now in (1000.0, 1059.0, 1061.0):
        clock.return_value = now
        await svc._recreate_gcp_session(_make_logging_context())
        calls_after.append(init_session.call_count)

    assert calls_after == [1, 1, 2]


@pytest.mark.asyncio
async def test_recreate_gcp_session_first_time_ignores_host_uptime(init_session, clock):
    """time.monotonic() may be below the quiet period on a freshly booted node."""
    clock.return_value = 5.0

    await _make_service()._recreate_gcp_session(_make_logging_context())

    init_session.assert_called_once()


@pytest.mark.asyncio
async def test_recreate_gcp_session_closes_old_session(init_session):
    svc = _make_service()
    old_session = svc.gcp_session

    await svc._recreate_gcp_session(_make_logging_context())

    old_session.close.assert_awaited_once()


# push_ack_ids

@pytest.mark.asyncio
@pytest.mark.parametrize("error", CONNECTION_FAILURES, ids=lambda e: type(e).__name__)
async def test_push_ack_ids_connection_failure_recreates_session(init_session, error):
    gcp_client = _make_gcp_client()
    gcp_client.push_ack_ids = AsyncMock(side_effect=error)
    svc = _make_service(gcp_client)

    await svc.push_ack_ids(["ack-1"], _make_logging_context())

    init_session.assert_called_once()


@pytest.mark.asyncio
async def test_push_ack_ids_http_error_does_not_recreate_session(init_session):
    gcp_client = _make_gcp_client()
    gcp_client.push_ack_ids = AsyncMock(side_effect=_http_error(500))
    svc = _make_service(gcp_client)

    await svc.push_ack_ids(["ack-1"], _make_logging_context())

    init_session.assert_not_called()


@pytest.mark.asyncio
async def test_push_ack_ids_logs_error_type_even_when_message_is_empty(init_session):
    logged = []
    gcp_client = _make_gcp_client()
    gcp_client.push_ack_ids = AsyncMock(side_effect=asyncio.TimeoutError())
    svc = _make_service(gcp_client)

    await svc.push_ack_ids(["ack-1"], _make_logging_context(logged))

    assert "Error acknowledging messages: TimeoutError: " in logged, logged
