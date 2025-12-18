#   Copyright 2021 Dynatrace LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from lib.entities.model import CdProperty
from lib.metric_ingest import *
from lib.topology.topology import build_entity_id_map


def test_create_dimension_correct_values():
    name = "n" * (MAX_DIMENSION_NAME_LENGTH - 1)
    value = "v" * (MAX_DIMENSION_VALUE_LENGTH - 1)

    dimension_value = create_dimension(name, value)

    assert dimension_value.name == name
    assert dimension_value.value == value


def test_create_dimension_too_long_dimension():
    name = "n" * (MAX_DIMENSION_NAME_LENGTH + 100)
    value = "v" * (MAX_DIMENSION_VALUE_LENGTH + 100)

    dimension_value = create_dimension(name, value)

    assert len(dimension_value.name) == MAX_DIMENSION_NAME_LENGTH
    assert len(dimension_value.value) == MAX_DIMENSION_VALUE_LENGTH


def test_create_dimension_escapes_quotes_and_removes_control_chars():
    name = "querystring"
    value = '"C:\\Program Files\\Foo\\bar.exe" -flag\nnext'

    dimension_value = create_dimension(name, value)

    assert dimension_value.value == '\\"C:\\Program Files\\Foo\\bar.exe\\" -flag next'
    assert "\n" not in dimension_value.value
    assert "\r" not in dimension_value.value
    assert "\t" not in dimension_value.value


def test_flatten_and_enrich_metric_results_all_additional_dimensions():
    context_mock = MetricsContext(None, None, "", "", datetime.utcnow(), 0, "", "", False, False, None)
    metric_results = [[IngestLine("entity_id", "m1", "count", 1, 10000, [])]]
    entity_id_map = build_entity_id_map([[Entity("entity_id", "", "", ip_addresses=["1.1.1.1", "0.0.0.0"], listen_ports=[],
                                         favicon_url="", dtype="", properties=[CdProperty("Example property", "example_value")],
                                         tags=[], dns_names=["other.dns.name", "dns.name"])]])

    lines = flatten_and_enrich_metric_results(context=context_mock, fetch_metric_results=metric_results, entity_id_map=entity_id_map)

    assert len(lines) == 1
    ingest_line = lines[0]
    expected_dimensions = [DimensionValue(name="entity.ip_address", value="0.0.0.0"),
                           DimensionValue(name="entity.dns_name", value="dns.name"),
                           DimensionValue(name="entity.example_property", value="example_value")]
    assert set(expected_dimensions) == set(ingest_line.dimension_values)

