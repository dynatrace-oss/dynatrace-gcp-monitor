import os
import re
import time
from dataclasses import asdict, dataclass
from typing import List

from aiohttp import ClientSession
from lib.clientsession_provider import init_gcp_client_session

from lib.configuration import config
from lib.context import LoggingContext
from lib.credentials import create_token
from lib.metrics import GCPService, Metric

logging_context = LoggingContext(None)


discovered_resource_type = os.environ.get("AUTODISCOVERY_RESOURCE_TYPE", "cloud_function")


GCP_UNIT_CONVERSION_MAP = {
    "1": "Count",
    "count": "Count",
    "Count": "Count",
    "{operation}": "Count",
    "{packet}": "Count",
    "{packets}": "Count",
    "{request}": "Count",
    "{port}": "Count",
    "{connection}": "Count",
    "{devices}": "Count",
    "{errors}": "Count",
    "{cpu}": "Count",
    "{query}": "Count",
    "{inode}": "Count",
    "s": "Second",
    "s{idle}": "Second",
    "sec": "Second",
    "By": "Byte",
    "Byte": "Byte",
    "bytes": "Byte",
    "By/s": "BytePerSecond",
    "kBy": "KiloBytePerSecond",
    "GBy.s": "GigaBytePerSecond",
    "GiBy": "GigaByte",
    "GBy": "GigaByte",
    "MiBy": "MegaByte",
    "ns": "NanoSecond",
    "us": "MicroSecond",
    "usec": "MicroSecond",
    "ms": "MilliSecond",
    "milliseconds": "MilliSecond",
    "us{CPU}": "MicroSecond",
    "10^2.%": "Percent",
    "%": "Percent",
    "percent": "Percent",
    "1/s": "PerSecond",
    "frames/seconds": "PerSecond",
    "s{CPU}": "Second",
    "s{uptime}": "Second",
    "{dBm}": "DecibelMilliWatt",
}


@dataclass()
class GCPMetricDescriptor:
    """Represents a Google Cloud Platform (GCP) Metric Descriptor."""

    @dataclass()
    class Options:
        ingestDelay: int
        samplePeriod: int
        valueType: str
        metricKind: str
        unit: str

    @dataclass()
    class Dimension:
        key: str
        value: str

    value: str
    key: str
    display_name: str
    name: str
    description: str
    type: str
    gcpOptions: Options
    dimensions: List[Dimension]
    monitored_resources_types: str

    @staticmethod
    def _cast_metric_key_to_dt_format(metric_name: str) -> str:
        metric_name = re.sub(r"\.", "_", metric_name)
        metric_name = re.sub(r"/", ".", metric_name)
        return metric_name

    @staticmethod
    def _cast_metric_kind_to_dt_format(metric_kind: str, value_type: str) -> str:
        if metric_kind == "GAUGE" or (metric_kind == "DELTA" and value_type == "DISTRIBUTION"):
            return "gauge"
        elif metric_kind == "DELTA" and value_type != "DISTRIBUTION":
            return "count,delta"
        return ""

    def __init__(self, **kwargs):
        self.value = kwargs.get("type", "")
        self.key = "cloud.gcp." + self._cast_metric_key_to_dt_format(kwargs.get("type", ""))
        self.display_name = kwargs.get("displayName", "")
        self.name = kwargs.get("displayName", "")
        self.description = kwargs.get("description", "")
        self.type = self._cast_metric_kind_to_dt_format(
            kwargs.get("metricKind", ""), kwargs.get("valueType", "")
        )
        self.gcpOptions = GCPMetricDescriptor.Options(
            ingestDelay=int(kwargs.get("metadata", {}).get("ingestDelay", "60s")[:-1]),
            samplePeriod=int(kwargs.get("metadata", {}).get("samplePeriod", "60s")[:-1]),
            valueType=kwargs.get("valueType", ""),
            metricKind=kwargs.get("metricKind", ""),
            unit=GCP_UNIT_CONVERSION_MAP.get(kwargs.get("unit", ""), "Unspecified"),
        )
        self.dimensions = [
            GCPMetricDescriptor.Dimension(
                key=dimension.get("key"),
                value="label:metric.labels." + dimension.get("key"),
            )
            for dimension in kwargs.get("labels") or []
        ]
        self.monitored_resources_types = kwargs.get("monitoredResourceTypes", [])


async def get_metric_descriptors(gcp_session, token) -> List[GCPMetricDescriptor]:
    project_id = config.project_id()
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    url = f"https://monitoring.googleapis.com/v3/projects/{project_id}/metricDescriptors"

    response = await gcp_session.request("GET", url=url, headers=headers)
    response = await response.json()

    discovered_metrics_descriptors = [
        GCPMetricDescriptor(**descriptor) for descriptor in response["metricDescriptors"]
    ]
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


async def enrich_services_autodiscovery(
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
            missing_metrics_list.append(Metric(**asdict(descriptor)))
    print(missing_metrics_list)
    logging_context.log(f"In Extension we have this amount of metrics: {len(existing_metric_list)}")
    logging_context.log(
        f"Resource type: {discovered_resource_type} have this amount of metrics: {len(discovered_metric_descriptors)}"
    )
    logging_context.log(f"Adding {len(missing_metrics_list)} metrics")
    logging_context.log(
        f"Adding metrics: {[metric.google_metric for metric in missing_metrics_list]}"
    )

    for service in gcp_services_list:
        if service.name == discovered_resource_type and service.feature_set == "default_metrics":
            service.metrics.extend([metric for metric in missing_metrics_list])

    end_time = time.time()

    print(f"Elapsed time in autodiscovery: {end_time-start_time} s")
    return gcp_services_list


async def prepare_services_autodiscovery_polling(
    current_services: List[GCPService],
) -> List[GCPService]:
    try:
        async with init_gcp_client_session() as gcp_session:
            token = await create_token(logging_context, gcp_session)
            if not token:
                raise Exception("Failed to fetch token")

            autodiscovery_fetch_result = await enrich_services_autodiscovery(
                current_services, gcp_session, token
            )

            return autodiscovery_fetch_result
    except Exception as e:
        logging_context.error(
            f"Failed to prepare autodiscovery new services metrics, will reuse from configuration file; {str(e)}"
        )
        return current_services
