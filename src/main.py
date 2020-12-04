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
import hashlib
import os
import time
import traceback
from datetime import datetime
from os import listdir
from os.path import isfile
from typing import Dict, List, Optional

import aiohttp
import yaml

from lib.context import Context, LoggingContext
from lib.credentials import create_token, get_project_id_from_environment, fetch_dynatrace_api_key, fetch_dynatrace_url, \
    get_all_accessible_projects
from lib.entities import entities_extractors
from lib.entities.model import Entity
from lib.metric_ingest import fetch_metric, push_ingest_lines, flatten_and_enrich_metric_results
from lib.metrics import GCPService, Metric, IngestLine
from lib.self_monitoring import push_self_monitoring_time_series


def dynatrace_gcp_extension(event, context, project_id: Optional[str] = None):
    try:
        asyncio.run(handle_event(event, context, project_id))
    except Exception as e:
        traceback.print_exc()
        raise e


async def async_dynatrace_gcp_extension(project_ids: Optional[List[str]] = None):
    timestamp_utc = datetime.utcnow()
    timestamp_utc_iso = timestamp_utc.isoformat()
    execution_identifier = hashlib.md5(timestamp_utc_iso.encode("UTF-8")).hexdigest()
    logging_context = LoggingContext(execution_identifier)
    logging_context.log(f'Starting execution for project(s): {project_ids}' if project_ids else "Starting execution")
    event_context = {
        'timestamp': timestamp_utc_iso,
        'event_id': timestamp_utc.timestamp(),
        'event_type': 'test',
        'execution_id': execution_identifier
    }
    data = {'data': '', 'publishTime': timestamp_utc_iso}

    start_time = time.time()
    await handle_event(data, event_context, "dynatrace-gcp-extension", project_ids)
    elapsed_time = time.time() - start_time
    logging_context.log(f"Execution took {elapsed_time}\n")


def is_yaml_file(f: str) -> bool:
    return f.endswith(".yml") or f.endswith(".yaml")


async def handle_event(event: Dict, event_context, project_id_owner: Optional[str], projects_ids: Optional[List[str]] = None):
    if isinstance(event_context, Dict):
        context = LoggingContext(event_context.get("execution_id", None))
    else:
        context = LoggingContext(None)

    selected_services = None
    if "GCP_SERVICES" in os.environ:
        selected_services_string = os.environ.get("GCP_SERVICES", "")
        selected_services = selected_services_string.split(",") if selected_services_string else []
    services = load_supported_services(context, selected_services)

    async with aiohttp.ClientSession() as session:
        setup_start_time = time.time()
        token = await create_token(context, session)

        if token is None:
            context.log("Cannot proceed without authorization token, stopping the execution")
            return
        if not isinstance(token, str):
            raise Exception(f"Failed to fetch access token, got non string value: {token}")

        context.log("Successfully obtained access token")

        if not project_id_owner:
            project_id_owner = get_project_id_from_environment()

        dynatrace_api_key = await fetch_dynatrace_api_key(session=session, project_id=project_id_owner, token=token)
        dynatrace_url = await fetch_dynatrace_url(session=session, project_id=project_id_owner, token=token)

        print_metric_ingest_input = \
            "PRINT_METRIC_INGEST_INPUT" in os.environ and os.environ["PRINT_METRIC_INGEST_INPUT"].upper() == "TRUE"

        context = Context(
            session=session,
            project_id_owner=project_id_owner,
            token=token,
            execution_time=datetime.utcnow(),
            execution_interval_seconds=60 * 1,
            dynatrace_api_key=dynatrace_api_key,
            dynatrace_url=dynatrace_url,
            print_metric_ingest_input=print_metric_ingest_input,
            scheduled_execution_id=context.scheduled_execution_id
        )

        if not projects_ids:
            projects_ids = await get_all_accessible_projects(context, session, token)

        setup_time = (time.time() - setup_start_time)
        context.setup_execution_time = {project_id: setup_time for project_id in projects_ids}

        context.start_processing_timestamp = time.time()

        process_project_metrics_tasks = [
            process_project_metrics(context, project_id, services)
            for project_id
            in projects_ids
        ]
        await asyncio.gather(*process_project_metrics_tasks, return_exceptions=True)
        context.log(f"Fetched and pushed GCP data in {time.time() - context.start_processing_timestamp} s")
        context.log(f"Processed {sum(context.dynatrace_ingest_lines_ok_count.values())} lines")

        await push_self_monitoring_time_series(context)

        await session.close()

    # Noise on windows at the end of the logs is caused by https://github.com/aio-libs/aiohttp/issues/4324


async def process_project_metrics(context: Context, project_id: str, services: List[GCPService]):
    context.log(project_id, f"Starting processing...")
    ingest_lines = await fetch_ingest_lines_task(context, project_id, services)
    fetch_data_time = time.time() - context.start_processing_timestamp
    context.fetch_gcp_data_execution_time[project_id] = fetch_data_time
    context.log(project_id, f"Finished fetching data in {fetch_data_time}")
    await push_ingest_lines(context, project_id, ingest_lines)


async def fetch_ingest_lines_task(context: Context, project_id: str, services: List[GCPService]) -> List[IngestLine]:
    fetch_metric_tasks = []
    topology_tasks = []
    topology_task_services = []

    for service in services:
        if service.name in entities_extractors:
            topology_task = entities_extractors[service.name](context, project_id, service)
            topology_tasks.append(topology_task)
            topology_task_services.append(service)
    fetch_topology_results = await asyncio.gather(*topology_tasks, return_exceptions=True)

    skipped_services = []
    for service in services:
        if service in topology_task_services:
            service_topology = fetch_topology_results[topology_task_services.index(service)]
            if not service_topology:
                skipped_services.append(service.name)
                continue  # skip fetching the metrics because there are no instances
        for metric in service.metrics:
            fetch_metric_task = run_fetch_metric(
                context=context,
                project_id=project_id,
                service=service,
                metric=metric
            )
            fetch_metric_tasks.append(fetch_metric_task)

    if skipped_services:
        skipped_services_string = ', '.join(skipped_services)
        context.log(project_id, f"Skipped fetching metrics for {skipped_services_string} due to no instances detected")

    fetch_metric_results = await asyncio.gather(*fetch_metric_tasks, return_exceptions=True)
    entity_id_map = build_entity_id_map(fetch_topology_results)
    flat_metric_results = flatten_and_enrich_metric_results(fetch_metric_results, entity_id_map)
    return flat_metric_results


def build_entity_id_map(fetch_topology_results: List[List[Entity]]) -> Dict[str, Entity]:
    result = {}
    for result_set in fetch_topology_results:
        for entity in result_set:
            result[entity.id] = entity
    return result


def load_supported_services(context: LoggingContext, selected_services: List[str]) -> List[GCPService]:
    working_directory = os.path.dirname(os.path.realpath(__file__))
    config_directory = os.path.join(working_directory, "config")
    config_files = [
        file for file
        in listdir(config_directory)
        if isfile(os.path.join(config_directory, file)) and is_yaml_file(file)
    ]

    services = []
    for file in config_files:
        config_file_path = os.path.join(config_directory, file)
        try:
            with open(config_file_path, encoding="utf-8") as config_file:
                config_yaml = yaml.safe_load(config_file)
                technology_name = extract_technology_name(config_yaml)

                for service_yaml in config_yaml.get("gcp", {}):
                    # If whitelist of services exists and current service is not present in it, skip
                    should_skip = selected_services and \
                                  (service_yaml.get("service", "None") not in selected_services)
                    if should_skip:
                        continue
                    services.append(GCPService(tech_name=technology_name, **service_yaml))
        except Exception as error:
            context.log(f"Failed to load configuration file: '{config_file_path}'. Error details: {error}")
            continue
    services_names = [service.name for service in services]
    context.log("Selected services: " + ",".join(services_names))
    return services


def extract_technology_name(config_yaml):
    technology_name = config_yaml.get("technology", {})
    if isinstance(technology_name, Dict):
        technology_name = technology_name.get("name", "N/A")
    return technology_name


async def run_fetch_metric(
        context: Context,
        project_id: str,
        service: GCPService,
        metric: Metric
):
    try:
        return await fetch_metric(context, project_id, service, metric)
    except Exception as e:
        context.log(project_id, f"Failed to finish task for [{metric.google_metric}], reason is {type(e).__name__} {e}")
        return []
