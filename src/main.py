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
from typing import Dict, List, Optional, Set, Iterable

import yaml

from lib.clientsession_provider import init_dt_client_session, init_gcp_client_session
from lib.configuration import config
from lib.context import MetricsContext, LoggingContext, get_query_interval_minutes
from lib.credentials import create_token, get_project_id_from_environment, fetch_dynatrace_api_key, fetch_dynatrace_url, \
    get_all_accessible_projects
from lib.entities.model import Entity
from lib.fast_check import check_dynatrace, check_version
from lib.gcp_apis import get_disabled_projects_and_disabled_apis_by_project_id
from lib.metric_ingest import fetch_metric, push_ingest_lines, flatten_and_enrich_metric_results
from lib.metrics import GCPService, Metric, IngestLine
from lib.self_monitoring import log_self_monitoring_metrics, sfm_push_metrics, sfm_create_descriptors_if_missing
from lib.sfm.for_metrics.metrics_definitions import SfmKeys
from lib.topology.topology import fetch_topology, build_entity_id_map
from lib.utilities import read_activation_yaml, get_activation_config_per_service, load_activated_feature_sets, \
    is_yaml_file, extract_technology_name
from lib.sfm.api_call_latency import ApiCallLatency


def dynatrace_gcp_extension(event, context):
    """
    Starting point for installation as a GCP function.
    See https://cloud.google.com/functions/docs/calling/pubsub#event_structure
    """
    try:
        asyncio.run(query_metrics(None, None))
    except Exception as e:
        traceback.print_exc()
        raise e


async def async_dynatrace_gcp_extension(services: Optional[List[GCPService]] = None):
    """
    Starting point for installation as a cluster and for tests.
    """
    timestamp_utc = datetime.utcnow()
    timestamp_utc_iso = timestamp_utc.isoformat()
    execution_identifier = hashlib.md5(timestamp_utc_iso.encode("UTF-8")).hexdigest()
    logging_context = LoggingContext(execution_identifier)
    logging_context.log("Starting execution")

    start_time = time.time()
    await query_metrics(execution_identifier, services)
    elapsed_time = time.time() - start_time
    logging_context.log(f"Execution took {elapsed_time}")


async def query_metrics(execution_id: Optional[str], services: Optional[List[GCPService]] = None):
    context = LoggingContext(execution_id)
    if not services:
        # Load services for GCP Function
        services = load_supported_services(context)

    async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
        setup_start_time = time.time()
        token = await create_token(context, gcp_session)

        if token is None:
            context.log("Cannot proceed without authorization token, stopping the execution")
            return
        if not isinstance(token, str):
            raise Exception(f"Failed to fetch access token, got non string value: {token}")

        context.log("Successfully obtained access token")

        project_id_owner = get_project_id_from_environment()

        dynatrace_api_key = await fetch_dynatrace_api_key(gcp_session=gcp_session, project_id=project_id_owner, token=token)
        dynatrace_url = await fetch_dynatrace_url(gcp_session=gcp_session, project_id=project_id_owner, token=token)
        check_version(logging_context=context)
        await check_dynatrace(logging_context=context,
                              project_id=project_id_owner,
                              dt_session=dt_session,
                              dynatrace_url=dynatrace_url,
                              dynatrace_access_key=dynatrace_api_key)

        query_interval_min = get_query_interval_minutes()

        context = MetricsContext(
            gcp_session=gcp_session,
            dt_session=dt_session,
            project_id_owner=project_id_owner,
            token=token,
            execution_time=datetime.utcnow(),
            execution_interval_seconds=60 * query_interval_min,
            dynatrace_api_key=dynatrace_api_key,
            dynatrace_url=dynatrace_url,
            print_metric_ingest_input=config.print_metric_ingest_input(),
            self_monitoring_enabled=config.self_monitoring_enabled(),
            scheduled_execution_id=context.scheduled_execution_id
        )

        projects_ids = await get_all_accessible_projects(context, gcp_session, token)

        disabled_projects = []
        disabled_apis_by_project_id = {}

        # Using metrics scope feature, checking disabled apis in every project is not needed
        if not config.scoping_project_support_enabled():
            disabled_projects, disabled_apis_by_project_id = \
                await get_disabled_projects_and_disabled_apis_by_project_id(context, projects_ids)

        if disabled_projects:
            for disabled_project in disabled_projects:
                projects_ids.remove(disabled_project)

        setup_time = (time.time() - setup_start_time)
        for project_id in projects_ids:
            context.sfm[SfmKeys.setup_execution_time].update(project_id, setup_time)

        context.start_processing_timestamp = time.time()

        process_project_metrics_tasks = [
            process_project_metrics(context, project_id, services, disabled_apis_by_project_id.get(project_id, set()))
            for project_id
            in projects_ids
        ]
        await asyncio.gather(*process_project_metrics_tasks, return_exceptions=True)
        context.log(f"Fetched and pushed GCP data in {time.time() - context.start_processing_timestamp} s")

        log_self_monitoring_metrics(context)
        if context.self_monitoring_enabled:
            context.log("Self monitoring update to GCP Monitoring")
            await sfm_create_descriptors_if_missing(context)
            await sfm_push_metrics(context.sfm.values(), context, context.execution_time)
        else:
            context.log("SFM disabled, will not push SFM metrics")
        ApiCallLatency.print_statistics(context)
        await gcp_session.close()
        await dt_session.close()

    # Noise on Windows at the end of the logs is caused by https://github.com/aio-libs/aiohttp/issues/4324


async def process_project_metrics(context: MetricsContext, project_id: str, services: List[GCPService],
                                  disabled_apis: Set[str]):
    try:
        context.log(project_id, f"Starting processing...")
        ingest_lines = await fetch_ingest_lines_task(context, project_id, services, disabled_apis)
        fetch_data_time = time.time() - context.start_processing_timestamp
        context.sfm[SfmKeys.fetch_gcp_data_execution_time].update(project_id, fetch_data_time)
        context.log(project_id, f"Finished fetching data in {fetch_data_time}")
        await push_ingest_lines(context, project_id, ingest_lines)
    except Exception as e:
        context.t_exception(f"Failed to finish processing due to {e}")


async def fetch_ingest_lines_task(context: MetricsContext, project_id: str, services: List[GCPService],
                                  disabled_apis: Set[str]) -> List[IngestLine]:
    fetch_metric_coros = []
    topology: Dict[GCPService, Iterable[Entity]] = {}

    # Topology fetching: retrieving additional instances info about enabled services
    # Using metrics scope feature, fetching topology is not needed,
    # because we can't fetch details from instances in other projects
    if not config.scoping_project_support_enabled():
        topology = await fetch_topology(context, project_id, services, disabled_apis)

    # Using metrics scope feature, topology and disabled_apis will be empty, so no filtering is applied
    # and metrics from all projects are being collected
    skipped_services_with_no_instances = []
    skipped_disabled_apis = set()

    for service in services:
        if service in topology and not topology[service]:
            skipped_services_with_no_instances.append(f"{service.name}/{service.feature_set}")
            continue  # skip fetching the metrics because there are no instances
        for metric in service.metrics:
            gcp_api_last_index = metric.google_metric.find("/")
            api = metric.google_metric[:gcp_api_last_index]
            if api in disabled_apis:
                skipped_disabled_apis.add(api)
                continue  # skip fetching the metrics because service API is disabled
            fetch_metric_coro = run_fetch_metric(
                context=context,
                project_id=project_id,
                service=service,
                metric=metric
            )
            fetch_metric_coros.append(fetch_metric_coro)

    context.log(f"Prepared {len(fetch_metric_coros)} fetch metric tasks")

    if skipped_services_with_no_instances:
        skipped_services_string = ', '.join(skipped_services_with_no_instances)
        context.log(project_id, f"Skipped fetching metrics for {skipped_services_string} due to no instances detected")
    if skipped_disabled_apis:
        skipped_disabled_apis_string = ", ".join(skipped_disabled_apis)
        context.log(project_id, f"Skipped fetching metrics for disabled APIs: {skipped_disabled_apis_string}")

    fetch_metric_results = await asyncio.gather(*fetch_metric_coros, return_exceptions=True)
    entity_id_map = build_entity_id_map(list(topology.values()))
    flat_metric_results = flatten_and_enrich_metric_results(context, fetch_metric_results, entity_id_map)
    return flat_metric_results


def load_supported_services(context: LoggingContext) -> List[GCPService]:
    activation_yaml = read_activation_yaml()
    activation_config_per_service = get_activation_config_per_service(activation_yaml)
    feature_sets_from_activation_config = load_activated_feature_sets(context, activation_yaml)

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
                    service_name = service_yaml.get("service", "None")
                    feature_set = service_yaml.get("featureSet", "default_metrics")
                    # If whitelist of services exists and current service is not present in it, skip
                    # If whitelist is empty - no services explicitly selected - load all available
                    whitelist_exists = feature_sets_from_activation_config.__len__() > 0
                    if f'{service_name}/{feature_set}' in feature_sets_from_activation_config or not whitelist_exists:
                        activation = activation_config_per_service.get(service_name, {})
                        services.append(GCPService(tech_name=technology_name, **service_yaml, activation=activation))

        except Exception as error:
            context.log(f"Failed to load configuration file: '{config_file_path}'. Error details: {error}")
            continue
    feature_sets = [f"{service.name}/{service.feature_set}" for service in services]
    if feature_sets:
        context.log("Selected feature sets: " + ", ".join(feature_sets))
    else:
        context.log("Empty feature sets. GCP services not monitored.")
    return services


async def run_fetch_metric(
        context: MetricsContext,
        project_id: str,
        service: GCPService,
        metric: Metric
):
    try:
        return await fetch_metric(context, project_id, service, metric)
    except Exception as e:
        context.log(project_id, f"Failed to finish task for [{metric.google_metric}], reason is {type(e).__name__} {e}")
        return []
