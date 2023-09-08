import asyncio
import os
import time
from dataclasses import asdict, dataclass
from itertools import chain
from typing import Any, Dict, List, NamedTuple, Set, Tuple

from aiohttp import ClientSession

from lib.autodiscovery.gcp_metrics_descriptor import GCPMetricDescriptor
from lib.clientsession_provider import init_dt_client_session, init_gcp_client_session
from lib.configuration import config
from lib.context import LoggingContext, MetricsContext
from lib.credentials import create_token, get_all_accessible_projects
from lib.gcp_apis import get_disabled_projects_and_disabled_apis_by_project_id
from lib.metric_ingest import push_ingest_lines
from lib.metrics import Dimension, GCPService, MetadataIngestLine, Metric
from main import get_metric_context

logging_context = LoggingContext("AUTODISCOVERY")


discovered_resource_type = os.environ.get("AUTODISCOVERY_RESOURCE_TYPE", "gce_instance")

FetchMetricDescriptorsResult = NamedTuple(
    "FetchMetricDescriptorsResult",
    [("project_id", str), ("metric_descriptor", GCPMetricDescriptor)],
)


AutodiscoveryResult = NamedTuple(
    "AutodiscoveryResult",
    [
        ("autodiscovered_resources_to_metrics", Dict[str, List[Metric]]),
        ("discovered_metric_list", Dict[str, Any]),
        ("resource_dimensions", Dict[str, List[Dimension]]),
    ],
)


label_mapping = {
    "project_id": "gcp.project.id",
    "region": "gcp.region",
    "location": "gcp.region",
    "zone": "gcp.region",
}


@dataclass(frozen=True)
class AutodiscoveryResourceLinking:
    possible_service_linking: List[GCPService]
    disabled_services_for_resource: List[GCPService]


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


async def fetch_resource_descriptors(
    gcp_session: ClientSession, token: str, project_id: str
) -> Dict[str, List[Dimension]]:
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    url = f"https://monitoring.googleapis.com/v3/projects/{project_id}/metricDescriptors"
    params = {}

    resource_dimensions = {}
    while True:
        response = await gcp_session.request("GET", url=url, headers=headers, params=params)
        response.raise_for_status()
        response_json = await response.json()

        for descriptor in response_json.get("metricDescriptors", []):
            type_key = descriptor["type"]
            dimensions = []

            if "labels" in descriptor:
                for label in descriptor["labels"]:
                    label_key = label.get("key","")
                    label_value = "label:resource.labels." + label_key
                    dimensions.append(Dimension(key=label_key, value=label_value))

                    if label_key in label_mapping:
                         dimensions.append(Dimension(key=label_mapping[label_key], value=label_value))

                resource_dimensions[type_key] = dimensions

        page_token = response_json.get("nextPageToken", "")
        params["pageToken"] = page_token
        if page_token == "":
            break

    return resource_dimensions


async def run_fetch_metric_descriptors(
    gcp_session: ClientSession, token: str, project_id: str, resources_to_autodiscovery: Set[str]
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
                    and len(metric_descriptor.monitored_resources_types) == 1
                    and metric_descriptor.monitored_resources_types[0] in resources_to_autodiscovery
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


async def send_metric_metadata(
    metrics: Dict[str, List[Metric]],
    context: MetricsContext,
    previously_discovered_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    metrics_metadata = []
    for resource_name, metric_list in metrics.items():
        for metric in metric_list:
            if metric.dynatrace_name not in previously_discovered_metrics:
                metrics_metadata.append(
                    MetadataIngestLine(
                        metric_name=metric.dynatrace_name,
                        metric_type=metric.dynatrace_metric_type,
                        metric_display_name=metric.name,
                        metric_description=metric.description,
                        metric_unit=metric.unit,
                    )
                )
                previously_discovered_metrics[metric.dynatrace_name] = None

    if len(metrics_metadata):
        logging_context.log(f"Adding {len(metrics_metadata)} new autodiscovered metrics metadata")
        await push_ingest_lines(context, "autodiscovery-metadata", metrics_metadata)
    return previously_discovered_metrics


async def get_metric_descriptors(
    metric_context: MetricsContext,
    gcp_session: ClientSession,
    token: str,
    autodiscovery_resources_to_services: Dict[str, AutodiscoveryResourceLinking],
) -> Tuple[Dict[GCPMetricDescriptor, List[str]], Dict[str, List[Dimension]]]:
    project_ids = await get_project_ids(metric_context, gcp_session, token)

    resources_to_autodiscovery = {
        resource for resource in autodiscovery_resources_to_services.keys()
    }
    metric_fetch_coroutines = []
    metric_per_project = {}
    for project_id in project_ids:
        metric_fetch_coroutines.append(
            run_fetch_metric_descriptors(gcp_session, token, project_id, resources_to_autodiscovery)
        )

    resource_labels = await fetch_resource_descriptors(gcp_session, token, project_ids[0])

    fetch_metrics_descriptor_results = await asyncio.gather(
        *metric_fetch_coroutines, return_exceptions=True
    )
    flattened_results = list(chain.from_iterable(fetch_metrics_descriptor_results))

    for fetch_reslut in flattened_results:
        metric_per_project.setdefault(fetch_reslut.metric_descriptor, []).append(
            fetch_reslut.project_id
        )

    return metric_per_project, resource_labels


async def get_existing_metrics(
    autodiscovery_resources: Dict[str, AutodiscoveryResourceLinking],
) -> Dict[str, Set[str]]:
    resources_to_metrics = {
        resource_name: set() for resource_name in autodiscovery_resources.keys()
    }

    for resource_name, service_linking in autodiscovery_resources.items():
        metric_name_list = []
        if service_linking:
            for service in service_linking.possible_service_linking:
                for metric in service.metrics:
                    metric_name_list.append(metric.google_metric)
            for service in service_linking.disabled_services_for_resource:
                for metric in service.metrics:
                    metric_name_list.append(metric.google_metric)
        resources_to_metrics[resource_name] = set(metric_name_list)

    return resources_to_metrics


async def run_autodiscovery(
    gcp_services_list: List[GCPService],
    gcp_session: ClientSession,
    dt_session: ClientSession,
    token: str,
    previously_discovered_metrics: Dict[str, Any],
    autodiscovery_resources: Dict[str, AutodiscoveryResourceLinking],
) -> AutodiscoveryResult:
    start_time = time.time()
    logging_context.log("Adding metrics using autodiscovery")
    metric_context = await get_metric_context(gcp_session, dt_session, token, logging_context)

    discovered_metric_descriptors, resource_labels = await get_metric_descriptors(
        metric_context, gcp_session, token, autodiscovery_resources
    )

    existing_resources_to_metrics = await get_existing_metrics(autodiscovery_resources)

    autodiscovery_resources_to_metrics = {}

    for descriptor, project_ids in discovered_metric_descriptors.items():
        monitored_resource = descriptor.monitored_resources_types[0]
        if descriptor.value not in existing_resources_to_metrics[monitored_resource]:
            autodiscovery_resources_to_metrics.setdefault(monitored_resource, []).append(
                Metric(**(asdict(descriptor)), autodiscovered_metric=True, project_ids=project_ids)
            )

    for resource_name, metric_list in autodiscovery_resources_to_metrics.items():
        logging_context.log(
            f"For resource: [{resource_name}] discovered {len(metric_list)} metrics"
        )
        for metric in metric_list:
            logging_context.log(
                f"For resource: [{resource_name}] Adding metric: [{metric.google_metric}]"
            )

    sended_metrics_metadata = await send_metric_metadata(
        autodiscovery_resources_to_metrics, metric_context, previously_discovered_metrics
    )

    end_time = time.time()

    logging_context.log(f"Elapsed time in autodiscovery: {end_time-start_time} s")
    return AutodiscoveryResult(
        autodiscovered_resources_to_metrics=autodiscovery_resources_to_metrics,
        discovered_metric_list=sended_metrics_metadata,
        resource_dimensions=resource_labels,
    )


async def enrich_services_with_autodiscovery_metrics(
    current_services: List[GCPService],
    previously_discovered_metrics: Dict[str, Any],
    autodiscovery_resources: Dict[str, AutodiscoveryResourceLinking],
) -> AutodiscoveryResult:
    try:
        async with init_gcp_client_session() as gcp_session, init_dt_client_session() as dt_session:
            token = await create_token(logging_context, gcp_session)
            if not token:
                raise Exception("Failed to fetch token")

            autodiscovery_fetch_result = await run_autodiscovery(
                current_services,
                gcp_session,
                dt_session,
                token,
                previously_discovered_metrics,
                autodiscovery_resources,
            )

            return autodiscovery_fetch_result
    except Exception as e:
        logging_context.error(
            f"Failed to prepare autodiscovery new services metrics, will reuse previous metrics list; "
            f"{type(e).__name__} : {e}"
        )
        return AutodiscoveryResult(
            autodiscovered_resources_to_metrics={},
            discovered_metric_list=previously_discovered_metrics,
            resource_dimensions={},
        )
