from datetime import timedelta

from lib.context import get_int_environment_value

MAX_MESSAGES_PROCESSED = 10_000
MAX_WORKERS = 100
EVENT_AGE_LIMIT_SECONDS = get_int_environment_value("DYNATRACE_LOG_INGEST_EVENT_MAX_AGE_SECONDS", int(timedelta(days=1).total_seconds()))
SENDING_WORKER_EXECUTION_PERIOD_SECONDS = get_int_environment_value("DYNATRACE_LOG_INGEST_SENDING_WORKER_EXECUTION_PERIOD", 60)