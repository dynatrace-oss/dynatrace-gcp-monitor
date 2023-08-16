import asyncio
import os
import time
from dataclasses import asdict
from itertools import chain
from typing import Dict, List, NamedTuple

from aiohttp import ClientSession
from lib.autodiscovery.gcp_metrics_descriptor import GCPMetricDescriptor
from lib.clientsession_provider import init_dt_client_session, init_gcp_client_session
from lib.configuration import config
from lib.context import LoggingContext, MetricsContext
from lib.credentials import create_token, get_all_accessible_projects
from lib.gcp_apis import get_disabled_projects_and_disabled_apis_by_project_id
from lib.metric_ingest import push_ingest_lines
from lib.metrics import GCPService, MetadataIngestLine, Metric
from main import get_metric_context

logging_context = LoggingContext("AUTODISCOVERY")


discovered_resource_type = os.environ.get("AUTODISCOVERY_RESOURCE_TYPE", "gce_instance")

FetchMetricDescriptorsResult = NamedTuple(
    "FetchMetricDescriptorsResult",
    [("project_id", str), ("metric_descriptor", GCPMetricDescriptor)],
)


async def get_project_ids(
    metric_context: MetricsContext,
    gcp_session: ClientSession,
    token: str,
) -> List[str]:
    projects_ids = await get_all_accessible_projects(metric_context, gcp_session, token)
    disabled_projects = []

    if not config.scoping_project_support_enabled():
        disabled_project, _ = await get_disabled_projects_and_disabled_apis_by_project_id(
            metric_context, projects_ids
        )

    if disabled_projects:
        for disabled_project in disabled_projects:
            projects_ids.remove(disabled_project)

    return projects_ids


async def run_fetch_metric_descriptors(
    gcp_session: ClientSession, token: str, project_id: str
) -> List[FetchMetricDescriptorsResult]:
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    url = f"https://monitoring.googleapis.com/v3/projects/{project_id}/metricDescriptors"
    params = {}

    project_discovered_metrics = []
    while True:
        response = await gcp_session.request("GET", url=url, headers=headers, params=params)
        response.raise_for_status()
        response_json = await response.json()

        for descriptor in response_json.get("metricDescriptors", []):
            try:
                metric_descriptor = GCPMetricDescriptor.create(**descriptor, project_id=project_id)
                if (
                    metric_descriptor.gcpOptions.valueType.upper() != "STRING"
                    and discovered_resource_type in metric_descriptor.monitored_resources_types
                ):
                    project_discovered_metrics.append(metric_descriptor)
            except Exception as error:
                logging_context.log(
                    f"Failed to load autodiscovered metric for project: {project_id}. Details: {error}"
                )

        page_token = response_json.get("nextPageToken", "")
        params["pageToken"] = page_token
        if page_token == "":
            break
    return [
        FetchMetricDescriptorsResult(project_id, metric_descriptor)
        for metric_descriptor in project_discovered_metrics
    ]


async def send_metric_metadata(metrics: List[Metric], context: MetricsContext):
    metrics_metadata = []
    for metric in metrics:
        metrics_metadata.append(
            MetadataIngestLine(
                metric_name=metric.dynatrace_name,
                metric_type=metric.dynatrace_metric_type,
                metric_display_name=metric.name,
                metric_description=metric.description,
                metric_unit=metric.unit,
            )
        )
    await push_ingest_lines(context, "autodiscovery-metadata", metrics_metadata)


async def get_metric_descriptors(
    metric_context: MetricsContext, gcp_session: ClientSession, token: str
) -> Dict[GCPMetricDescriptor, List[str]]:
    project_ids = await get_project_ids(metric_context, gcp_session, token)

    metric_fetch_coroutines = []
    metric_per_project = {}
    for project_id in project_ids:
        metric_fetch_coroutines.append(run_fetch_metric_descriptors(gcp_session, token, project_id))

    fetch_metrics_descriptor_results = await asyncio.gather(
        *metric_fetch_coroutines, return_exceptions=True
    )
    flattened_results = list(chain.from_iterable(fetch_metrics_descriptor_results))
    
    for fetch_reslut in flattened_results:
        metric_per_project.setdefault(fetch_reslut.metric_descriptor, []).append(
            fetch_reslut.project_id
        )

    return metric_per_project


async def run_autodiscovery(
    gcp_services_list: List[GCPService],
    gcp_session: ClientSession,
    dt_session: ClientSession,
    token: str,
):
    start_time = time.time()
    logging_context.log("Adding metrics using autodiscovery")
    metric_context = await get_metric_context(gcp_session, dt_session, token, logging_context)

    filtered_gcp_extension_services = list(
        filter(lambda x: discovered_resource_type in x.name, gcp_services_list)
    )

    existing_metric_list = []
    for service in filtered_gcp_extension_services:
        existing_metric_list.extend(service.metrics)

    discovered_metric_descriptors = await get_metric_descriptors(metric_context, gcp_session, token)

    existing_metric_names = {}
    for existing_metric in existing_metric_list:
        existing_metric_names[existing_metric.google_metric] = None

    missing_metrics_list = []

    for descriptor, project_ids in discovered_metric_descriptors.items():
        if descriptor.value not in existing_metric_names:
            metric_fields = asdict(descriptor)
            metric_fields["autodiscovered_metric"] = True
            autodiscovered_metric = Metric(**(metric_fields), project_ids=project_ids)
            missing_metrics_list.append(autodiscovered_metric)

    logging_context.log(f"In the extension there are {len(existing_metric_list)} metrics")
    logging_context.log(
        f"Discovered Resource type {discovered_resource_type} has {len(discovered_metric_descriptors)} metrics"
    )
    logging_context.log(f"Adding {len(missing_metrics_list)} metrics")
    logging_context.log(
        f"Adding metrics: {[metric.google_metric for metric in missing_metrics_list]}"
    )
    await send_metric_metadata(missing_metrics_list, metric_context)

    for service in gcp_services_list:
        if service.name == discovered_resource_type and service.feature_set == "default_metrics":
            service.metrics.extend([metric for metric in missing_metrics_list])

    end_time = time.time()

    logging_context.log(f"Elapsed time in autodiscovery: {end_time-start_time} s")
    return gcp_services_list


async def enrich_services_with_autodiscovery_metrics(
    current_services: List[GCPService],
) -> List[GCPService]:
    try:
        async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
            token = await create_token(logging_context, gcp_session)
            if not token:
                raise Exception("Failed to fetch token")

            autodiscovery_fetch_result = await run_autodiscovery(
                current_services, gcp_session, dt_session, token
            )

            return autodiscovery_fetch_result
    except Exception as e:
        logging_context.error(
            f"Failed to prepare autodiscovery new services metrics, will reuse from configuration file; {str(e)}"
        )
        return current_services
