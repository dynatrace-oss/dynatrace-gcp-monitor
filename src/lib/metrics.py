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

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Text, Any, Dict
from lib.configuration import config

VARIABLE_BRACKETS_PATTERN=re.compile("{{.*?}}")
VARIABLE_VAR_PATTERN=re.compile("var:\\S+")

ALLOWED_METRIC_DIMENSION_VALUE_LENGTH = config.gcp_allowed_metric_dimension_value_length()
ALLOWED_METRIC_KEY_LENGTH = config.gcp_allowed_metric_key_length()
ALLOWED_METRIC_DIMENSION_KEY_LENGTH = config.gcp_allowed_metric_dimension_key_length()

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
    displayName: str = ""
    description: str = ""
    unit: str = ""
    include_metadata: bool = False

    def dimensions_string(self) -> str:
        dimension_values = [f'{dimension_value.name[0:ALLOWED_METRIC_DIMENSION_KEY_LENGTH]}="{dimension_value.value[0:ALLOWED_METRIC_DIMENSION_VALUE_LENGTH]}"'
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
        metadata = ""
        if self.include_metadata:
            metric_t = self.metric_type if  self.metric_type != 'count,delta' else 'count'
            metadata = f"\n#{self.metric_name[0:ALLOWED_METRIC_KEY_LENGTH]} {metric_t} dt.meta.displayname=\"{self.displayName}\",dt.meta.description=\"{self.description}\",dt.meta.unit=\"{self.unit}\""
        return f"{self.metric_name[0:ALLOWED_METRIC_KEY_LENGTH]}{self.dimensions_string()} {metric_type}{separator}{self.value} {self.timestamp}{metadata}"


@dataclass(frozen=True)
class Dimension:
    """Represents singular dimension."""

    key_for_get_func_create_entity_id: Text
    key_for_create_entity_id: Text
    key_for_fetch_metric: Text
    key_for_send_to_dynatrace: Text

    def __init__(self, **kwargs):
        key = kwargs.get("key", "")
        value = kwargs.get("value", "").replace("label:", "")
        object.__setattr__(self, "key_for_get_func_create_entity_id", value)
        object.__setattr__(self, "key_for_create_entity_id", (value.replace("resource.labels.", "") or key))
        object.__setattr__(self, "key_for_fetch_metric", value or f'metric.labels.{key}')
        object.__setattr__(self, "key_for_send_to_dynatrace", key) # or 'resource|metric.labels.{key}' from response used by lib.metric_ingest.create_dimensions will use last part of source/value, as this is how this worked before - no breaking changes allowed


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
    autodiscovered: bool
    description: str

    def __init__(self, **kwargs):
        gcp_options = kwargs.get("gcpOptions", {})
        object.__setattr__(self, "name", kwargs.get("name", ""))
        object.__setattr__(self, "metric_type", kwargs.get("type", ""))
        object.__setattr__(self, "google_metric", kwargs.get("value", "").replace("metric:", ""))
        object.__setattr__(self, "google_metric_kind", gcp_options.get("metricKind", ""))
        object.__setattr__(self, "dynatrace_name", kwargs.get("key", "").replace(":", "."))
        object.__setattr__(self, "dynatrace_metric_type", kwargs.get("type", ""))
        object.__setattr__(self, "unit", kwargs.get("gcpOptions", {}).get("unit", None))
        object.__setattr__(self, "value_type", gcp_options.get("valueType", ""))
        object.__setattr__(self, "autodiscovered", kwargs.get("autodiscovered", False))
        object.__setattr__(self, "description", kwargs.get("description", ""))

        object.__setattr__(self, "dimensions", [Dimension(**x) for x in kwargs.get("dimensions", {})])

        ingest_delay = kwargs.get("gcpOptions", {}).get("ingestDelay", None)
        if ingest_delay:
            object.__setattr__(self, "ingest_delay", timedelta(seconds=ingest_delay))
        else:
            object.__setattr__(self, "ingest_delay", timedelta(seconds=60))

        sps = kwargs.get("gcpOptions", {}).get("samplePeriod", None)
        if sps:
            object.__setattr__(self, "sample_period_seconds", timedelta(seconds=sps))
        else:
            object.__setattr__(self, "sample_period_seconds", timedelta(seconds=60))


@dataclass(frozen=True)
class GCPService:
    """Describes singular GCP service to ingest data from."""
    # IMPORTANT! this object is only for one combination of object/featureSet!
    # If you have 2 featureSets enabled for some service you will have 2 such objects

    name: Text
    technology_name: Text
    feature_set: Text
    dimensions: List[Dimension]
    metrics = List[Metric]
    monitoring_filter: Text
    activation: Dict[Text, Any]

    def __init__(self, **kwargs):
        object.__setattr__(self, "name", kwargs.get("service", ""))
        object.__setattr__(self, "feature_set", kwargs.get("featureSet", ""))
        object.__setattr__(self, "technology_name", kwargs.get("tech_name", "N/A"))
        object.__setattr__(self, "dimensions", [Dimension(**x) for x in kwargs.get("dimensions", {})])

        object.__setattr__(self, "metrics", [
            Metric(**x)
            for x
            in kwargs.get("metrics", {})
            if x.get("gcpOptions", {}).get("valueType", "").upper() != "STRING"
        ])
        object.__setattr__(self, "activation", kwargs.get("activation", {}))
        monitoring_filter = kwargs.get("gcpMonitoringFilter", "")
        if self.activation:
            for var_key, var_value in (self.activation.get("vars", {}) or {}).items():
                monitoring_filter = monitoring_filter.replace(f'{{{var_key}}}', var_value)\
                    .replace(f'var:{var_key}', var_value)
        # remove not matched variables
        monitoring_filter = VARIABLE_BRACKETS_PATTERN.sub('', monitoring_filter)
        monitoring_filter = VARIABLE_VAR_PATTERN.sub('', monitoring_filter)
        object.__setattr__(self, "monitoring_filter", monitoring_filter)

    def __hash__(self):
        return hash((self.name, self.technology_name, self.feature_set, self.monitoring_filter))


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
