import time
import pytest

from lib.logs.gcp_client import GCPClient
from lib.context import LoggingContext


class DummyContext(LoggingContext):
    def __init__(self):
        super().__init__("test")
        self.captured = []

    def log(self, *args):
        self.captured.append(" ".join(str(a) for a in args))


class OkResp:
    status = 200
    reason = "OK"

    async def json(self):
        return {"receivedMessages": []}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False
    def raise_for_status(self):
        return None


class UnauthorizedResp(OkResp):
    status = 401


class DummySession:
    def __init__(self, resp):
        self._resp = resp

    def request(self, *a, **kw):
        return self._resp


@pytest.mark.asyncio
async def test_update_token_changes_headers_and_resets_flag():
    ctx = DummyContext()
    client = GCPClient({"access_token": "tokA", "expires_at": time.time() + 60}, context=ctx)

    old_headers = client.headers.copy()
    client.update_gcp_client_in_the_next_loop = True
    client.update_token({"access_token": "tokB", "expires_at": time.time() + 120})

    assert client.headers != old_headers
    assert client.update_gcp_client_in_the_next_loop is False


@pytest.mark.asyncio
async def test_update_token_rollback_on_invalid_input():
    ctx = DummyContext()
    client = GCPClient({"access_token": "tokA", "expires_at": time.time() + 60}, context=ctx)
    old_state = (client.api_token, client.token_expires_at, client.headers.copy())

    with pytest.raises(ValueError):
        client.update_token({})

    assert (client.api_token, client.token_expires_at, client.headers) == old_state
    assert client.update_gcp_client_in_the_next_loop is True


@pytest.mark.asyncio
async def test_pull_messages_sets_update_flag_on_expiry_and_401():
    ctx = DummyContext()
    # Expired token
    client = GCPClient({"access_token": "tokA", "expires_at": time.time() - 10}, context=ctx)

    # First call marks update due to expiry
    ok_session = DummySession(OkResp())
    await client.pull_messages(ctx, ok_session)
    assert client.update_gcp_client_in_the_next_loop is True

    # 401 also triggers update flag
    client.update_gcp_client_in_the_next_loop = False
    unauthorized_session = DummySession(UnauthorizedResp())
    await client.pull_messages(ctx, unauthorized_session)
    assert client.update_gcp_client_in_the_next_loop is True


@pytest.mark.asyncio
async def test_push_ack_ids_triggers_update_on_expired_and_401():
    ctx = DummyContext()
    client = GCPClient({"access_token": "tokA", "expires_at": time.time() - 1}, context=ctx)
    called = {"count": 0}

    async def updater(gcp_session, logging_context):
        called["count"] += 1

    # Expired token causes a call to updater before request
    ok_session = DummySession(OkResp())
    await client.push_ack_ids(["id1"], ok_session, ctx, updater)
    assert called["count"] == 1

    # 401 response causes another call to updater
    unauthorized_session = DummySession(UnauthorizedResp())
    # Ensure not expired now, so only 401 triggers update
    client.token_expires_at = time.time() + 120
    await client.push_ack_ids(["id1"], unauthorized_session, ctx, updater)
    assert called["count"] == 2
