import asyncio
import unittest
from datetime import datetime
from typing import Dict, Iterable
from unittest.mock import MagicMock

from lib.context import MetricsContext
from lib.entities.model import EntitiesExtractorData, Entity
from lib.metrics import GCPService
from lib.topology import topology


fake_entities_1 = [MagicMock()]
fake_entities_2 = [MagicMock(), MagicMock()]

async def extractor_1(ctx: MetricsContext, project_id: str, svc_def: GCPService) -> Iterable[Entity]:
    return fake_entities_1

async def extractor_2(ctx: MetricsContext, project_id: str, svc_def: GCPService) -> Iterable[Entity]:
    return fake_entities_2

service1_ok = GCPService(service="service1")
service2_no_extractor = GCPService(service="service2")
service3_disabled_api = GCPService(service="service3")
service4_also_ok = GCPService(service="service4")

services = [service1_ok, service2_no_extractor, service3_disabled_api, service4_also_ok]

disabled_apis = ["disabled_api"]

entities_extractors: Dict[str, EntitiesExtractorData] = {
    "service1": EntitiesExtractorData(extractor_1, "ok_api"),
    "service3": EntitiesExtractorData(extractor_1, "disabled_api"),
    "service4": EntitiesExtractorData(extractor_2, "ok_api"),
}


@unittest.mock.patch("lib.topology.topology.entities_extractors", new=entities_extractors)
def test_fetch_topology():
    context = MetricsContext(None, None, "", "", datetime.utcnow(), 0, "", "", False, False, None)

    topology_coro = topology.fetch_topology(context, "my_project_id", services, set(disabled_apis))

    topology_result = asyncio.run(topology_coro)

    assert service1_ok in topology_result
    assert service2_no_extractor not in topology_result
    assert service3_disabled_api not in topology_result
    assert service4_also_ok in topology_result

    assert topology_result[service1_ok] is fake_entities_1
    assert topology_result[service4_also_ok] is fake_entities_2

    print(topology_result)
