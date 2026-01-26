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
import os
import queue
import time
from collections import Counter
from asyncio import Queue
from typing import Dict, List

import aiohttp

from lib.clientsession_provider import init_gcp_client_session
from lib.configuration import config
from lib.context import LoggingContext, LogsSfmContext, LogsContext
from lib.credentials import create_token, fetch_dynatrace_log_ingest_url
from lib.instance_metadata import InstanceMetadata
from lib.logs.log_forwarder_variables import LOGS_SUBSCRIPTION_PROJECT, LOGS_SUBSCRIPTION_ID, \
    SFM_WORKER_EXECUTION_PERIOD_SECONDS, MAX_SFM_MESSAGES_PROCESSED
from lib.sfm.for_logs.log_sfm_metric_descriptor import LOG_SELF_MONITORING_CONNECTIVITY_METRIC_TYPE, \
    LOG_SELF_MONITORING_ALL_REQUESTS_METRIC_TYPE, LOG_SELF_MONITORING_PULLING_TIME_SIZE_METRIC_TYPE, \
    LOG_SELF_MONITORING_TOO_OLD_RECORDS_METRIC_TYPE, LOG_SELF_MONITORING_PARSING_ERRORS_METRIC_TYPE, \
    LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_TYPE, LOG_SELF_MONITORING_SENDING_TIME_SIZE_METRIC_TYPE, \
    LOG_SELF_MONITORING_TOO_LONG_CONTENT_METRIC_TYPE, LOG_SELF_MONITORING_LOG_INGEST_PAYLOAD_SIZE_METRIC_TYPE, \
    LOG_SELF_MONITORING_PULLED_LOGS_ENTRIES_METRIC_TYPE, LOG_SELF_MONITORING_SENT_LOGS_ENTRIES_METRIC_TYPE, \
    LOG_SELF_MONITORING_PUBLISH_TIME_FALLBACK_METRIC_TYPE, \
    LOG_SELF_MONITORING_RAW_LOG_INGEST_PAYLOAD_SIZE_METRIC_TYPE, LOG_SELF_MONITORING_ACK_FAILURES_METRIC_TYPE, \
    LOG_SELF_MONITORING_ACK_SUCCEEDED_METRIC_TYPE, LOG_SELF_MONITORING_ACK_BACKLOG_METRIC_TYPE, \
    LOG_SELF_MONITORING_PUSH_QUEUE_SIZE_METRIC_TYPE, LOG_SELF_MONITORING_PUSH_WAIT_TIME_METRIC_TYPE, \
    LOG_SELF_MONITORING_MESSAGES_PER_SECOND_METRIC_TYPE, LOG_SELF_MONITORING_BATCH_LATENCY_METRIC_TYPE
from lib.sfm.for_logs.log_sfm_metrics import LogSelfMonitoring
from lib.self_monitoring import push_self_monitoring_time_series, sfm_create_descriptors_if_missing


def aggregate_self_monitoring_metrics(aggregated_sfm: LogSelfMonitoring, sfm_list: List[LogSelfMonitoring]):
    for sfm in sfm_list:
        aggregated_sfm.all_requests += sfm.all_requests
        aggregated_sfm.too_old_records += sfm.too_old_records
        aggregated_sfm.publish_time_fallback_records += sfm.publish_time_fallback_records
        aggregated_sfm.parsing_errors += sfm.parsing_errors
        aggregated_sfm.records_with_too_long_content += sfm.records_with_too_long_content
        aggregated_sfm.dt_connectivity.extend(sfm.dt_connectivity)
        aggregated_sfm.gcp_connectivity.extend(sfm.gcp_connectivity)
        # Note: These times are CUMULATIVE across coroutines (may exceed wall-clock time)
        aggregated_sfm.processing_time += sfm.processing_time
        aggregated_sfm.pulling_time += sfm.pulling_time
        aggregated_sfm.sending_time += sfm.sending_time
        aggregated_sfm.log_ingest_payload_size += sfm.log_ingest_payload_size
        aggregated_sfm.log_ingest_raw_size += sfm.log_ingest_raw_size
        aggregated_sfm.pulled_logs_entries += sfm.pulled_logs_entries
        aggregated_sfm.sent_logs_entries += sfm.sent_logs_entries
        aggregated_sfm.ack_failures += sfm.ack_failures
        aggregated_sfm.acks_succeeded += sfm.acks_succeeded
        aggregated_sfm.ack_backlog = max(aggregated_sfm.ack_backlog, sfm.ack_backlog)
        # Bottleneck detection metrics
        aggregated_sfm.push_queue_size_max = max(aggregated_sfm.push_queue_size_max, sfm.push_queue_size_max)
        aggregated_sfm.push_wait_time += sfm.push_wait_time
        aggregated_sfm.messages_per_second += sfm.messages_per_second
        aggregated_sfm.batch_latency_total += sfm.batch_latency_total
        aggregated_sfm.batch_latency_count += sfm.batch_latency_count
    return aggregated_sfm


def put_sfm_into_queue(context: LogsContext):
    try:
        context.sfm_queue.put_nowait(context.self_monitoring)
    except Exception as exception:
        if isinstance(exception, queue.Full):
            context.error("Failed to add self-monitoring metric to queue due to full sfm queue, rejecting the sfm")


async def create_sfm_loop(sfm_queue: Queue, logging_context: LoggingContext, instance_metadata: InstanceMetadata):
    # Create a long-lived session instead of creating a new one every 60s
    async with init_gcp_client_session() as gcp_session:
        while True:
            try:
                await asyncio.sleep(SFM_WORKER_EXECUTION_PERIOD_SECONDS)
                self_monitoring = LogSelfMonitoring()
                await _loop_single_period(self_monitoring, sfm_queue, logging_context, instance_metadata, gcp_session)
            except Exception:
                logging_context.log("Logs Self Monitoring Loop Exception - will retry next cycle")


async def _loop_single_period(self_monitoring: LogSelfMonitoring,
                              sfm_queue: Queue,
                              context: LoggingContext,
                              instance_metadata: InstanceMetadata,
                              gcp_session: aiohttp.ClientSession):
    try:
        sfm_list = await _pull_sfm(sfm_queue)
        if sfm_list:
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

                await sfm_create_descriptors_if_missing(context)
                time_series = create_self_monitoring_time_series(self_monitoring, context)
                await push_self_monitoring_time_series(context, time_series)
            for _ in sfm_list:
                sfm_queue.task_done()
    except Exception:
        context.log("Log SFM Loop Exception - will retry next cycle")


async def _create_sfm_logs_context(sfm_queue, context: LoggingContext, gcp_session: aiohttp.ClientSession, instance_metadata: InstanceMetadata):
    self_monitoring_enabled = config.self_monitoring_enabled()
    token = await create_token(context, gcp_session)
    dynatrace_log_ingest_url = await fetch_dynatrace_log_ingest_url(
        gcp_session=gcp_session,
        project_id=config.project_id(),
        token=token,
    )
    container_name = instance_metadata.hostname if instance_metadata else "local deployment"
    zone = instance_metadata.zone if instance_metadata else "us-east1"
    return LogsSfmContext(
        project_id_owner=LOGS_SUBSCRIPTION_PROJECT,
        dynatrace_url=dynatrace_log_ingest_url,
        logs_subscription_id=LOGS_SUBSCRIPTION_ID,
        token=token,
        scheduled_execution_id=str(int(time.time()))[-8:],
        sfm_queue=sfm_queue,
        self_monitoring_enabled=self_monitoring_enabled,
        gcp_session=gcp_session,
        container_name=container_name,
        zone=zone,
        worker_pid = str(os.getpid())
    )


async def _pull_sfm(sfm_queue: Queue):
    sfm_list: List[LogSelfMonitoring] = []
    # Limit used to avoid pulling forever (the same as for job_queue)
    while len(sfm_list) < MAX_SFM_MESSAGES_PROCESSED and sfm_queue.qsize() > 0:
        single_sfm: LogSelfMonitoring = await sfm_queue.get()
        sfm_list.append(single_sfm)
    return sfm_list


def _log_self_monitoring_data(self_monitoring: LogSelfMonitoring, logging_context: LoggingContext):
    # Format HTTP status codes as "code:count" pairs (0 = network error)
    dt_connectivity = Counter(self_monitoring.dt_connectivity)
    dt_status = ", ".join(f"{code}:{count}" for code, count in sorted(dt_connectivity.items())) or "-"
    
    gcp_connectivity = Counter(self_monitoring.gcp_connectivity)
    gcp_status = ", ".join(f"{code}:{count}" for code, count in sorted(gcp_connectivity.items())) or "-"
    
    # Calculate derived metrics
    pulled = self_monitoring.pulled_logs_entries
    sent = self_monitoring.sent_logs_entries
    dropped = pulled - sent if pulled > 0 else 0
    
    # Throughput (messages per second based on wall-clock time)
    wall_clock_seconds = SFM_WORKER_EXECUTION_PERIOD_SECONDS
    throughput = sent / wall_clock_seconds if sent > 0 else 0
    self_monitoring.messages_per_second = throughput
    
    # === CORE METRICS (always logged) ===
    logging_context.log("SFM", f"Pipeline: pulled={pulled}, sent={sent}, dropped={dropped}")
    logging_context.log("SFM", f"Connectivity: DT={dt_status}, GCP={gcp_status}")
    logging_context.log("SFM", f"Timing [s]: pull={self_monitoring.pulling_time:.2f}, process={self_monitoring.processing_time:.2f}, send={self_monitoring.sending_time:.2f}")
    logging_context.log("SFM", f"ACKs: ok={self_monitoring.acks_succeeded}, failed={self_monitoring.ack_failures}, pending_tasks={self_monitoring.ack_backlog}")
    
    # === CONDITIONAL METRICS (only when relevant) ===
    
    # Payload and throughput (only when data was sent)
    if sent > 0:
        logging_context.log("SFM", f"Payload [kB]: {self_monitoring.log_ingest_payload_size:.1f}, throughput: {throughput:.1f} msg/s")
    
    # Data quality issues (only when there are problems)
    issues = []
    if self_monitoring.too_old_records > 0:
        issues.append(f"too_old={self_monitoring.too_old_records}")
    if self_monitoring.publish_time_fallback_records > 0:
        issues.append(f"missing_ts={self_monitoring.publish_time_fallback_records}")
    if self_monitoring.parsing_errors > 0:
        issues.append(f"parse_err={self_monitoring.parsing_errors}")
    if self_monitoring.records_with_too_long_content > 0:
        issues.append(f"too_long={self_monitoring.records_with_too_long_content}")
    if issues:
        logging_context.log("SFM", f"Data issues: {', '.join(issues)}")
    
    # Bottleneck indicators (only when there's potential backpressure)
    if self_monitoring.push_queue_size_max > 0 or self_monitoring.push_wait_time > 0.1:
        logging_context.log("SFM", f"Push throttle: waiting={self_monitoring.push_queue_size_max}, wait_time={self_monitoring.push_wait_time:.3f}s")


def create_time_series(
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
            create_time_series(
                context,
                LOG_SELF_MONITORING_ALL_REQUESTS_METRIC_TYPE,
                {
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "logs_subscription_id": context.logs_subscription_id,
                    "container_name": context.container_name,
                    "worker_pid": context.worker_pid
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.all_requests}
                }]))

    if sfm.too_old_records:
        time_series.append(
            create_time_series(
                context,
                LOG_SELF_MONITORING_TOO_OLD_RECORDS_METRIC_TYPE,
                {
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "logs_subscription_id": context.logs_subscription_id,
                    "container_name": context.container_name,
                    "worker_pid": context.worker_pid
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.too_old_records}
                }]))

    if sfm.parsing_errors:
        time_series.append(
            create_time_series(
                context,
                LOG_SELF_MONITORING_PARSING_ERRORS_METRIC_TYPE,
                {
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "logs_subscription_id": context.logs_subscription_id,
                    "container_name": context.container_name,
                    "worker_pid": context.worker_pid
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.parsing_errors}
                }]))

    if sfm.records_with_too_long_content:
        time_series.append(
            create_time_series(
                context,
                LOG_SELF_MONITORING_TOO_LONG_CONTENT_METRIC_TYPE,
                {
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "logs_subscription_id": context.logs_subscription_id,
                    "container_name": context.container_name,
                    "worker_pid": context.worker_pid
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.records_with_too_long_content}
                }]))

    if sfm.publish_time_fallback_records:
        time_series.append(
            create_time_series(
                context,
                LOG_SELF_MONITORING_PUBLISH_TIME_FALLBACK_METRIC_TYPE,
                {
                    "dynatrace_tenant_url": context.dynatrace_url,
                    "logs_subscription_id": context.logs_subscription_id,
                    "container_name": context.container_name,
                    "worker_pid": context.worker_pid
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.publish_time_fallback_records}
                }]))

    time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"doubleValue": sfm.processing_time}
            }],
            "DOUBLE"))

    time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_SENDING_TIME_SIZE_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"doubleValue": sfm.sending_time}
            }],
            "DOUBLE"))
    time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_PULLING_TIME_SIZE_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"doubleValue": sfm.pulling_time}
            }],
            "DOUBLE"))

    connectivity_counter = Counter(sfm.dt_connectivity)
    for http_status, counter in connectivity_counter.items():
        # Report all non-200 status codes as connectivity issues (0 = network error)
        if http_status != 200:
            time_series.append(create_time_series(
                    context,
                    LOG_SELF_MONITORING_CONNECTIVITY_METRIC_TYPE,
                    {
                        "dynatrace_tenant_url": context.dynatrace_url,
                        "logs_subscription_id": context.logs_subscription_id,
                        "container_name": context.container_name,
                        "worker_pid": context.worker_pid,
                        "connectivity_status": str(http_status)  # HTTP status code as string
                    },
                    [{
                        "interval": interval,
                        "value": {"int64Value": counter}
                    }]))

    if sfm.log_ingest_payload_size:
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_LOG_INGEST_PAYLOAD_SIZE_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"doubleValue": sfm.log_ingest_payload_size}
            }],
            "DOUBLE"
        ))
    if sfm.log_ingest_raw_size:
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_RAW_LOG_INGEST_PAYLOAD_SIZE_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"doubleValue": sfm.log_ingest_raw_size}
            }],
            "DOUBLE"
        ))

    if sfm.pulled_logs_entries:
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_PULLED_LOGS_ENTRIES_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"int64Value": sfm.pulled_logs_entries}
            }]
        ))

    if sfm.sent_logs_entries:
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_SENT_LOGS_ENTRIES_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"int64Value": sfm.sent_logs_entries}
            }]
        ))


    if sfm.acks_succeeded:
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_ACK_SUCCEEDED_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [
                {
                    "interval": interval,
                    "value": {"int64Value": sfm.acks_succeeded}
                }
            ]
        ))

    if sfm.ack_backlog:
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_ACK_BACKLOG_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [
                {
                    "interval": interval,
                    "value": {"int64Value": sfm.ack_backlog}
                }
            ]
        ))

    if sfm.ack_failures:
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_ACK_FAILURES_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"int64Value": sfm.ack_failures}
            }]
        ))

    # Bottleneck detection metrics
    if sfm.push_queue_size_max:
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_PUSH_QUEUE_SIZE_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"int64Value": sfm.push_queue_size_max}
            }]
        ))

    if sfm.push_wait_time:
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_PUSH_WAIT_TIME_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"doubleValue": sfm.push_wait_time}
            }],
            "DOUBLE"
        ))

    if sfm.messages_per_second:
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_MESSAGES_PER_SECOND_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"doubleValue": sfm.messages_per_second}
            }],
            "DOUBLE"
        ))

    if sfm.batch_latency_count > 0:
        avg_batch_latency = sfm.batch_latency_total / sfm.batch_latency_count
        time_series.append(create_time_series(
            context,
            LOG_SELF_MONITORING_BATCH_LATENCY_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id,
                "container_name": context.container_name,
                "worker_pid": context.worker_pid
            },
            [{
                "interval": interval,
                "value": {"doubleValue": avg_batch_latency}
            }],
            "DOUBLE"
        ))

    return {"timeSeries": time_series}


