import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from lib.context import create_logs_context
from lib.logs.dynatrace_client import DynatraceClient
from lib.logs.logs_processor import LogBatch
from lib.sfm.for_logs.log_sfm_metrics import LogSelfMonitoring


def _make_full_queue() -> asyncio.Queue:
    q = asyncio.Queue(maxsize=1)
    q.put_nowait(LogSelfMonitoring())
    return q


def _make_batch(ack_id: str = "ACK_ID_1") -> LogBatch:
    payload = '[{"content": "test", "timestamp": "2024-01-01T00:00:00Z", "cloud.provider": "gcp"}]'
    return LogBatch(
        serialized_batch=payload,
        number_of_logs_in_batch=1,
        ack_ids=[ack_id],
        size_batch_bytes=len(payload),
        self_monitoring=LogSelfMonitoring(),
    )


def _make_session(status: int = 200) -> MagicMock:
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.reason = "OK"
    mock_response.text = AsyncMock(return_value="")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.request = MagicMock(return_value=mock_response)
    return session


@pytest.mark.asyncio
async def test_send_logs_does_not_block_on_full_sfm_queue():
    """Regression: send_logs must not hang when sfm_queue is at capacity.

    Before the fix, the finally block used `await sfm_queue.put()` which blocks
    indefinitely on a full queue, freezing all worker coroutines.
    """
    sfm_queue = _make_full_queue()
    context = create_logs_context(sfm_queue)
    batch = _make_batch("ACK_ID_1")
    client = DynatraceClient(url="http://fake-dt/api/v2/logs/ingest", api_key="fake-key")

    ack_ids = []
    await asyncio.wait_for(
        client.send_logs(context, _make_session(200), batch, ack_ids),
        timeout=2.0,
    )

    assert ack_ids == ["ACK_ID_1"]
    assert sfm_queue.qsize() == 1  # SFM item was dropped, queue still full but not blocking
