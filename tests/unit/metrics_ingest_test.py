import aiohttp

from lib.entities.model import CdProperty
from lib.metric_ingest import *


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


def test_flatten_and_enrich_metric_results_all_additional_dimensions():
    context_mock = Context(aiohttp.ClientSession(), aiohttp.ClientSession(), "", "", datetime.utcnow(), 0, "", "", False, None)
    metric_results = [[IngestLine("entity_id", "m1", "count", 1, 10000, [])]]
    entity_id_map = {"entity_id": Entity("entity_id", "", "", ip_addresses=frozenset(["0.0.0.0"]), listen_ports=frozenset([]),
                                         favicon_url="", dtype="", properties=[CdProperty("Example property", "example_value")],
                                         tags=frozenset([]), dns_names=frozenset(["dns.name"]))}

    lines = flatten_and_enrich_metric_results(context=context_mock, fetch_metric_results=metric_results, entity_id_map=entity_id_map)

    assert len(lines) == 1
    ingest_line = lines[0]
    expected_dimensions = [DimensionValue(name="entity.ip_address", value="0.0.0.0"),
                           DimensionValue(name="entity.dns_name", value="dns.name"),
                           DimensionValue(name="entity.example_property", value="example_value")]
    assert set(expected_dimensions) == set(ingest_line.dimension_values)

