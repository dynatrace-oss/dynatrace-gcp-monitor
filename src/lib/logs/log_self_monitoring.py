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
import json
import os
import queue
import time
import traceback
from collections import Counter
from queue import Queue
from typing import Dict, List

import aiohttp

from lib.context import LoggingContext, LogsSfmContext, DynatraceConnectivity
from lib.credentials import create_token, get_dynatrace_log_ingest_url_from_env
from lib.logs.log_forwarder_variables import SENDING_WORKER_EXECUTION_PERIOD_SECONDS, MAX_MESSAGES_PROCESSED
from lib.logs.log_sfm_metric_descriptor import LOG_SELF_MONITORING_METRIC_PREFIX, LOG_SELF_MONITORING_METRIC_MAP, \
    LOG_SELF_MONITORING_CONNECTIVITY_METRIC_TYPE, LOG_SELF_MONITORING_ALL_REQUESTS_METRIC_TYPE, \
    LOG_SELF_MONITORING_TOO_OLD_RECORDS_METRIC_TYPE, LOG_SELF_MONITORING_PARSING_ERRORS_METRIC_TYPE, \
    LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_TYPE, LOG_SELF_MONITORING_SENDING_TIME_SIZE_METRIC_TYPE, \
    LOG_SELF_MONITORING_TOO_LONG_CONTENT_METRIC_TYPE


class LogSelfMonitoring:
    def __init__(self):
        self.too_old_records: int = 0
        self.parsing_errors: int = 0
        self.records_with_too_long_content: int = 0
        self.all_requests: int = 0
        self.dynatrace_connectivity = []
        self.processing_time_start: float = 0
        self.processing_time: float = 0
        self.sending_time_start: float = 0
        self.sending_time: float = 0

    def calculate_processing_time(self):
        self.processing_time = (time.perf_counter() - self.processing_time_start)

    def calculate_sending_time(self):
        self.sending_time = (time.perf_counter() - self.sending_time_start)


def aggregate_self_monitoring_metrics(aggregated_sfm: LogSelfMonitoring, sfm_list: List[LogSelfMonitoring]):
    for sfm in sfm_list:
        aggregated_sfm.all_requests += sfm.all_requests
        aggregated_sfm.too_old_records += sfm.too_old_records
        aggregated_sfm.parsing_errors += sfm.parsing_errors
        aggregated_sfm.records_with_too_long_content += sfm.records_with_too_long_content
        aggregated_sfm.dynatrace_connectivity.extend(sfm.dynatrace_connectivity)
        aggregated_sfm.processing_time += sfm.processing_time
        aggregated_sfm.sending_time += sfm.sending_time
    return aggregated_sfm


def put_sfm_into_queue(sfm_queue: Queue, sfm: LogSelfMonitoring, logging_context: LoggingContext):
    try:
        sfm_queue.put(sfm, True, SENDING_WORKER_EXECUTION_PERIOD_SECONDS + 1)
    except Exception as exception:
        if isinstance(exception, queue.Full):
            logging_context.error("Failed to add self-monitoring metric to queue due to full sfm queue, rejecting the sfm")


async def create_sfm_worker_loop(sfm_queue: Queue, logging_context: LoggingContext):
    while True:
        await asyncio.sleep(SENDING_WORKER_EXECUTION_PERIOD_SECONDS)
        self_monitoring = LogSelfMonitoring()
        asyncio.get_event_loop().create_task(_loop_single_period(self_monitoring, sfm_queue, logging_context))


async def _loop_single_period(self_monitoring: LogSelfMonitoring, sfm_queue: Queue, context: LoggingContext):
    try:
        sfm_list = _pull_sfm(sfm_queue)
        if sfm_list:
            context = await _create_sfm_logs_context(sfm_queue, context)
            self_monitoring = aggregate_self_monitoring_metrics(self_monitoring, sfm_list)
            _log_self_monitoring_data(self_monitoring, context)
            if context.self_monitoring_enabled:
                await _push_log_self_monitoring_time_series(self_monitoring, context)
            for _ in sfm_list:
                sfm_queue.task_done()
    except Exception:
        print("Log SFM Loop Exception:")
        traceback.print_exc()


async def _create_sfm_logs_context(sfm_queue, context: LoggingContext):
    async with aiohttp.ClientSession() as gcp_session:
        dynatrace_url = get_dynatrace_log_ingest_url_from_env()
        logs_subscription_project = os.environ.get("LOGS_SUBSCRIPTION_PROJECT")
        logs_subscription_id = os.environ.get('LOGS_SUBSCRIPTION_ID', "")
        self_monitoring_enabled = os.environ.get('SELF_MONITORING_ENABLED', "False").upper() == "TRUE"
        token = await create_token(context, gcp_session)
        return LogsSfmContext(
            project_id_owner=logs_subscription_project,
            dynatrace_url=dynatrace_url,
            logs_subscription_id=logs_subscription_id,
            token=token,
            scheduled_execution_id=str(int(time.time()))[-8:],
            sfm_queue=sfm_queue,
            self_monitoring_enabled=self_monitoring_enabled
        )


def _pull_sfm(sfm_queue: Queue):
    sfm_list: List[LogSelfMonitoring] = []
    # Limit used to avoid pulling forever (the same as for job_queue)
    while len(sfm_list) < MAX_MESSAGES_PROCESSED and sfm_queue.qsize() > 0:
        single_sfm: LogSelfMonitoring = sfm_queue.get()
        sfm_list.append(single_sfm)
    return sfm_list


async def _push_log_self_monitoring_time_series(self_monitoring: LogSelfMonitoring, context: LogsSfmContext, is_retry: bool = False):
    if context.token is None:
        context.log("Cannot proceed without authorization token, failed to send ")
        return
    if not isinstance(context.token, str):
        context.log(f"Failed to fetch access token, got non string value: {context.token}")
        return

    try:
        context.log(f"Pushing self monitoring time series to GCP Monitor...")
        async with aiohttp.ClientSession() as gcp_session:
            await create_metric_descriptors_if_missing(context, gcp_session)
            time_series = create_self_monitoring_time_series(self_monitoring, context)
            self_monitoring_response = await gcp_session.request(
                "POST",
                url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/timeSeries",
                data=json.dumps(time_series),
                headers={"Authorization": "Bearer {token}".format(token=context.token)}
            )
            status = self_monitoring_response.status
            if status == 500 and not is_retry:
                context.log(
                    "GCP Monitor responded with 500 Internal Error, it may occur when metric descriptor is updated. Retrying after 5 seconds")
                await asyncio.sleep(5)
                await _push_log_self_monitoring_time_series(self_monitoring, context, True)
            elif status != 200:
                self_monitoring_response_json = await self_monitoring_response.json()
                context.log(
                    f"Failed to push self monitoring time series, error is: {status} => {self_monitoring_response_json}")
            else:
                context.log(f"Finished pushing self monitoring time series to GCP Monitor")
            self_monitoring_response.close()
    except Exception as e:
        context.log(f"Failed to push self monitoring time series, reason is {type(e).__name__} {e}")


def _log_self_monitoring_data(self_monitoring: LogSelfMonitoring, logging_context: LoggingContext):
    dynatrace_connectivity = Counter(self_monitoring.dynatrace_connectivity)
    dynatrace_connectivity = [f"{connectivity.name}:{count}" for connectivity, count in dynatrace_connectivity.items()]
    dynatrace_connectivity = ", ".join(dynatrace_connectivity)
    logging_context.log("SFM", f"Number of all log ingest requests sent to Dynatrace: {self_monitoring.all_requests}")
    logging_context.log("SFM", f"Dynatrace connectivity: {dynatrace_connectivity}")
    logging_context.log("SFM", f"Number of invalid log records due to too old timestamp: {self_monitoring.too_old_records}")
    logging_context.log("SFM", f"Number of errors occurred during parsing logs: {self_monitoring.parsing_errors}")
    logging_context.log("SFM", f"Number of records with too long content: {self_monitoring.records_with_too_long_content}")
    logging_context.log("SFM", f"Total logs processing time [s]: {self_monitoring.processing_time}")
    logging_context.log("SFM", f"Total logs sending time [s]: {self_monitoring.sending_time}")


async def create_metric_descriptors_if_missing(context: LogsSfmContext, gcp_session):
    try:
        dynatrace_metrics_descriptors = await gcp_session.request(
            'GET',
            url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/metricDescriptors",
            params=[('filter', f'metric.type = starts_with("{LOG_SELF_MONITORING_METRIC_PREFIX}")')],
            headers={"Authorization": f"Bearer {context.token}"}
        )
        dynatrace_metrics_descriptors_json = await dynatrace_metrics_descriptors.json()
        existing_metric_types = {metric.get("type", ""): metric for metric in dynatrace_metrics_descriptors_json.get("metricDescriptors", [])}
        for metric_type, metric_descriptor in LOG_SELF_MONITORING_METRIC_MAP.items():
            existing_metric_descriptor = existing_metric_types.get(metric_type, None)
            if existing_metric_descriptor:
                await replace_metric_descriptor_if_required(context,
                                                      existing_metric_descriptor,
                                                      metric_descriptor,
                                                      metric_type,
                                                      gcp_session)
            else:
                await create_metric_descriptor(context, metric_descriptor, metric_type, gcp_session)
    except Exception as e:
        context.log(f"Failed to create self monitoring metrics descriptors, reason is {type(e).__name__} {e}")


async def replace_metric_descriptor_if_required(context: LogsSfmContext,
                                                existing_metric_descriptor: Dict,
                                                metric_descriptor: Dict,
                                                metric_type: str,
                                                gcp_session):
    existing_label_keys = extract_label_keys(existing_metric_descriptor)
    descriptor_label_keys = extract_label_keys(metric_descriptor)
    if existing_label_keys != descriptor_label_keys:
        await delete_metric_descriptor(context, metric_type, gcp_session)
        await create_metric_descriptor(context, metric_descriptor, metric_type, gcp_session)


async def delete_metric_descriptor(context: LogsSfmContext, metric_type: str, gcp_session):
    context.log(f"Removing old descriptor for '{metric_type}'")
    response = await gcp_session.request(
        "DELETE",
        url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/metricDescriptors/{metric_type}",
        headers={"Authorization": f"Bearer {context.token}"}
    )
    if response.status != 200:
        response_body = await response.json()
        context.log(f"Failed to remove descriptor for '{metric_type}' due to '{response_body}'")


async def create_metric_descriptor(context: LogsSfmContext, metric_descriptor: Dict, metric_type: str, gcp_session):
    context.log(f"Creating missing metric descriptor for '{metric_type}'")
    response = await gcp_session.request(
        "POST",
        url=f"https://monitoring.googleapis.com/v3/projects/{context.project_id_owner}/metricDescriptors",
        data=json.dumps(metric_descriptor),
        headers={"Authorization": f"Bearer {context.token}"}
    )

    if response.status > 202:
        response_body = await response.json()
        context.log(f"Failed to create descriptor for '{metric_type}' due to '{response_body}'")


def extract_label_keys(metric_descriptor: Dict):
    return sorted([label.get("key", "") for label in metric_descriptor.get("labels", [])])


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
                "location": context.location,
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
                    "logs_subscription_id": context.logs_subscription_id
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
                    "logs_subscription_id": context.logs_subscription_id
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
                    "logs_subscription_id": context.logs_subscription_id
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
                    "logs_subscription_id": context.logs_subscription_id
                },
                [{
                    "interval": interval,
                    "value": {"int64Value": sfm.records_with_too_long_content}
                }]))

    time_series.append(create_time_serie(
            context,
            LOG_SELF_MONITORING_PROCESSING_TIME_METRIC_TYPE,
            {
                "dynatrace_tenant_url": context.dynatrace_url,
                "logs_subscription_id": context.logs_subscription_id
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
                "logs_subscription_id": context.logs_subscription_id
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
                        "connectivity_status": dynatrace_connectivity.name
                    },
                    [{
                        "interval": interval,
                        "value": {"int64Value": counter}
                    }]))

    return {"timeSeries": time_series}


