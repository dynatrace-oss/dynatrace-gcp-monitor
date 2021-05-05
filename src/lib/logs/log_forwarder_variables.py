import os
from datetime import timedelta

from lib.context import get_int_environment_value

MAX_MESSAGES_PROCESSED = 10_000
MAX_WORKERS = 100
LOGS_SUBSCRIPTION_PROJECT = os.environ.get("LOGS_SUBSCRIPTION_PROJECT", None)
LOGS_SUBSCRIPTION_ID = os.environ.get('LOGS_SUBSCRIPTION_ID', None)
CONTENT_LENGTH_LIMIT = get_int_environment_value("DYNATRACE_LOG_INGEST_CONTENT_MAX_LENGTH", 8192)
EVENT_AGE_LIMIT_SECONDS = get_int_environment_value("DYNATRACE_LOG_INGEST_EVENT_MAX_AGE_SECONDS", int(timedelta(days=1).total_seconds()))
SENDING_WORKER_EXECUTION_PERIOD_SECONDS = get_int_environment_value("DYNATRACE_LOG_INGEST_SENDING_WORKER_EXECUTION_PERIOD", 60)
REQUEST_BODY_MAX_SIZE = get_int_environment_value("DYNATRACE_LOG_INGEST_REQUEST_MAX_SIZE", 1048576)
BATCH_MAX_MESSAGES = get_int_environment_value("DYNATRACE_LOG_INGEST_BATCH_MAX_MESSAGES", 10_000)