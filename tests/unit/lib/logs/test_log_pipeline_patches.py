#   Copyright 2024 Dynatrace LLC
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

"""
Tests for log pipeline reliability patches.
These tests verify fixes for duplicate log issues caused by Pub/Sub redelivery.
"""

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from aiohttp import ClientTimeout


# =============================================================================
# Patch 2: HTTP Timeouts
# =============================================================================

class TestHttpTimeouts:
    """Test that HTTP client sessions have timeouts configured."""

    def test_dt_client_timeout_is_defined(self):
        """DT client timeout constant should be defined."""
        from lib.clientsession_provider import DT_CLIENT_TIMEOUT
        assert isinstance(DT_CLIENT_TIMEOUT, ClientTimeout)
        assert DT_CLIENT_TIMEOUT.total == 60
        assert DT_CLIENT_TIMEOUT.connect == 30

    def test_gcp_client_timeout_is_defined(self):
        """GCP client timeout constant should be defined."""
        from lib.clientsession_provider import GCP_CLIENT_TIMEOUT
        assert isinstance(GCP_CLIENT_TIMEOUT, ClientTimeout)
        assert GCP_CLIENT_TIMEOUT.total == 120
        assert GCP_CLIENT_TIMEOUT.connect == 30

    def test_dt_session_uses_timeout_in_code(self):
        """DT client session creation should use timeout parameter."""
        import inspect
        from lib import clientsession_provider
        source = inspect.getsource(clientsession_provider.init_dt_client_session)
        # Verify timeout is passed to ClientSession
        assert 'timeout=' in source
        assert 'DT_CLIENT_TIMEOUT' in source

    def test_gcp_session_uses_timeout_in_code(self):
        """GCP client session creation should use timeout parameter."""
        import inspect
        from lib import clientsession_provider
        source = inspect.getsource(clientsession_provider.init_gcp_client_session)
        # Verify timeout is passed to ClientSession
        assert 'timeout=' in source
        assert 'GCP_CLIENT_TIMEOUT' in source


# =============================================================================
# Patch 8: Session Reuse
# =============================================================================

class TestSessionReuse:
    """Test that LogIntegrationService reuses HTTP sessions."""

    def test_session_attributes_exist(self):
        """LogIntegrationService should have session attributes."""
        from lib.logs.log_integration_service import LogIntegrationService
        assert hasattr(LogIntegrationService, '_gcp_session')
        assert hasattr(LogIntegrationService, '_dt_session')

    def test_get_session_methods_exist(self):
        """LogIntegrationService should have session getter methods."""
        from lib.logs.log_integration_service import LogIntegrationService
        service = LogIntegrationService()
        assert hasattr(service, '_get_gcp_session')
        assert hasattr(service, '_get_dt_session')
        assert asyncio.iscoroutinefunction(service._get_gcp_session)
        assert asyncio.iscoroutinefunction(service._get_dt_session)

    def test_close_sessions_method_exists(self):
        """LogIntegrationService should have close_sessions method."""
        from lib.logs.log_integration_service import LogIntegrationService
        service = LogIntegrationService()
        assert hasattr(service, 'close_sessions')
        assert asyncio.iscoroutinefunction(service.close_sessions)

    def test_close_sessions_called_in_log_forwarder(self):
        """log_forwarder should call close_sessions in finally block."""
        import inspect
        from lib.logs import log_forwarder
        source = inspect.getsource(log_forwarder.run_logs)
        assert 'try:' in source
        assert 'finally:' in source
        assert 'close_sessions' in source


# =============================================================================
# Patch 9: Retry with Backoff
# =============================================================================

class TestRetryWithBackoff:
    """Test retry logic with exponential backoff for transient failures."""

    def test_retryable_status_codes_defined(self):
        """RETRYABLE_STATUS_CODES should include common transient errors."""
        from lib.logs.dynatrace_client import RETRYABLE_STATUS_CODES
        assert 429 in RETRYABLE_STATUS_CODES  # Too Many Requests
        assert 500 in RETRYABLE_STATUS_CODES  # Internal Server Error
        assert 502 in RETRYABLE_STATUS_CODES  # Bad Gateway
        assert 503 in RETRYABLE_STATUS_CODES  # Service Unavailable
        assert 504 in RETRYABLE_STATUS_CODES  # Gateway Timeout

    def test_max_retries_defined(self):
        """MAX_RETRIES should be defined and reasonable."""
        from lib.logs.dynatrace_client import MAX_RETRIES
        assert MAX_RETRIES >= 2
        assert MAX_RETRIES <= 5

    def test_initial_backoff_defined(self):
        """INITIAL_BACKOFF_SECONDS should be defined."""
        from lib.logs.dynatrace_client import INITIAL_BACKOFF_SECONDS
        assert INITIAL_BACKOFF_SECONDS >= 1


# =============================================================================
# Patch 10: Include Pub/Sub messageId
# =============================================================================

class TestMessageIdInclusion:
    """Test that Pub/Sub messageId is included in forwarded logs."""

    def test_process_message_accepts_message_id_parameter(self):
        """_process_message should accept message_id parameter."""
        from lib.logs.logs_processor import _process_message
        import inspect
        sig = inspect.signature(_process_message)
        params = list(sig.parameters.keys())
        assert 'message_id' in params

    def test_message_id_included_in_payload(self):
        """messageId should be included in the log payload."""
        from lib.logs.logs_processor import _process_message
        from lib.context import LogsProcessingContext
        from queue import Queue
        from datetime import datetime, timezone

        # Use current timestamp to avoid "too old" rejection
        now = datetime.now(timezone.utc).isoformat()

        sfm_queue = Queue()
        context = LogsProcessingContext(
            scheduled_execution_id="test123",
            message_publish_time=now,
            sfm_queue=sfm_queue
        )

        # Create a test message with valid log data and current timestamp
        log_data = {
            "insertId": "test-insert-id",
            "timestamp": now,
            "textPayload": "Test log message"
        }
        message = {
            "data": base64.b64encode(json.dumps(log_data).encode()).decode()
        }

        # Process with messageId
        result = _process_message(
            context=context,
            message=message,
            ack_id="test-ack-id",
            message_id="12345678901234567"
        )

        assert result is not None
        payload = json.loads(result.payload)
        assert "gcp.pubsub.message_id" in payload
        assert payload["gcp.pubsub.message_id"] == "12345678901234567"

    def test_message_id_optional_for_backward_compatibility(self):
        """messageId parameter should be optional."""
        from lib.logs.logs_processor import _process_message
        from lib.context import LogsProcessingContext
        from queue import Queue
        from datetime import datetime, timezone

        # Use current timestamp to avoid "too old" rejection
        now = datetime.now(timezone.utc).isoformat()

        sfm_queue = Queue()
        context = LogsProcessingContext(
            scheduled_execution_id="test123",
            message_publish_time=now,
            sfm_queue=sfm_queue
        )

        log_data = {
            "insertId": "test-insert-id",
            "timestamp": now,
            "textPayload": "Test log message"
        }
        message = {
            "data": base64.b64encode(json.dumps(log_data).encode()).decode()
        }

        # Process without messageId - should not raise
        result = _process_message(
            context=context,
            message=message,
            ack_id="test-ack-id"
            # message_id not provided
        )

        assert result is not None
        payload = json.loads(result.payload)
        # Should not have messageId field when not provided
        assert "gcp.pubsub.message_id" not in payload


# =============================================================================
# Integration-style tests for error logging (Patches 3, 4, 7)
# =============================================================================

class TestErrorLogging:
    """Test that errors are properly logged instead of silently swallowed."""

    def test_log_integration_service_logs_errors_attribute(self):
        """Verify logging_context.error is called for failures."""
        # This is a structural test - the actual logging tests require
        # more complex mocking of the async gather behavior
        from lib.logs.log_integration_service import LogIntegrationService
        import inspect

        # Check that push_ack_ids has error logging
        source = inspect.getsource(LogIntegrationService.push_ack_ids)
        assert 'logging_context.error' in source
        assert 'ACK chunk' in source

        # Check that push_logs has error logging
        source = inspect.getsource(LogIntegrationService.push_logs)
        assert 'logging_context.error' in source
        assert 'send to Dynatrace failed' in source

        # Check that perform_pull has error logging
        source = inspect.getsource(LogIntegrationService.perform_pull)
        assert 'logging_context.error' in source
        assert 'Pull request' in source
