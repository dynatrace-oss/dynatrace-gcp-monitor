from dataclasses import dataclass
from typing import List, Tuple

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


@dataclass(frozen=True)
class GCPMetricDescriptorOptions:
    ingestDelay: int
    samplePeriod: int
    valueType: str
    metricKind: str
    unit: str


@dataclass(frozen=True, order=True)
class GCPMetricDescriptorDimension:
    key: str
    value: str


@dataclass(frozen=True)
class GCPMetricDescriptor:
    """Represents a Google Cloud Platform (GCP) Metric Descriptor."""

    value: str
    key: str
    display_name: str
    name: str
    description: str
    type: str
    gcpOptions: GCPMetricDescriptorOptions
    dimensions: Tuple[GCPMetricDescriptorDimension, ...]
    monitored_resources_types: Tuple[str, ...]

    @staticmethod
    def _cast_metric_key_to_dt_format(metric_name: str) -> str:
        return metric_name.replace(".", "_").replace("/", ".")

    @staticmethod
    def _cast_metric_kind_to_dt_format(metric_kind: str, value_type: str) -> str:
        if metric_kind == "GAUGE" or (metric_kind == "DELTA" and value_type == "DISTRIBUTION"):
            return "gauge"
        elif metric_kind == "DELTA" and value_type != "DISTRIBUTION":
            return "count,delta"
        elif metric_kind == "CUMULATIVE":
            return "count,delta"
        else:
            raise Exception(f"Unknown metric type {metric_kind}")

    @staticmethod
    def _get_key_metric_suffix(metric_name: str, data_type: str) -> str:
        if (
            metric_name.endswith("_count") or metric_name.endswith(".count")
        ) and data_type == "gauge":
            return ".gauge"
        if (
            not metric_name.endswith("_count")
            and not metric_name.endswith(".count")
            and (data_type == "count" or data_type == "count,delta")
        ):
            return ".count"
        return ""

    @classmethod
    def create(cls, **kwargs):
        value = kwargs.get("type", "")
        type_ = cls._cast_metric_kind_to_dt_format(
            kwargs.get("metricKind", ""), kwargs.get("valueType", "")
        )
        key = (
            "cloud.gcp."
            + cls._cast_metric_key_to_dt_format(kwargs.get("type", ""))
            + cls._get_key_metric_suffix(kwargs.get("type", ""), type_)
        )
        display_name = kwargs.get("displayName", "")
        name = kwargs.get("displayName", "")
        description = kwargs.get("description", "")

        gcp_options = GCPMetricDescriptorOptions(
            ingestDelay=int(kwargs.get("metadata", {}).get("ingestDelay", "60s")[:-1]),
            samplePeriod=int(kwargs.get("metadata", {}).get("samplePeriod", "60s")[:-1]),
            valueType=kwargs.get("valueType", ""),
            metricKind=kwargs.get("metricKind", ""),
            unit=GCP_UNIT_CONVERSION_MAP.get(kwargs.get("unit", ""), "Unspecified"),
        )
        dimensions = tuple(
            sorted(
                [
                    GCPMetricDescriptorDimension(
                        key=dimension.get("key"),
                        value="label:metric.labels." + dimension.get("key"),
                    )
                    for dimension in kwargs.get("labels") or []
                ]
            )
        )
        monitored_resources_types = tuple(sorted(kwargs.get("monitoredResourceTypes", [])))

        return cls(
            value=value,
            key=key,
            display_name=display_name,
            name=name,
            description=description,
            type=type_,
            gcpOptions=gcp_options,
            dimensions=dimensions,
            monitored_resources_types=monitored_resources_types,
        )
