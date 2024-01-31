import time
import asyncio
from typing import List, Tuple
from lib.clientsession_provider import init_gcp_client_session, init_dt_client_session
from lib.context import LoggingContext, LogsProcessingContext, create_logs_context
from lib.credentials import create_token
from lib.logs.dynatrace_client import DynatraceClient
from lib.logs.gcp_client import GCPClient
from lib.logs.log_self_monitoring import put_sfm_into_queue
from lib.logs.logs_processor import (
    prepare_context_and_process_message,
    prepare_batches,
    LogBatch,
)
from lib.utilities import chunks
from lib.logs.log_forwarder_variables import (
    REQUEST_BODY_MAX_SIZE,
    NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES,
    NUMBER_OF_CONCURRENT_PUSH_COROUTINES,
)


class LogIntegrationService:
    def __init__(self, sfm_queue: asyncio.Queue):
        self.gcp_client = None
        self.dynatrace_client = DynatraceClient()
        self.sfm_queue = sfm_queue
        self.log_push_semaphore = asyncio.Semaphore(NUMBER_OF_CONCURRENT_PUSH_COROUTINES)

    async def update_gcp_client(self, logging_context: LoggingContext):
        async with init_gcp_client_session() as gcp_session:
            token = await create_token(logging_context, gcp_session)
            if token is None:
                raise Exception("Cannot start pub/sub pulling - Failed to fetch token")
            self.gcp_client = GCPClient(token)

    async def keep_gcp_token_updated(self, logging_context: LoggingContext):
        while True:
            await asyncio.sleep(20 * 60)
            task = self.update_gcp_client(logging_context)
            try:
                await asyncio.wait_for(task, 5 * 60)
            except asyncio.exceptions.TimeoutError as e:
                raise Exception("Failed to fetch Google API token")

    async def perform_pull(
        self, logging_context: LoggingContext
    ) -> Tuple[List[LogBatch], List[str]]:
        async with init_gcp_client_session() as gcp_session:
            context = LogsProcessingContext(None, None, self.sfm_queue)
            context.self_monitoring.pulling_time_start = time.perf_counter()

            tasks_to_pull_messages = [
                self.gcp_client.pull_messages(logging_context, gcp_session)
                for _ in range(NUMBER_OF_CONCURRENT_MESSAGE_PULL_COROUTINES)
            ]
            responses = await asyncio.gather(*tasks_to_pull_messages, return_exceptions=True)

            context.self_monitoring.calculate_pulling_time()
            processed_messages = []
            ack_ids_of_erroneous_messages = []

            context.self_monitoring.processing_time_start = time.perf_counter()
            for response in responses:
                if not isinstance(response, Exception):
                    for received_message in response.get("receivedMessages", []):  # type: ignore
                        message_job = prepare_context_and_process_message(
                            self.sfm_queue, received_message
                        )
                        if not message_job or message_job.bytes_size > REQUEST_BODY_MAX_SIZE - 2:
                            ack_ids_of_erroneous_messages.append(received_message.get("ackId"))
                            continue
                        processed_messages.append(message_job)
            context.self_monitoring.calculate_processing_time()
            put_sfm_into_queue(context)
            return (
                prepare_batches(processed_messages) if processed_messages else [],
                ack_ids_of_erroneous_messages,
            )

    async def push_logs(self, log_batches, logging_context: LoggingContext) -> List[str]:
        ack_ids_to_send = []
        context = create_logs_context(self.sfm_queue)
        batch_length = len(log_batches)
        if batch_length == 0:
            logging_context.log(f"Skipping pushing logs - no logs to push")
            return []

        logging_context.log(f"Number of log batches to push to Dynatrace: {batch_length}")

        async def process_batch(batch: LogBatch):
            async with self.log_push_semaphore:
                await self.dynatrace_client.send_logs(context, dt_session, batch, ack_ids_to_send)

        context.self_monitoring.sending_time_start = time.perf_counter()
        async with init_dt_client_session() as dt_session:
            exceptions = await asyncio.gather(
                *[process_batch(batch) for batch in log_batches], return_exceptions=True
            )
        context.self_monitoring.calculate_sending_time()
        put_sfm_into_queue(context)

        return ack_ids_to_send

    async def push_ack_ids(self, ack_ids: List[str], logging_context: LoggingContext):
        # request size limit is 524288, but we are not able to easily control size of created protobuf
        # empiric test indicates that ack_ids have around 200-220 chars. We can safely assume that ack id is never longer
        # than 256 chars, we split ack ids into chunks with no more than 2048 ack_id's
        async with init_gcp_client_session() as gcp_session:
            chunk_size = 2048
            tasks_to_send_ack_ids = [
                self.gcp_client.push_ack_ids(chunk, gcp_session, logging_context)
                for chunk in chunks(ack_ids, chunk_size)
            ]
            exceptions = await asyncio.gather(*tasks_to_send_ack_ids, return_exceptions=True)
        if ack_ids:
            logging_context.log("Log ingest payload has been pushed successfully")
