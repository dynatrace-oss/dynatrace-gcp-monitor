import asyncio
from typing import List, Set, Dict, Iterable, Awaitable

from lib.context import MetricsContext
from lib.entities import entities_extractors
from lib.entities.model import Entity
from lib.metrics import GCPService


async def fetch_topology(context: MetricsContext, project_id: str, services: List[GCPService], disabled_apis: Set[str]) \
        -> Dict[GCPService, Iterable[Entity]]:

    topology_tasks_by_service: Dict[GCPService, Awaitable[Iterable[Entity]]] = {}

    for service in choose_services_for_topology_fetch(context, project_id, services, disabled_apis):
        topology_function = entities_extractors[service.name].extractor(context, project_id, service)
        topology_task = asyncio.create_task(topology_function)
        topology_tasks_by_service[service] = topology_task

    topology_by_service: Dict[GCPService, Iterable[Entity]] = {}

    for service, task in topology_tasks_by_service.items():
        topology_by_service[service] = await task

    return topology_by_service


def choose_services_for_topology_fetch(
        context: MetricsContext, project_id: str, services: List[GCPService], disabled_apis: Set[str]):
    services_for_topology_fetch = []
    disabled_topology_services = set()
    no_extractor_services = set()

    for service in services:
        if service.name not in entities_extractors:
            no_extractor_services.add(service.name)
            continue

        extractor = entities_extractors[service.name]

        if extractor.used_api in disabled_apis:
            disabled_topology_services.add(service.name)
            continue

        services_for_topology_fetch.append(service)

    msg_chosen_services = ", ".join([service.name for service in services_for_topology_fetch])
    msg_disabled_topology_services = ", ".join(disabled_topology_services)
    msg_no_extractor_services = ", ".join(no_extractor_services)
    context.log(project_id, f"Services chosen for topology fetch (fetching additional resource info to create Dynatrace entities): [{msg_chosen_services}];"
                            f" skipped services (disabled APIs=these services are disabled in this GCP project): [{msg_disabled_topology_services}]; "
                            f" skipped services (entity extractors not yet implemented in GCP Monitor): [{msg_no_extractor_services}]")

    return services_for_topology_fetch


def build_entity_id_map(fetch_topology_results: List[Iterable[Entity]]) -> Dict[str, Entity]:
    result = {}
    for result_set in fetch_topology_results:
        for entity in result_set:
            # Ensure order of entries to avoid "flipping" when choosing the first one for dimension value
            entity.dns_names.sort()
            entity.ip_addresses.sort()
            entity.tags.sort()
            entity.listen_ports.sort()
            result[entity.id] = entity
    return result
