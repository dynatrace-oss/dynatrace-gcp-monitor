"""This module contains data class definitions describing metrics."""

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

from dataclasses import dataclass
from datetime import timedelta
from typing import List, Text, Any


@dataclass(frozen=True)
class DimensionValue:
    name: Text
    value: Text


@dataclass(frozen=True)
class IngestLine:
    entity_id: Text
    metric_name: Text
    metric_type: Text
    value: Any
    timestamp: int
    dimension_values: List[DimensionValue]

    def dimensions_string(self) -> str:
        dimension_values = [f'{dimension_value.name}="{dimension_value.value}"'
                            for dimension_value
                            in self.dimension_values
                            if dimension_value.value != ""]  # MINT rejects line with empty dimension value
        dimensions = ",".join(dimension_values)
        if dimensions:
            dimensions = "," + dimensions
        return dimensions

    def to_string(self) -> str:
        separator = ',' if self.metric_type == 'gauge' else '='
        metric_type = self.metric_type if self.metric_type != 'count' else 'count,delta'
        return f"{self.metric_name}{self.dimensions_string()} {metric_type}{separator}{self.value} {self.timestamp}"


@dataclass(frozen=True)
class Dimension:
    """Represents singular dimension."""

    dimension: Text
    source: Text

    def __init__(self, **kwargs):
        if "value" in kwargs:
            object.__setattr__(self, "dimension", kwargs.get("value", ""))
        else:
            object.__setattr__(self, "dimension", kwargs.get("id", ""))

        object.__setattr__(self, "source", kwargs.get("value", ""))


@dataclass(frozen=True)
class Metric:
    """Represents singular metric to be ingested."""

    name: str
    google_metric: Text
    google_metric_kind: Text
    dynatrace_name: Text
    dynatrace_metric_type: Text
    unit: Text
    dimensions: List[Dimension]
    ingest_delay: timedelta
    sample_period_seconds: timedelta
    value_type: str
    metric_type: str

    def __init__(self, **kwargs):
        gcp_options = kwargs.get("gcpOptions", {})
        object.__setattr__(self, "name", kwargs.get("name", ""))
        object.__setattr__(self, "metric_type", kwargs.get("type", ""))
        object.__setattr__(self, "google_metric", kwargs.get("value", ""))
        object.__setattr__(self, "google_metric_kind", gcp_options.get("metricKind", ""))
        object.__setattr__(self, "dynatrace_name", kwargs.get("id", "").replace(":", "."))
        object.__setattr__(self, "dynatrace_metric_type", kwargs.get("type", ""))
        object.__setattr__(self, "unit", kwargs.get("unit", ""))
        object.__setattr__(self, "value_type", gcp_options.get("valueType", ""))
        object.__setattr__(self, "dimensions", [
            Dimension(**x) for x in kwargs.get("dimensions", {})
        ])

        ingest_delay = kwargs.get("gcpOptions", {}).get("ingestDelay", None)
        if ingest_delay:
            ingest_delay = ingest_delay.replace("s", "")
            object.__setattr__(self, "ingest_delay", timedelta(seconds=int(ingest_delay)))
        else:
            object.__setattr__(self, "ingest_delay", timedelta(seconds=60))

        sps = kwargs.get("gcpOptions", {}).get("samplePeriod", None)
        if sps:
            sps = sps.replace("s", "")
            object.__setattr__(self, "sample_period_seconds", timedelta(seconds=int(sps)))
        else:
            object.__setattr__(self, "sample_period_seconds", timedelta(seconds=60))


@dataclass(frozen=True)
class GCPService:
    """Describes singular GCP service to ingest data from."""

    name: Text
    technology_name: Text
    dimensions: List[Dimension]
    metrics = List[Metric]

    def __init__(self, **kwargs):
        object.__setattr__(self, "name", kwargs.get("service", ""))
        object.__setattr__(self, "technology_name", kwargs.get("tech_name", "N/A"))
        object.__setattr__(self, "dimensions", [
            Dimension(**x) for x in kwargs.get("dimensions", {})
        ])
        object.__setattr__(self, "metrics", [
            Metric(**x)
            for x
            in kwargs.get("metrics", {})
            if x.get("gcpOptions", {}).get("valueType", "").upper() != "STRING"
        ])


DISTRIBUTION_VALUE_KEY = 'distributionValue'
BOOL_VALUE_KEY = 'boolValue'
DOUBLE_VALUE_KEY = 'doubleValue'
INT_VALUE_KEY = 'int64Value'

TYPED_VALUE_KEY_MAPPING = {
    'INT64': INT_VALUE_KEY,
    'DOUBLE': DOUBLE_VALUE_KEY,
    'BOOL': BOOL_VALUE_KEY,
    'DISTRIBUTION': DISTRIBUTION_VALUE_KEY
}
