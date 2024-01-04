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
import time
from asyncio import Queue
from typing import List

from lib.clientsession_provider import init_gcp_client_session
from lib.context import LoggingContext, create_logs_context
from lib.credentials import create_token
from lib.instance_metadata import InstanceMetadata
from lib.logs.dynatrace_aio_client import DynatraceAioClient, DynatraceAioClientFactory
from lib.logs.gcp_aio_client import GCPAioClient, GCPAioClientFactory
from lib.logs.log_forwarder_variables import (
    LOGS_SUBSCRIPTION_ID,
    LOGS_SUBSCRIPTION_PROJECT,
    MAX_SFM_MESSAGES_PROCESSED,
    PROCESSING_WORKERS,
    REQUEST_BODY_MAX_SIZE,
)
from lib.logs.log_self_monitoring import create_sfm_loop
from lib.logs.logs_processor import prepare_context_and_process_message
from lib.logs.worker_state import WorkerState
from lib.utilities import chunks


def run_logs_wrapper(logging_context, instance_metadata):
    asyncio.run(run_logs(logging_context, instance_metadata))


async def run_logs(logging_context: LoggingContext, instance_metadata: InstanceMetadata):
    if not LOGS_SUBSCRIPTION_PROJECT or not LOGS_SUBSCRIPTION_ID:
        raise Exception(
            "Cannot start pubsub streaming pull - GCP_PROJECT or LOGS_SUBSCRIPTION_ID are not defined"
        )

    async with init_gcp_client_session() as gcp_session:
        token = await create_token(logging_context, gcp_session)
        gcp_client_factory = GCPAioClientFactory(token)
        dynatrace_client_factory = DynatraceAioClientFactory()

        sfm_queue = Queue(MAX_SFM_MESSAGES_PROCESSED)
        tasks = []

        for i in range(0, PROCESSING_WORKERS):
            worker_task = asyncio.create_task(
                pull_and_flush_logs_forever(f"Worker-{i}", sfm_queue, gcp_client_factory,dynatrace_client_factory)
            )
            tasks.append(worker_task)


        sfm_task = asyncio.create_task(
            create_sfm_loop(sfm_queue, logging_context, instance_metadata)
        )
        tasks.append(sfm_task)

        await asyncio.gather(*tasks, return_exceptions=True)


import datetime
import time


async def worker(client, result_array, sem):
    async with sem:
        result = await client.pull_messages()

    messages = len(result.get("receivedMessages"))
    size_bytes = 0
    for r_m in result.get("receivedMessages"):
        sb = len(r_m.get("message").get("data"))
        size_bytes += sb

    result_array.append((messages, size_bytes))


async def perf_aio(factory: GCPAioClientFactory):
    semaphore = asyncio.Semaphore(10000)

    while True:
        client = factory.get_gcp_pub_client()

        array = []
        tasks = []
        start = time.time()

        for i in range(100):
            task = asyncio.ensure_future(worker(client, array, semaphore))
            tasks.append(task)
        await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start
        await client.aio_http_session.close()

        final_count = 0
        final_size = 0

        for res in array:
            final_count += res[0]
            final_size += res[1]

        print(
            f"[{datetime.datetime.now()}] Got: {final_count} messages. Size: {round(final_size/(1024*1024),3) } MB Elapsed: {elapsed} s"
        )


async def pull_and_flush_logs_forever(
    worker_name: str, sfm_queue: Queue, gcp_client_factory: GCPAioClientFactory, dynatrace_client_factory: DynatraceAioClientFactory
):
    logging_context = LoggingContext(worker_name)
    worker_state = WorkerState(worker_name)
    logging_context.log(f"Starting processing")
    while True:
        try:
            await perform_pull(
                worker_state, sfm_queue, gcp_client_factory.get_gcp_pub_client(), dynatrace_client_factory.get_dynatrace_client(), logging_context
            )
        except Exception as e:
            logging_context.exception("Failed to pull messages")
            # Backoff for 1 minute to avoid spamming requests and logs
            await asyncio.sleep(60)


async def perform_pull(
    worker_state: WorkerState,
    sfm_queue: Queue,
    gcp_aio_client: GCPAioClient,
    dynatrace_aio_client: DynatraceAioClient,
    logging_context: LoggingContext,
):
    async with gcp_aio_client as gcp_client, dynatrace_aio_client as dynatrace_client:
        response = await gcp_client.pull_messages(logging_context)

        for received_message in response.get("receivedMessages", []):
            message_job = prepare_context_and_process_message(sfm_queue, received_message)

            if not message_job or message_job.bytes_size > REQUEST_BODY_MAX_SIZE - 2:
                worker_state.ack_ids.append(received_message.get("ackId"))
                continue

            if worker_state.should_flush(message_job):
                await perform_flush(worker_state, sfm_queue, gcp_client, dynatrace_client)

            worker_state.add_job(message_job, received_message.get("ackId"))

        # check if worker_state should flush because of time
        if worker_state.should_flush():
            await perform_flush(worker_state, sfm_queue, gcp_client, dynatrace_client)


async def perform_flush(
    worker_state: WorkerState,
    sfm_queue: Queue,
    gcp_client: GCPAioClient,
    dynatrace_client: DynatraceAioClient,
):
    context = create_logs_context(sfm_queue)
    try:
        if worker_state.jobs:
            sent = False
            display_payload_size = round((worker_state.finished_batch_bytes_size / 1024), 3)
            try:
                context.log(
                    worker_state.worker_name, f"Log ingest payload size: {display_payload_size} kB"
                )
                await dynatrace_client.send_logs(context, worker_state.jobs, worker_state.finished_batch)
                context.log(worker_state.worker_name, "Log ingest payload pushed successfully")
                sent = True
            except Exception:
                context.exception(worker_state.worker_name, "Failed to ingest logs")
            if sent:
                context.self_monitoring.sent_logs_entries += len(worker_state.jobs)
                context.self_monitoring.log_ingest_payload_size += display_payload_size
                await send_batched_ack(gcp_client, worker_state.ack_ids,context )
        elif worker_state.ack_ids:
            # Send ACKs if processing all messages has failed
            await send_batched_ack(gcp_client, worker_state.ack_ids, context)
    except Exception:
        context.exception(worker_state.worker_name, "Failed to perform flush")
    finally:
        # reset state event if we failed to flush, to AVOID getting stuck in processing the same messages
        # over and over again and letting their acknowledgement deadline expire
        worker_state.reset()


async def send_batched_ack(gcp_client: GCPAioClient, ack_ids: List[str], logging_context: LoggingContext):
    # request size limit is 524288, but we are not able to easily control size of created protobuf
    # empiric test indicates that ack_ids have around 200-220 chars. We can safely assume that ack id is never longer
    # than 256 chars, we split ack ids into chunks with no more than 2048 ack_id's
    chunk_size = 2048
    if len(ack_ids) < chunk_size:
        await gcp_client.push_acks(ack_ids, logging_context)
    else:
        for chunk in chunks(ack_ids, chunk_size):
            await gcp_client.push_acks(chunk, logging_context)
