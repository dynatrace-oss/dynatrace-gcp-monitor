#     Copyright 2020 Dynatrace LLC
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
import json
import time
from collections import Counter
from datetime import datetime
from importlib import reload
from queue import Queue
from typing import NewType, Any, List, Dict

import pytest
from google.protobuf.timestamp_pb2 import Timestamp
from google.pubsub_v1 import PubsubMessage, PullResponse, ReceivedMessage, PullRequest
from wiremock.constants import Config
from wiremock.resources.mappings import MappingRequest, HttpMethods, MappingResponse, Mapping
from wiremock.resources.mappings.resource import Mappings
from wiremock.resources.requests.resource import Requests
from wiremock.server import WireMockServer

from lib.context import LoggingContext, DynatraceConnectivity
from lib.instance_metadata import InstanceMetadata
from lib.logs import log_self_monitoring, log_forwarder_variables, logs_processor, dynatrace_client, worker_state
from lib.logs.log_forwarder import WorkerState, perform_pull, perform_flush
from lib.logs.log_self_monitoring import LogSelfMonitoring
from lib.logs.metadata_engine import ATTRIBUTE_TIMESTAMP, ATTRIBUTE_CONTENT, ATTRIBUTE_CLOUD_PROVIDER

LOG_MESSAGE_DATA = '{"insertId":"000000-ff1a5bfd-b64a-442e-91b2-deba5557dbfe","labels":{"execution_id":"zh2htc8ax7y6"},"logName":"projects/dynatrace-gcp-extension/logs/cloudfunctions.googleapis.com%2Fcloud-functions","receiveTimestamp":"2021-03-29T10:25:15.862698697Z","resource":{"labels":{"function_name":"dynatrace-gcp-monitor","project_id":"dynatrace-gcp-extension","region":"us-central1"},"type":"not_cloud_function"},"severity":"INFO","textPayload":"2021-03-29 10:25:11.101768  : Access to following projects: dynatrace-gcp-extension","timestamp":"2021-03-29T10:25:11.101Z","trace":"projects/dynatrace-gcp-extension/traces/f748c1e106a134178afee611c90bf984"}'
INVALID_TIMESTAMP_DATA = '{"insertId":"000000-ff1a5bfd-b64a-442e-91b2-deba5557dbfe","labels":{"execution_id":"zh2htc8ax7y6"},"logName":"projects/dynatrace-gcp-extension/logs/cloudfunctions.googleapis.com%2Fcloud-functions","receiveTimestamp":"2021-03-29T10:25:15.862698697Z","resource":{"labels":{"function_name":"dynatrace-gcp-monitor","project_id":"dynatrace-gcp-extension","region":"us-central1"},"type":"not_cloud_function"},"severity":"INFO","textPayload":"2021-03-29 10:25:11.101768  : Access to following projects: dynatrace-gcp-extension","timestamp":"INVALID_TIMESTAMP","trace":"projects/dynatrace-gcp-extension/traces/f748c1e106a134178afee611c90bf984"}'

MOCKED_API_PORT = 9011
ACCESS_KEY = 'abcdefjhij1234567890'

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)
system_variables = {
    'DYNATRACE_LOG_INGEST_CONTENT_MAX_LENGTH': str(800),
    'DYNATRACE_LOG_INGEST_REQUEST_MAX_SIZE': str(5 * 1024),
    'DYNATRACE_LOG_INGEST_URL': 'http://localhost:' + str(MOCKED_API_PORT),
    'DYNATRACE_ACCESS_KEY': ACCESS_KEY,
    'REQUIRE_VALID_CERTIFICATE': 'False',
    'GCP_PROJECT': 'dynatrace-gcp-extension'
    # Set below-mentioned environment variables to push custom metrics to GCP Monitor
    # 'SELF_MONITORING_ENABLED': 'True',
    # 'GOOGLE_APPLICATION_CREDENTIALS': '',
    # 'LOGS_SUBSCRIPTION_ID': ''
}


@pytest.fixture(scope="session", autouse=True)
def setup_wiremock():
    # setup WireMock server
    wiremock = WireMockServer(port=MOCKED_API_PORT)
    wiremock.start()
    Config.base_url = 'http://localhost:{}/__admin'.format(MOCKED_API_PORT)

    # run test
    yield

    # stop WireMock server
    wiremock.stop()


@pytest.fixture(scope="function", autouse=True)
def cleanup():
    Mappings.delete_all_mappings()
    Requests.reset_request_journal()


@pytest.fixture(scope="function", autouse=True)
def setup_env(monkeypatch):
    for variable_name in system_variables:
        monkeypatch.setenv(variable_name, system_variables[variable_name])
    reload(log_forwarder_variables)
    reload(logs_processor)
    reload(worker_state)
    reload(log_self_monitoring)
    reload(dynatrace_client)


def response(status: int, status_message: str):
    Mappings.create_mapping(mapping=Mapping(
        priority=100,
        request=MappingRequest(
            method=HttpMethods.POST,
            url='/api/v2/logs/ingest',
            headers={'Authorization': {'equalTo': "Api-Token {}".format(ACCESS_KEY)}},
        ),
        response=MappingResponse(
            status=status,
            status_message=status_message
        ),
        persistent=False
    ))


class MockSubscriberClient:
    received_messages: List[ReceivedMessage]
    ack_queue: Queue

    def __init__(self, ack_queue: Queue, messages: List[ReceivedMessage] = None):
        self.received_messages = messages if messages else []
        self.ack_queue = ack_queue

    def add_message(self, message: ReceivedMessage):
        self.received_messages.append(message)

    def add_all_messages(self, messages: List[ReceivedMessage]):
        self.received_messages += messages

    def pull(self, pull_request: PullRequest) -> PullResponse:
        pull_response = PullResponse()
        pull_response.received_messages = self.received_messages.copy()
        return pull_response

    def acknowledge(self, request: Dict):
        for ack_id in request.get("ack_ids", []):
            self.ack_queue.put_nowait(ack_id)


@pytest.mark.asyncio
async def test_execution_successful():
    expected_cluster_response_code = 200

    response(expected_cluster_response_code, "Success")

    message_data_json = load_json_with_fresh_timestamp()
    fresh_message_data = json.dumps(message_data_json)

    expected_ack_ids = [f"ACK_ID_{i}" for i in range(0, 10)]
    messages = [
        create_fake_message(ack_id=ack_id, message_data=fresh_message_data)
        for ack_id
        in expected_ack_ids
    ]

    self_monitoring = await run_worker_with_messages(messages, expected_ack_ids)

    verify_requests(expected_cluster_response_code, 3)

    assert self_monitoring.too_old_records == 0
    assert self_monitoring.records_with_too_long_content == 0
    assert Counter(self_monitoring.dynatrace_connectivity) == {DynatraceConnectivity.Ok: 3}
    assert self_monitoring.processing_time > 0
    assert self_monitoring.sending_time > 0
    assert self_monitoring.sent_logs_entries == 10
    assert self_monitoring.parsing_errors == 0
    assert self_monitoring.publish_time_fallback_records == 0


@pytest.mark.asyncio
async def test_content_too_long():
    expected_cluster_response_code = 200

    response(expected_cluster_response_code, "Success")

    ack_id = 'CONTENT_TOO_LONG'

    message_data_json = load_json_with_fresh_timestamp()
    message_data_json["content"] = "LOTS_OF_DATA "*100
    too_long_content_message_data = json.dumps(message_data_json)

    messages = [create_fake_message(ack_id=ack_id, message_data=too_long_content_message_data)]
    expected_ack_ids = [ack_id]

    self_monitoring = await run_worker_with_messages(messages, expected_ack_ids)

    verify_requests(expected_cluster_response_code, 1)

    assert self_monitoring.too_old_records == 0
    assert self_monitoring.records_with_too_long_content == 1
    assert Counter(self_monitoring.dynatrace_connectivity) == {DynatraceConnectivity.Ok: 1}
    assert self_monitoring.processing_time > 0
    assert self_monitoring.sending_time > 0
    assert self_monitoring.sent_logs_entries == 1
    assert self_monitoring.parsing_errors == 0
    assert self_monitoring.publish_time_fallback_records == 0


@pytest.mark.asyncio
async def test_too_old_message():
    expected_cluster_response_code = 200

    response(expected_cluster_response_code, "Success")

    ack_id = 'TOO_OLD'

    messages = [create_fake_message(ack_id=ack_id, message_data=LOG_MESSAGE_DATA)]
    expected_ack_ids = [ack_id]

    self_monitoring = await run_worker_with_messages(messages, expected_ack_ids)

    verify_requests(expected_cluster_response_code, 0)

    assert self_monitoring.too_old_records == 1
    assert self_monitoring.records_with_too_long_content == 0
    assert not self_monitoring.dynatrace_connectivity
    assert self_monitoring.processing_time > 0
    assert self_monitoring.sending_time == 0
    assert self_monitoring.sent_logs_entries == 0
    assert self_monitoring.parsing_errors == 0
    assert self_monitoring.publish_time_fallback_records == 0


@pytest.mark.asyncio
async def test_invalid_timestamp():
    expected_cluster_response_code = 200

    response(expected_cluster_response_code, "Success")

    ack_id = 'INVALID_TIMESTAMP'

    messages = [create_fake_message(ack_id=ack_id, message_data=INVALID_TIMESTAMP_DATA)]
    expected_ack_ids = [ack_id]

    self_monitoring = await run_worker_with_messages(messages, expected_ack_ids)

    verify_requests(expected_cluster_response_code, 1)

    assert self_monitoring.too_old_records == 0
    assert self_monitoring.records_with_too_long_content == 0
    assert Counter(self_monitoring.dynatrace_connectivity) == {DynatraceConnectivity.Ok: 1}
    assert self_monitoring.processing_time > 0
    assert self_monitoring.sending_time > 0
    assert self_monitoring.sent_logs_entries == 1
    assert self_monitoring.parsing_errors == 0
    assert self_monitoring.publish_time_fallback_records == 1


@pytest.mark.asyncio
async def test_binary_data():
    expected_cluster_response_code = 200

    response(expected_cluster_response_code, "Success")

    ack_id = 'INVALID_TIMESTAMP'

    binary_message = create_fake_message(ack_id=ack_id, message_data="")
    binary_message.message.data = b'\xc3\x28'  # Invalid 2 Octet Sequence
    messages = [binary_message]
    expected_ack_ids = [ack_id]

    self_monitoring = await run_worker_with_messages(messages, expected_ack_ids)

    verify_requests(expected_cluster_response_code, 0)

    assert self_monitoring.too_old_records == 0
    assert self_monitoring.records_with_too_long_content == 0
    assert not self_monitoring.dynatrace_connectivity
    assert self_monitoring.processing_time > 0
    assert self_monitoring.sending_time == 0
    assert self_monitoring.sent_logs_entries == 0
    assert self_monitoring.parsing_errors == 1
    assert self_monitoring.publish_time_fallback_records == 0


@pytest.mark.asyncio
async def test_plain_text_message():
    expected_cluster_response_code = 200

    response(expected_cluster_response_code, "Success")

    ack_id = 'PLAIN_TEXT'

    messages = [create_fake_message(ack_id=ack_id, message_data="Plain Text message")]
    expected_ack_ids = [ack_id]

    self_monitoring = await run_worker_with_messages(messages, expected_ack_ids)

    verify_requests(expected_cluster_response_code, 1)

    assert self_monitoring.too_old_records == 0
    assert self_monitoring.records_with_too_long_content == 0
    assert Counter(self_monitoring.dynatrace_connectivity) == {DynatraceConnectivity.Ok: 1}
    assert self_monitoring.processing_time > 0
    assert self_monitoring.sending_time > 0
    assert self_monitoring.sent_logs_entries == 1
    assert self_monitoring.parsing_errors == 0
    assert self_monitoring.publish_time_fallback_records == 1


@pytest.mark.asyncio
async def test_execution_expired_token():
    expected_cluster_response_code = 401
    expected_sent_requests = 3

    response(expected_cluster_response_code, "Expired token")

    message_data_json = load_json_with_fresh_timestamp()
    fresh_message_data = json.dumps(message_data_json)

    messages = [
        create_fake_message(ack_id=ack_id, message_data=fresh_message_data)
        for ack_id
        in [f"ACK_ID_{i}" for i in range(0, 10)]
    ]

    self_monitoring = await run_worker_with_messages(messages, [])

    verify_requests(expected_cluster_response_code, expected_sent_requests)

    assert self_monitoring.too_old_records == 0
    assert self_monitoring.parsing_errors == 0
    assert self_monitoring.records_with_too_long_content == 0
    assert Counter(self_monitoring.dynatrace_connectivity) == {DynatraceConnectivity.ExpiredToken: 3}
    assert self_monitoring.processing_time > 0
    assert self_monitoring.sending_time > 0


async def run_worker_with_messages(
        messages: List[ReceivedMessage],
        expected_ack_ids: List[str],
) -> LogSelfMonitoring:
    ack_queue = Queue()
    sfm_queue = Queue()
    mock_subscriber_client = MockSubscriberClient(ack_queue, messages)
    pull_request = PullRequest()

    test_worker_state = WorkerState("TEST")
    logging_context = LoggingContext("Logging context - test")
    perform_pull(test_worker_state, sfm_queue, mock_subscriber_client, "", pull_request, logging_context)
    # Flush down rest of messages
    perform_flush(test_worker_state, sfm_queue, mock_subscriber_client, "")

    metadata = InstanceMetadata(
        project_id="",
        container_name="",
        token_scopes="",
        service_account="",
        audience="",
        hostname="local deployment 1",
        zone="us-east1"
    )

    self_monitoring = LogSelfMonitoring()
    await log_self_monitoring._loop_single_period(self_monitoring, sfm_queue, LoggingContext("TEST"), metadata)
    sfm_queue.join()

    assert ack_queue.qsize() == len(expected_ack_ids)
    while ack_queue.qsize() > 0:
        ack_id = ack_queue.get_nowait()
        assert ack_id in expected_ack_ids
        expected_ack_ids.remove(ack_id)

    assert len(expected_ack_ids) == 0

    return self_monitoring


def load_json_with_fresh_timestamp() -> Dict:
    message_data_json = json.loads(LOG_MESSAGE_DATA)
    message_data_json["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return message_data_json


def verify_requests(expected_cluster_response_code, expected_sent_requests):
    sent_requests = Requests.get_all_received_requests().get_json_data().get('requests')
    assert len(sent_requests) == expected_sent_requests
    for request in sent_requests:
        assert_correct_body_structure(request)
        assert request.get('responseDefinition').get('status') == expected_cluster_response_code


def assert_correct_body_structure(request):
    request_body = request.get("request", {}).get("body", None)
    assert request_body
    request_data = json.loads(request_body)

    for record in request_data:
        assert record.get(ATTRIBUTE_CLOUD_PROVIDER, None) == "gcp"
        assert ATTRIBUTE_CONTENT in record
        assert ATTRIBUTE_TIMESTAMP in record


def create_fake_message(
        message_data,
        ack_id="ACK_ID",
        message_id="MESSAGE_ID",
        timestamp_epoch_seconds=int(time.time())
) -> ReceivedMessage:
    publish_time_timestamp = Timestamp()
    publish_time_timestamp.seconds = timestamp_epoch_seconds

    pubsub_message = PubsubMessage()
    pubsub_message.data = message_data.encode("UTF-8")
    pubsub_message.message_id = message_id
    pubsub_message.publish_time = publish_time_timestamp
    pubsub_message.ordering_key = ""

    received_message = ReceivedMessage()
    received_message.ack_id = ack_id
    received_message.message = pubsub_message
    received_message.delivery_attempt = 0

    return received_message
