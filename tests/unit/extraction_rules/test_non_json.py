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
import datetime
from queue import Queue

from lib.context import LogsProcessingContext
from lib.logs import logs_processor
from lib.logs.metadata_engine import ATTRIBUTE_TIMESTAMP, ATTRIBUTE_CONTENT, ATTRIBUTE_CLOUD_PROVIDER


def test_extraction_non_json():
    publish_time = datetime.datetime.now(datetime.timezone.utc)

    context = LogsProcessingContext(
        scheduled_execution_id="test",
        message_publish_time=publish_time,
        sfm_queue=Queue()
    )
    actual_output = logs_processor._create_dt_log_payload(context, "Hello World")
    assert actual_output == {
        ATTRIBUTE_CLOUD_PROVIDER: 'gcp',
        ATTRIBUTE_TIMESTAMP: publish_time.isoformat(),
        ATTRIBUTE_CONTENT: "Hello World"
    }
