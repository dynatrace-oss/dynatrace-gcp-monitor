import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from aiohttp import ClientConnectionError, ClientResponseError, ServerDisconnectedError
from lib.context import LoggingContext
from lib.logs.log_integration_service import LogIntegrationService, _SESSION_RECREATE_QUIET_PERIOD_SECONDS


def _make_logging_context() -> LoggingContext:
    return LoggingContext("test")


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


def _make_service(gcp_client=None, dt_session=None) -> LogIntegrationService:
    """Build a LogIntegrationService bypassing async create()."""
    svc = LogIntegrationService.__new__(LogIntegrationService)
    svc.sfm_queue = asyncio.Queue()
    svc.log_push_semaphore = asyncio.Semaphore(10)
    svc.gcp_client = gcp_client or _make_gcp_client()
    svc.gcp_session = _make_session_mock()
    svc.dt_session = dt_session or _make_session_mock()
    svc._closed = False
    svc._last_gcp_session_recreated_at = 0.0
    svc.dynatrace_client = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# perform_pull — connection error detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_perform_pull_recreates_session_on_connection_error():
    """A ClientError (non-HTTP) from pull_messages triggers session recreation."""
    error = ServerDisconnectedError()
    gcp_client = _make_gcp_client(pull_side_effect=error)
    svc = _make_service(gcp_client)

    old_session = svc.gcp_session
    with patch("lib.logs.log_integration_service.init_gcp_client_session") as mock_init:
        new_session = MagicMock()
        mock_init.return_value = new_session
        await svc.perform_pull(_make_logging_context())

    assert svc.gcp_session is new_session
    assert svc.gcp_session is not old_session


@pytest.mark.asyncio
async def test_perform_pull_does_not_recreate_session_on_http_error():
    """An HTTP error (ClientResponseError) must not trigger session recreation."""
    request_info = MagicMock()
    error = ClientResponseError(request_info=request_info, history=(), status=503)
    gcp_client = _make_gcp_client(pull_side_effect=error)
    svc = _make_service(gcp_client)

    old_session = svc.gcp_session
    with patch("lib.logs.log_integration_service.init_gcp_client_session") as mock_init:
        await svc.perform_pull(_make_logging_context())
        mock_init.assert_not_called()

    assert svc.gcp_session is old_session


@pytest.mark.asyncio
async def test_perform_pull_returns_empty_on_all_connection_errors():
    """When every pull task fails with a connection error, no batches are returned."""
    error = ServerDisconnectedError()
    gcp_client = _make_gcp_client(pull_side_effect=error)
    svc = _make_service(gcp_client)

    with patch("lib.logs.log_integration_service.init_gcp_client_session"):
        batches, erroneous_ids = await svc.perform_pull(_make_logging_context())

    assert batches == []
    assert erroneous_ids == []


# ---------------------------------------------------------------------------
# _recreate_gcp_session — quiet period
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recreate_gcp_session_honours_quiet_period():
    """A second recreation within the quiet period is skipped."""
    svc = _make_service()

    with patch("lib.logs.log_integration_service.init_gcp_client_session") as mock_init:
        mock_init.return_value = MagicMock()

        await svc._recreate_gcp_session(_make_logging_context())
        first_session = svc.gcp_session

        await svc._recreate_gcp_session(_make_logging_context())

    # init_gcp_client_session called exactly once
    assert mock_init.call_count == 1
    assert svc.gcp_session is first_session


@pytest.mark.asyncio
async def test_recreate_gcp_session_allowed_after_quiet_period():
    """A recreation is allowed once the quiet period has elapsed."""
    svc = _make_service()
    svc._last_gcp_session_recreated_at = 0.0  # expired long ago

    with patch("lib.logs.log_integration_service.init_gcp_client_session") as mock_init, \
         patch("lib.logs.log_integration_service.time") as mock_time:
        mock_time.monotonic.return_value = _SESSION_RECREATE_QUIET_PERIOD_SECONDS + 1
        mock_init.return_value = MagicMock()

        await svc._recreate_gcp_session(_make_logging_context())
        await svc._recreate_gcp_session(_make_logging_context())

    # Only the first call should succeed; the second is inside the new quiet period
    assert mock_init.call_count == 1


@pytest.mark.asyncio
async def test_recreate_gcp_session_closes_old_session():
    """The old session is closed when a new one is created."""
    svc = _make_service()
    old_session = _make_session_mock()
    svc.gcp_session = old_session

    with patch("lib.logs.log_integration_service.init_gcp_client_session") as mock_init:
        mock_init.return_value = MagicMock()
        await svc._recreate_gcp_session(_make_logging_context())

    old_session.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# push_ack_ids — connection error detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_push_ack_ids_recreates_session_on_connection_error():
    """A connection-level error during ack triggers session recreation."""
    error = ServerDisconnectedError()
    gcp_client = _make_gcp_client()
    gcp_client.push_ack_ids = AsyncMock(side_effect=error)
    svc = _make_service(gcp_client)

    with patch("lib.logs.log_integration_service.init_gcp_client_session") as mock_init:
        mock_init.return_value = MagicMock()
        await svc.push_ack_ids(["ack-1"], _make_logging_context())

    mock_init.assert_called_once()


@pytest.mark.asyncio
async def test_push_ack_ids_does_not_recreate_session_on_http_error():
    """An HTTP error (ClientResponseError) during ack does not recreate the session."""
    request_info = MagicMock()
    error = ClientResponseError(request_info=request_info, history=(), status=500)
    gcp_client = _make_gcp_client()
    gcp_client.push_ack_ids = AsyncMock(side_effect=error)
    svc = _make_service(gcp_client)

    with patch("lib.logs.log_integration_service.init_gcp_client_session") as mock_init:
        await svc.push_ack_ids(["ack-1"], _make_logging_context())
        mock_init.assert_not_called()


@pytest.mark.asyncio
async def test_push_ack_ids_logs_error_type_and_message():
    """The error log includes the exception type, not just an empty string."""
    error = ServerDisconnectedError()
    gcp_client = _make_gcp_client()
    gcp_client.push_ack_ids = AsyncMock(side_effect=error)
    svc = _make_service(gcp_client)

    ctx = _make_logging_context()
    logged = []
    ctx.log = lambda msg: logged.append(msg)

    with patch("lib.logs.log_integration_service.init_gcp_client_session"):
        await svc.push_ack_ids(["ack-1"], ctx)

    assert any("ServerDisconnectedError" in m for m in logged), \
        f"Expected exception type in log, got: {logged}"
