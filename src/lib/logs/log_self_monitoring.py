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
import asyncio
import os
import queue
import time
import traceback
from collections import Counter
from queue import Queue
from typing import Dict, List

import aiohttp

from lib.context import LoggingContext, LogsSfmContext, DynatraceConnectivity, LogsContext
from lib.credentials import create_token, get_dynatrace_log_ingest_url_from_env
from lib.instance_metadata import InstanceMetadata
from lib.logs.log_forwarder_variables import LOGS_SUBSCRIPTION_PROJECT, LOGS_SUBSCRIPTION_ID, \
    SFM_WORKER_EXECUTION_PERIOD_SECONDS, MAX_SFM_MESSAGES_PROCESSED
from lib.logs.log_sfm_metric_descriptor import LOG_SELF_MONITORING_CONNECTIVITY_METRIC_TYPE, \
    LOG_SELF_MONITORING_ALL_REQUESTS_METRIC_TYPE, \
    LOG_SELF_MONITORING_TOO_OLD_RECORDS_METRIC_TYPE, LOG_SELF_MONITORING_PARSING_ERRORS_METRIC_TYPE, \
    LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_TYPE, LOG_SELF_MONITORING_SENDING_TIME_SIZE_METRIC_TYPE, \
    LOG_SELF_MONITORING_TOO_LONG_CONTENT_METRIC_TYPE, LOG_SELF_MONITORING_LOG_INGEST_PAYLOAD_SIZE_METRIC_TYPE, \
    LOG_SELF_MONITORING_SENT_LOGS_ENTRIES_METRIC_TYPE, LOG_SELF_MONITORING_PUBLISH_TIME_FALLBACK_METRIC_TYPE
from lib.logs.log_sfm_metrics import LogSelfMonitoring
from lib.self_monitoring import push_self_monitoring_time_series


def aggregate_self_monitoring_metrics(aggregated_sfm: LogSelfMonitoring, sfm_list: List[LogSelfMonitoring]):
    for sfm in sfm_list:
        aggregated_sfm.all_requests += sfm.all_requests
        aggregated_sfm.too_old_records += sfm.too_old_records
        aggregated_sfm.publish_time_fallback_records += sfm.publish_time_fallback_records
        aggregated_sfm.parsing_errors += sfm.parsing_errors
        aggregated_sfm.records_with_too_long_content += sfm.records_with_too_long_content
        aggregated_sfm.dynatrace_connectivity.extend(sfm.dynatrace_connectivity)
        aggregated_sfm.processing_time += sfm.processing_time
        aggregated_sfm.sending_time += sfm.sending_time
        aggregated_sfm.log_ingest_payload_size += sfm.log_ingest_payload_size
        aggregated_sfm.sent_logs_entries += sfm.sent_logs_entries
    return aggregated_sfm


def put_sfm_into_queue(context: LogsContext):
    try:
        context.sfm_queue.put_nowait(context.self_monitoring)
    except Exception as exception:
        if isinstance(exception, queue.Full):
            context.error("Failed to add self-monitoring metric to queue due to full sfm queue, rejecting the sfm",
                          "sfm-full-queue-error")


async def create_sfm_worker_loop(sfm_queue: Queue, logging_context: LoggingContext, instance_metadata: InstanceMetadata):
    while True:
        try:
            await asyncio.sleep(SFM_WORKER_EXECUTION_PERIOD_SECONDS)
            self_monitoring = LogSelfMonitoring()
            asyncio.get_event_loop().create_task(_loop_single_period(self_monitoring, sfm_queue, logging_context, instance_metadata))
        except Exception:
            print("Logs Self Monitoring Worker Loop Exception:")
            traceback.print_exc()


async def _loop_single_period(self_monitoring: LogSelfMonitoring, sfm_queue: Queue, context: LoggingContext, instance_metadata: InstanceMetadata):
    try:
        sfm_list = _pull_sfm(sfm_queue)
        if sfm_list:
            async with aiohttp.ClientSession() as gcp_session:
                context = await _create_sfm_logs_context(sfm_queue, context, gcp_session, instance_metadata)
                self_monitoring = aggregate_self_monitoring_metrics(self_monitoring, sfm_list)
                _log_self_monitoring_data(self_monitoring, context)
                if context.self_monitoring_enabled:
                    if context.token is None:
                        context.log("Cannot proceed without authorization token, failed to send log self monitoring")
                        return
                    if not isinstance(context.token, str):
                        context.log(f"Failed to fetch access token, got non string value: {context.token}")
                        return
                    time_series = create_self_monitoring_time_series(self_monitoring, context)
                    await push_self_monitoring_time_series(context, time_series)
                for _ in sfm_list:
                    sfm_queue.task_done()
    except Exception:
        print("Log SFM Loop Exception:")
        traceback.print_exc()


async def _create_sfm_logs_context(sfm_queue, context: LoggingContext, gcp_session: aiohttp.ClientSession(), instance_metadata: InstanceMetadata):
    dynatrace_url = get_dynatrace_log_ingest_url_from_env()
    self_monitoring_enabled = os.environ.get('SELF_MONITORING_ENABLED', "FALSE").upper() in ["TRUE", "YES"]
    token = await create_token(context, gcp_session)
    container_name = instance_metadata.hostname if instance_metadata else "local deployment"
    zone = instance_metadata.zone if instance_metadata else "us-east1"
    return LogsSfmContext(
        project_id_owner=LOGS_SUBSCRIPTION_PROJECT,
        dynatrace_url=dynatrace_url,
        logs_subscription_id=LOGS_SUBSCRIPTION_ID,
        token=token,
        scheduled_execution_id=str(int(time.time()))[-8:],
        sfm_queue=sfm_queue,
        self_monitoring_enabled=self_monitoring_enabled,
        gcp_session=gcp_session,
        container_name=container_name,
        zone=zone
    )


def _pull_sfm(sfm_queue: Queue):
    sfm_list: List[LogSelfMonitoring] = []
    # Limit used to avoid pulling forever (the same as for job_queue)
    while len(sfm_list) < MAX_SFM_MESSAGES_PROCESSED and sfm_queue.qsize() > 0:
        single_sfm: LogSelfMonitoring = sfm_queue.get()
        sfm_list.append(single_sfm)
    return sfm_list


def _log_self_monitoring_data(self_monitoring: LogSelfMonitoring, logging_context: LoggingContext):
    dynatrace_connectivity = Counter(self_monitoring.dynatrace_connectivity)
    dynatrace_connectivity = [f"{connectivity.name}:{count}" for connectivity, count in dynatrace_connectivity.items()]
    dynatrace_connectivity = ", ".join(dynatrace_connectivity)
    logging_context.log("SFM", f"Number of all log ingest requests sent to Dynatrace: {self_monitoring.all_requests}")
    logging_context.log("SFM", f"Dynatrace connectivity: {dynatrace_connectivity}")
    logging_context.log("SFM", f"Number of log records with missing/invalid timestamp (used publish time): {self_monitoring.publish_time_fallback_records}")
    logging_context.log("SFM", f"Number of invalid log records due to too old timestamp: {self_monitoring.too_old_records}")
    logging_context.log("SFM", f"Number of errors occurred during parsing logs: {self_monitoring.parsing_errors}")
    logging_context.log("SFM", f"Number of records with too long content: {self_monitoring.records_with_too_long_content}")
    logging_context.log("SFM", f"Total logs processing time [s]: {self_monitoring.processing_time}")
    logging_context.log("SFM", f"Total logs sending time [s]: {self_monitoring.sending_time}")
    logging_context.log("SFM", f"Log ingest payload size [kB]: {self_monitoring.log_ingest_payload_size}")
    logging_context.log("SFM", f"Number of sent logs entries: {self_monitoring.sent_logs_entries}")


def create_time_serie(
        context: LogsSfmContext,
        metric_type: str,
        metric_labels: Dict,
        points: List[Dict],
        value_type: str = "INT64"):
    return {
        "resource": {
            "type": "generic_task",
            "labels": {
                "project_id": context.project_id_owner,
                "location": context.zone,
                "namespace": context.function_name,
                "job": context.function_name,
                "task_id": context.function_name
            }
        },
        "metric": {
            "type": metric_type,
            "labels": metric_labels
        },
        "valueType": value_type,
        "metricKind": "GAUGE",
        "points": points
    }


def create_self_monitoring_time_series(sfm: LogSelfMonitoring, context: LogsSfmContext) -> Dict:
    interval = {"endTime": context.timestamp.isoformat() + "Z"}
    time_series = []
    if sfm.all_requests:
        time_series.append(
            create_time_serie(
                context,
                LOG_SELF_MONITORING_ALL_REQUESTS_METRIC_TYPE,
                {
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "logs_subscription_id": context.logs_subscription_id,
                    "container_name": context.container_name
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.all_requests}
                }]))

    if sfm.too_old_records:
        time_series.append(
            create_time_serie(
                context,
                LOG_SELF_MONITORING_TOO_OLD_RECORDS_METRIC_TYPE,
                {
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "logs_subscription_id": context.logs_subscription_id,
                    "container_name": context.container_name
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.too_old_records}
                }]))

    if sfm.parsing_errors:
        time_series.append(
            create_time_serie(
                context,
                LOG_SELF_MONITORING_PARSING_ERRORS_METRIC_TYPE,
                {
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "logs_subscription_id": context.logs_subscription_id,
                    "container_name": context.container_name
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.parsing_errors}
                }]))

    if sfm.records_with_too_long_content:
        time_series.append(
            create_time_serie(
                context,
                LOG_SELF_MONITORING_TOO_LONG_CONTENT_METRIC_TYPE,
                {
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "logs_subscription_id": context.logs_subscription_id,
                    "container_name": context.container_name
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.records_with_too_long_content}
                }]))

    if sfm.publish_time_fallback_records:
        time_series.append(
            create_time_serie(
                context,
                LOG_SELF_MONITORING_PUBLISH_TIME_FALLBACK_METRIC_TYPE,
                {
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "logs_subscription_id": context.logs_subscription_id,
                    "container_name": context.container_name
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.publish_time_fallback_records}
                }]))

    time_series.append(create_time_serie(
            context,
            LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name
            },
            [{
                "interval": interval,
                "value": {"doubleValue": sfm.processing_time}
            }],
            "DOUBLE"))

    time_series.append(create_time_serie(
            context,
            LOG_SELF_MONITORING_SENDING_TIME_SIZE_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name
            },
            [{
                "interval": interval,
                "value": {"doubleValue": sfm.sending_time}
            }],
            "DOUBLE"))

    connectivity_counter = Counter(sfm.dynatrace_connectivity)
    for dynatrace_connectivity, counter in connectivity_counter.items():
        if dynatrace_connectivity.name != DynatraceConnectivity.Ok.name:
            time_series.append(create_time_serie(
                    context,
                    LOG_SELF_MONITORING_CONNECTIVITY_METRIC_TYPE,
                    {
                        "dynatrace_tenant_url": context.dynatrace_url,
                        "logs_subscription_id": context.logs_subscription_id,
                        "container_name": context.container_name,
                        "connectivity_status": dynatrace_connectivity.name
                    },
                    [{
                        "interval": interval,
                        "value": {"int64Value": counter}
                    }]))

    if sfm.log_ingest_payload_size:
        time_series.append(create_time_serie(
            context,
            LOG_SELF_MONITORING_LOG_INGEST_PAYLOAD_SIZE_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name
            },
            [{
                "interval": interval,
                "value": {"doubleValue": sfm.log_ingest_payload_size}
            }],
            "DOUBLE"
        ))

    if sfm.sent_logs_entries:
        time_series.append(create_time_serie(
            context,
            LOG_SELF_MONITORING_SENT_LOGS_ENTRIES_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name
            },
            [{
                "interval": interval,
                "value": {"int64Value": sfm.sent_logs_entries}
            }]
        ))

    return {"timeSeries": time_series}


