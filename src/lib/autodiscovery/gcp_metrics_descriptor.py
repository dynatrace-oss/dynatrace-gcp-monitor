from dataclasses import dataclass
from typing import List

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
        return metric_name.replace(".", "_").replace("/", ".")

    @staticmethod
    def _cast_metric_kind_to_dt_format(metric_kind: str, value_type: str) -> str:
        if metric_kind == "GAUGE" or (metric_kind == "DELTA" and value_type == "DISTRIBUTION"):
            return "gauge"
        elif metric_kind == "DELTA" and value_type != "DISTRIBUTION":
            return "count,delta"
        else:
            raise Exception("Unknown metric type")

    @staticmethod
    def _get_key_metric_sufix(metric_name: str, data_type: str) -> str:
        if (
            metric_name.endswith("_count") or metric_name.endswith(".count")
        ) and data_type == "gauge":
            return ".gauge"
        if (
            not metric_name.endswith("_count")
            and not metric_name.endswith(".count")
            and data_type == "count"
        ):
            return ".count"
        return ""

    def _metric_parse(self, **kwargs):
        self.value = kwargs.get("type", "")
        self.type = self._cast_metric_kind_to_dt_format(
            kwargs.get("metricKind", ""), kwargs.get("valueType", "")
        )
        self.key = (
            "cloud.gcp."
            + self._cast_metric_key_to_dt_format(kwargs.get("type", ""))
            + self._get_key_metric_sufix(kwargs.get("type", ""), self.type)
        )
        self.display_name = kwargs.get("displayName", "")
        self.name = kwargs.get("displayName", "")
        self.description = kwargs.get("description", "")

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

    def __init__(self, **kwargs):
        try:
            self._metric_parse(**kwargs)
        except Exception as e:
            raise Exception(f"Error for metric name: {self.value} " + str(e))
