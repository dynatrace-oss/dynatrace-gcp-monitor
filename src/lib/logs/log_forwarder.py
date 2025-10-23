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

import asyncio
from asyncio import Queue

from lib.context import LoggingContext
from lib.instance_metadata import InstanceMetadata
from lib.logs.log_forwarder_variables import (
    LOGS_SUBSCRIPTION_ID,
    LOGS_SUBSCRIPTION_PROJECT,
    MAX_SFM_MESSAGES_PROCESSED,
    NUMBER_OF_CONCURRENT_LOG_FORWARDING_LOOPS,
    LOG_PROCESS_STARTUP_DELAY_SECONDS,
)
from lib.logs.log_self_monitoring import create_sfm_loop
from lib.logs.log_integration_service import LogIntegrationService


def run_logs_wrapper(logging_context, instance_metadata, process_number):
    asyncio.run(run_logs(logging_context, instance_metadata, process_number))


async def run_logs(
    logging_context: LoggingContext, instance_metadata: InstanceMetadata, process_number
):
    if not LOGS_SUBSCRIPTION_PROJECT or not LOGS_SUBSCRIPTION_ID:
        raise Exception(
            "Cannot start pubsub pulling - LOGS_SUBSCRIPTION_PROJECT or LOGS_SUBSCRIPTION_ID are not defined"
        )

    # Each process starts later than the previous one
    await asyncio.sleep(process_number * LOG_PROCESS_STARTUP_DELAY_SECONDS)

    sfm_queue = Queue(MAX_SFM_MESSAGES_PROCESSED)
    logging_context.log(
        f"Using Pub/Sub subscription: projects/{LOGS_SUBSCRIPTION_PROJECT}/subscriptions/{LOGS_SUBSCRIPTION_ID}"
    )
    log_integration_service = await LogIntegrationService.create(sfm_queue=sfm_queue, logging_context=logging_context)

    tasks = []

    for worker_number in range(0, NUMBER_OF_CONCURRENT_LOG_FORWARDING_LOOPS):
        worker_task = asyncio.create_task(
            pull_and_push_logs_forever(process_number, worker_number, log_integration_service)
        )
        tasks.append(worker_task)

    sfm_task = asyncio.create_task(create_sfm_loop(sfm_queue, logging_context, instance_metadata))
    tasks.append(sfm_task)

    await asyncio.gather(*tasks)


async def pull_and_push_logs_forever(
    process_number: int, worker_number: int, log_integration_service: LogIntegrationService
):
    logging_context = LoggingContext(f"Process-{process_number}", f"Worker-{worker_number}")
    logging_context.log(f"Starting processing")
    while True:
        try:
            # Pull logs from pub/sub, process them and create batches out of them to send to Dynatrace
            log_batches, ack_ids_of_erroneous_messages = await log_integration_service.perform_pull(logging_context)

            # Push logs batches to Dynatrace
            ack_ids_to_send = await log_integration_service.push_logs(log_batches, logging_context)

            # Push ACK_IDs to pub/sub
            ack_ids_to_send.extend(ack_ids_of_erroneous_messages)
            await log_integration_service.push_ack_ids(ack_ids_to_send, logging_context)
        except Exception as e:
            logging_context.exception(f"Failed to pull or push messages: {e}")
            # Backoff for 1 minute to avoid spamming requests and logs
            await asyncio.sleep(60)
