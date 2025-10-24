import pytest

try:
    # Close shared aiohttp sessions after each integration test to ensure
    # strict isolation between tests (event loop + connection pools).
    from lib.clientsession_provider import close_shared_sessions
except Exception:
    close_shared_sessions = None  # type: ignore


@pytest.fixture(scope="function", autouse=True)
async def _close_sessions_after_test():
    yield
    if close_shared_sessions is not None:
        try:
            await close_shared_sessions()
        except Exception:
            # Defensive: never fail the test due to teardown cleanup
            pass

