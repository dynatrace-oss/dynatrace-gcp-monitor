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
from datetime import datetime
from queue import Queue
from typing import NewType, Any

import pytest
from google.cloud.pubsub_v1.subscriber._protocol.requests import AckRequest
from google.cloud.pubsub_v1.subscriber.message import Message
from google.protobuf.timestamp_pb2 import Timestamp
from google.pubsub_v1 import PubsubMessage
from wiremock.constants import Config
from wiremock.resources.mappings import MappingRequest, HttpMethods, MappingResponse, Mapping
from wiremock.resources.mappings.resource import Mappings
from wiremock.resources.requests.resource import Requests
from wiremock.server import WireMockServer

from lib.logs.logs_processor import create_process_message_handler
from lib.logs.logs_sending_worker import _loop_single_period

LOG_MESSAGE_DATA = '{"insertId":"000000-ff1a5bfd-b64a-442e-91b2-deba5557dbfe","labels":{"execution_id":"zh2htc8ax7y6"},"logName":"projects/dynatrace-gcp-extension/logs/cloudfunctions.googleapis.com%2Fcloud-functions","receiveTimestamp":"2021-03-29T10:25:15.862698697Z","resource":{"labels":{"function_name":"dynatrace-gcp-function","project_id":"dynatrace-gcp-extension","region":"us-central1"},"type":"cloud_function"},"severity":"INFO","textPayload":"2021-03-29 10:25:11.101768  : Access to following projects: dynatrace-gcp-extension","timestamp":"2021-03-29T10:25:11.101Z","trace":"projects/dynatrace-gcp-extension/traces/f748c1e106a134178afee611c90bf984"}'

MOCKED_API_PORT = 9011
ACCESS_KEY = 'abcdefjhij1234567890'

MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)
system_variables = {
    # 'DYNATRACE_LOG_INGEST_CONTENT_MAX_LENGTH': str(500),
    'DYNATRACE_LOG_INGEST_REQUEST_MAX_SIZE': str(5 * 1024),
    'DYNATRACE_URL': 'http://localhost:' + str(MOCKED_API_PORT),
    'DYNATRACE_ACCESS_KEY': ACCESS_KEY,
    'REQUIRE_VALID_CERTIFICATE': 'False'
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


def test_execution_successful():
    expected_cluster_response_code = 200

    response(expected_cluster_response_code, "Success")

    ack_queue = Queue()
    job_queue = Queue()

    message_handler = create_process_message_handler(job_queue)

    expected_ack_ids = [f"ACK_ID_{i}" for i in range(0, 10)]

    message_data_json = json.loads(LOG_MESSAGE_DATA)
    message_data_json["timestamp"] = datetime.utcnow().isoformat() + "Z"
    fresh_message_data = json.dumps(message_data_json)

    for ack_id in expected_ack_ids:
        message = create_fake_message(ack_queue, ack_id=ack_id, message_data=fresh_message_data)
        message_handler(message)

    _loop_single_period(0, job_queue)
    job_queue.join()

    assert ack_queue.qsize() == len(expected_ack_ids)
    while ack_queue.qsize() > 0:
        request = ack_queue.get_nowait()
        assert isinstance(request, AckRequest)
        assert request.ack_id in expected_ack_ids
        expected_ack_ids.remove(request.ack_id)

    verify_requests(expected_cluster_response_code)


def verify_requests(expected_cluster_response_code):
    sent_requests = Requests.get_all_received_requests().get_json_data().get('requests')
    assert len(sent_requests) > 0
    for request in sent_requests:
        assert_correct_body_structure(request)
        assert request.get('responseDefinition').get('status') == expected_cluster_response_code


def assert_correct_body_structure(request):
    request_body = request.get("request", {}).get("body", None)
    assert request_body
    request_data = json.loads(request_body)

    for record in request_data:
        assert 'cloud.provider' in record
        assert record.get("cloud.provider") == "gcp"
        assert 'content' in record
        assert 'timestamp' in record


def create_fake_message(
        ack_queue,
        message_data,
        ack_id="ACK_ID",
        message_id="MESSAGE_ID",
        timestamp_epoch_seconds=int(time.time())
):
    publish_time_timestamp = Timestamp()
    publish_time_timestamp.seconds = timestamp_epoch_seconds

    pubsub_message = PubsubMessage()
    pubsub_message.data = message_data.encode("UTF-8")
    pubsub_message.message_id = message_id
    pubsub_message.publish_time = publish_time_timestamp
    pubsub_message.ordering_key = ""

    return Message(PubsubMessage.pb(pubsub_message), ack_id, 0, ack_queue)
