import os
import time
from dataclasses import asdict
from typing import List

from aiohttp import ClientSession

from lib.autodiscovery.gcp_metrics_descriptor import GCPMetricDescriptor
from lib.clientsession_provider import init_gcp_client_session
from lib.configuration import config
from lib.context import LoggingContext
from lib.credentials import create_token
from lib.metrics import GCPService, Metric

logging_context = LoggingContext("AUTODISCOVERY")


discovered_resource_type = os.environ.get("AUTODISCOVERY_RESOURCE_TYPE", "gce_instance")


async def get_metric_descriptors(
    gcp_session: ClientSession, token: str
) -> List[GCPMetricDescriptor]:
    project_id = config.project_id()
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    url = f"https://monitoring.googleapis.com/v3/projects/{project_id}/metricDescriptors"
    params = {}


    discovered_metrics_descriptors = []

    while True:
        partly_discovered_metrics = []

        response = await gcp_session.request("GET", url=url, headers=headers, params=params)
        response.raise_for_status()
        response_json = await response.json()

        for descriptor in response_json.get("metricDescriptors", []):
            try:
                partly_discovered_metrics.append( GCPMetricDescriptor(**descriptor))
            except Exception as error:
                logging_context.log(f"Failed to load autodiscovered metric. Details: {error}")
        discovered_metrics_descriptors.extend(partly_discovered_metrics)

        page_token = response_json.get("nextPageToken", "")
        params["pageToken"] = page_token
        if page_token == "":
            break

    discovered_metrics_descriptors = list(
        filter(
            lambda descriptor: descriptor.gcpOptions.valueType.upper() != "STRING",
            discovered_metrics_descriptors,
        )
    )
    discovered_metrics_descriptors = list(
        filter(
            lambda descriptor: discovered_resource_type in descriptor.monitored_resources_types,
            discovered_metrics_descriptors,
        )
    )
    return discovered_metrics_descriptors


async def run_autodiscovery(
    gcp_services_list: List[GCPService], gcp_session: ClientSession, token: str
):
    start_time = time.time()
    logging_context.log("Adding metrics using autodiscovery")

    bucket_gcp_services = list(
        filter(lambda x: discovered_resource_type in x.name, gcp_services_list)
    )

    existing_metric_list = []
    for service in bucket_gcp_services:
        existing_metric_list.extend(service.metrics)

    discovered_metric_descriptors = await get_metric_descriptors(gcp_session, token)

    existing_metric_names = [
        existing_metric.google_metric for existing_metric in existing_metric_list
    ]
    missing_metrics_list = []

    for descriptor in discovered_metric_descriptors:
        if descriptor.value not in existing_metric_names:
            metric_fields = asdict(descriptor)
            metric_fields["include_metadata"] = True
            autodiscovered_metric = Metric(**(metric_fields))
            missing_metrics_list.append(autodiscovered_metric)

    logging_context.log(f"In the extension there are {len(existing_metric_list)} metrics")
    logging_context.log(
        f"Discovered Resource type {discovered_resource_type} has {len(discovered_metric_descriptors)} metrics"
    )
    logging_context.log(f"Adding {len(missing_metrics_list)} metrics")
    logging_context.log(
        f"Adding metrics: {[metric.google_metric for metric in missing_metrics_list]}"
    )

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
        async with init_gcp_client_session() as gcp_session:
            token = await create_token(logging_context, gcp_session)
            if not token:
                raise Exception("Failed to fetch token")

            autodiscovery_fetch_result = await run_autodiscovery(
                current_services, gcp_session, token
            )

            return autodiscovery_fetch_result
    except Exception as e:
        logging_context.error(
            f"Failed to prepare autodiscovery new services metrics, will reuse from configuration file; {str(e)}"
        )
        return current_services
