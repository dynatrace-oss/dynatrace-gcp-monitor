#     Copyright 2024 Dynatrace LLC
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

import os
from datetime import timedelta

from lib.configuration.config import get_int_environment_value

PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES = get_int_environment_value("PROCESSING_WORKER_PULL_REQUEST_MAX_MESSAGES", 1000)
PARALLEL_PROCESSES = get_int_environment_value("PARALLEL_PROCESSES", 1)
NUMBER_OF_CONCURRENT_LOG_FORWARDING_LOOPS = get_int_environment_value("NUMBER_OF_CONCURRENT_LOG_FORWARDING_LOOPS", 5)
# Default 10:10 ratio is safe for most deployments (1.25 vCPU / 1 Gi)
# For high-throughput (4 vCPU / 4 Gi), set to 20:20
NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES = get_int_environment_value("NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES", 10)
NUMBER_OF_CONCURRENT_PUSH_COROUTINES = get_int_environment_value("NUMBER_OF_CONCURRENT_PUSH_COROUTINES", 10)

# ACK coroutines: auto-calculate to match push coroutines if not explicitly set
# Experiments show 1:1 push:ack ratio is optimal
# Empty string or missing → auto-calculate; positive integer → use that value
_ack_coroutines_env = os.environ.get("NUMBER_OF_CONCURRENT_ACK_COROUTINES", "").strip()
if _ack_coroutines_env and _ack_coroutines_env.isdigit() and int(_ack_coroutines_env) > 0:
    NUMBER_OF_CONCURRENT_ACK_COROUTINES = int(_ack_coroutines_env)
else:
    # Auto-calculate: match push coroutines (1:1 ratio), minimum 5
    NUMBER_OF_CONCURRENT_ACK_COROUTINES = max(5, NUMBER_OF_CONCURRENT_PUSH_COROUTINES)
MAX_SFM_MESSAGES_PROCESSED = 10_000
LOGS_SUBSCRIPTION_PROJECT = os.environ.get("GCP_PROJECT", os.environ.get("LOGS_SUBSCRIPTION_PROJECT", None))
LOGS_SUBSCRIPTION_ID = os.environ.get('LOGS_SUBSCRIPTION_ID', None)
CONTENT_LENGTH_LIMIT = get_int_environment_value("DYNATRACE_LOG_INGEST_CONTENT_MAX_LENGTH", 8192)
ATTRIBUTE_VALUE_LENGTH_LIMIT = get_int_environment_value("DYNATRACE_LOG_INGEST_ATTRIBUTE_VALUE_MAX_LENGTH", 250)
EVENT_AGE_LIMIT_SECONDS = get_int_environment_value("DYNATRACE_LOG_INGEST_EVENT_MAX_AGE_SECONDS", int(timedelta(days=1).total_seconds()))
SENDING_WORKER_EXECUTION_PERIOD_SECONDS = get_int_environment_value("DYNATRACE_LOG_INGEST_SENDING_WORKER_EXECUTION_PERIOD", 60)
SFM_WORKER_EXECUTION_PERIOD_SECONDS = get_int_environment_value("DYNATRACE_LOG_INGEST_SFM_WORKER_EXECUTION_PERIOD", 60)
LOG_PROCESS_STARTUP_DELAY_SECONDS =  get_int_environment_value("LOG_PROCESS_STARTUP_DELAY_SECONDS", 15)
REQUEST_BODY_MAX_SIZE = get_int_environment_value("DYNATRACE_LOG_INGEST_REQUEST_MAX_SIZE", 5242000)
REQUEST_MAX_EVENTS = get_int_environment_value("DYNATRACE_LOG_INGEST_REQUEST_MAX_EVENTS", 50_000)
BATCH_MAX_MESSAGES = get_int_environment_value("DYNATRACE_LOG_INGEST_BATCH_MAX_MESSAGES", 10_000)
DYNATRACE_LOG_INGEST_CONTENT_MARK_TRIMMED = "[TRUNCATED]"
CLOUD_LOG_FORWARDER = os.environ.get("CLOUD_LOG_FORWARDER", "")
CLOUD_LOG_FORWARDER_POD = os.environ.get("HOSTNAME", "")
