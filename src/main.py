#     Copyright 2023 Dynatrace LLC
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
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Iterable
from aiohttp import ClientSession


from lib.clientsession_provider import init_dt_client_session, init_gcp_client_session
from lib.configuration import config
from lib.context import MetricsContext, LoggingContext, get_query_interval_minutes
from lib.credentials import create_token, fetch_dynatrace_api_key, fetch_dynatrace_url, \
    get_all_accessible_projects
from lib.entities.model import Entity
from lib.fast_check import check_dynatrace, check_version
from lib.gcp_apis import get_disabled_projects_and_disabled_apis_by_project_id
from lib.metric_ingest import fetch_metric, push_ingest_lines, flatten_and_enrich_metric_results
from lib.metrics import GCPService, MetadataIngestLine, Metric, IngestLine
from lib.self_monitoring import log_self_monitoring_metrics, sfm_push_metrics, sfm_create_descriptors_if_missing
from lib.sfm.for_metrics.metrics_definitions import SfmKeys
from lib.topology.topology import fetch_topology, build_entity_id_map
from lib.sfm.api_call_latency import ApiCallLatency


async def async_dynatrace_gcp_extension(services: Optional[List[GCPService]] = None):
    """
    Starting point for metrics monitoring main loop.
    """
    timestamp_utc = datetime.utcnow()
    timestamp_utc_iso = timestamp_utc.isoformat()
    execution_identifier = hashlib.md5(timestamp_utc_iso.encode("UTF-8")).hexdigest()
    logging_context = LoggingContext(execution_identifier)
    logging_context.log(f"GCP Monitor - Release version: {config.release_tag()}")
    logging_context.log("Starting execution")

    start_time = time.time()
    await query_metrics(execution_identifier, services)
    elapsed_time = time.time() - start_time
    logging_context.log(f"Execution took {elapsed_time}")


async def get_metric_context(
    gcp_session: ClientSession,
    dt_session: ClientSession,
    token: str,
    logging_context: LoggingContext,
) -> MetricsContext:
    project_id_owner = config.project_id()

    dynatrace_api_key = await fetch_dynatrace_api_key(
        gcp_session=gcp_session, project_id=project_id_owner, token=token
    )
    dynatrace_url = await fetch_dynatrace_url(
        gcp_session=gcp_session, project_id=project_id_owner, token=token
    )
    check_version(logging_context=logging_context)
    await check_dynatrace(
        logging_context=logging_context,
        project_id=project_id_owner,
        dt_session=dt_session,
        dynatrace_url=dynatrace_url,
        dynatrace_access_key=dynatrace_api_key,
    )

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
        scheduled_execution_id=logging_context.scheduled_execution_id,
    )

    return context

async def query_metrics(execution_id: Optional[str], services: Optional[List[GCPService]] = None):
    logging_context = LoggingContext(execution_id)

    async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
        setup_start_time = time.time()
        token = await create_token(logging_context, gcp_session)

        if token is None:
            logging_context.log("Cannot proceed without authorization token, stopping the execution")
            return
        if not isinstance(token, str):
            raise Exception(f"Failed to fetch access token, got non string value: {token}")

        logging_context.log("Successfully obtained access token")

        context = await get_metric_context(
            gcp_session, dt_session, token, logging_context=logging_context
        )

        projects_ids = await get_all_accessible_projects(context, gcp_session, token)

        disabled_projects = set()
        disabled_projects_by_prefix = set()
        disabled_apis_by_project_id = {}

        # Using metrics scope feature, checking disabled apis in every project is not needed
        if not config.scoping_project_support_enabled():
            disabled_projects, disabled_apis_by_project_id = \
                await get_disabled_projects_and_disabled_apis_by_project_id(context, projects_ids)
        
        disabled_projects.update(filter(None, config.excluded_projects().split(',')))
        disabled_projects_by_prefix.update(filter(None, config.excluded_projects_by_prefix().split(',')))

        if disabled_projects_by_prefix:
            for p in disabled_projects_by_prefix:
                not_matching = [s for s in projects_ids if p not in s]
                projects_ids = not_matching
            context.log("Disabled projects: " + ", ".join(disabled_projects_by_prefix))

        if disabled_projects:
            projects_ids = [x for x in projects_ids if x not in disabled_projects]
            context.log("Disabled projects: " + ", ".join(disabled_projects))
            

        setup_time = (time.time() - setup_start_time)
        for project_id in projects_ids:
            context.sfm[SfmKeys.setup_execution_time].update(project_id, setup_time)

        context.start_processing_timestamp = time.time()

        excluded_metrics = config.excluded_metrics().split(',')
        process_project_metrics_tasks = [
            process_project_metrics(context, project_id, services, disabled_apis_by_project_id.get(project_id, set()), excluded_metrics)
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
                                  disabled_apis: Set[str], excluded_metrics: List[str]):
    try:
        context.log(project_id, f"Starting processing...")
        ingest_lines = await fetch_ingest_lines_task(context, project_id, services, disabled_apis, excluded_metrics)
        fetch_data_time = time.time() - context.start_processing_timestamp
        context.sfm[SfmKeys.fetch_gcp_data_execution_time].update(project_id, fetch_data_time)
        context.log(project_id, f"Finished fetching data in {fetch_data_time}")
        await push_ingest_lines(context, project_id, ingest_lines)
    except Exception as e:
        context.t_exception(f"Failed to finish processing due to {e}")


async def fetch_ingest_lines_task(context: MetricsContext, project_id: str, services: List[GCPService],
                                  disabled_apis: Set[str], excluded_metrics: List[str]) -> List[IngestLine]:
    fetch_metric_coros = []
    metrics_metadata = []
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
    skipped_excluded_metrics = []

    for service in services:
        if not service.is_enabled:
            continue  # skip disabled services
        if service in topology and not topology[service]:
            skipped_services_with_no_instances.append(f"{service.name}/{service.feature_set}")
            continue  # skip fetching the metrics because there are no instances

        for metric in service.metrics:
            if metric.name in excluded_metrics:
                skipped_excluded_metrics.append(metric.name)
                continue

            # Fetch metric only if it's metric from extensions or is autodiscovered in project_id
            if not metric.autodiscovered_metric or project_id in metric.project_ids:
                gcp_api_last_index = metric.google_metric.find("/")
                api = metric.google_metric[:gcp_api_last_index]
                if api in disabled_apis:
                    skipped_disabled_apis.add(api)
                    continue  # skip fetching the metrics because service API is disabled
                fetch_metric_coro = run_fetch_metric(
                    context=context, project_id=project_id, service=service, metric=metric
                )
                fetch_metric_coros.append(fetch_metric_coro)

    context.log(f"Prepared {len(fetch_metric_coros)} fetch metric tasks")

    if skipped_services_with_no_instances:
        skipped_services_string = ', '.join(skipped_services_with_no_instances)
        context.log(project_id, f"Skipped fetching metrics for {skipped_services_string} due to no instances detected")
    if skipped_disabled_apis:
        skipped_disabled_apis_string = ", ".join(skipped_disabled_apis)
        context.log(project_id, f"Skipped fetching metrics for disabled APIs: {skipped_disabled_apis_string}")

    if skipped_excluded_metrics:
        context.log(project_id, f"Skipped fetching for excluded metrics: {", ".join(skipped_excluded_metrics)}")

    fetch_metric_results = await asyncio.gather(*fetch_metric_coros, return_exceptions=True)
    entity_id_map = build_entity_id_map(list(topology.values()))
    flat_metric_results = flatten_and_enrich_metric_results(context, fetch_metric_results, entity_id_map)

    flat_metric_results.extend(metrics_metadata)
    return flat_metric_results


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
