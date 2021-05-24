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

import asyncio
import re
from functools import partial
from typing import Any, Dict, Iterable, Text

from lib.context import MetricsContext
from lib.entities.decorator import entity_extractor
from lib.entities.google_api import generic_paging, fetch_zones
from lib.entities.ids import get_func_create_entity_id, LabelToApiRspMapping
from lib.entities.model import CdProperty, Entity
from lib.metrics import GCPService

export_labels_regex = re.compile(
    r"^projects\/([\w,-]*)\/zones\/([\w,-.]*)/instances$"
)

_GCP_COMPUTE_ENDPOINT = "https://compute.googleapis.com"


def _extract_label(gfun_name: Text, group_index: int) -> Text:
    """Attempt to extract part of gcp function name.

    0 -> Full name
    1 -> project_id
    2 -> zone
    """
    if (group_index < 0) or (group_index > 2):
        raise ValueError("Expected group_index <0,2>")

    match = export_labels_regex.match(gfun_name)
    if not match:
        raise ValueError("Pubsub name should adhere to expected schema")

    return match.group(group_index)


LabelToApiResponseMapping: LabelToApiRspMapping = {
    "resource.labels.instance_id": lambda x: _extract_label(x.get("name", ""), 2),
    "resource.labels.zone_id": lambda x: _extract_label(x.get("name", ""), 2),
    "resource.labels.project_id": lambda x: _extract_label(x.get("name", ""), 1),
}
create_entity_id = get_func_create_entity_id(LabelToApiResponseMapping)


def _get_properties(rsp: Dict[Text, Any]) -> Iterable[CdProperty]:
    """ Retrieve key properties to be passed onto dynatrace server. """
    machine_type = rsp.get("machineType", "/").split("/")[-1]
    labels = [CdProperty(label, value) for label, value in rsp.get("labels", {}).items()]
    return [
        *labels,
        CdProperty("Status", rsp.get("status", "N/A")),
        CdProperty("Cpu Platform", rsp.get("cpuPlatform", "N/A")),
        CdProperty("Machine Type", machine_type),
    ]


def _cloud_function_resp_to_monitored_entities(page: Dict[Text, Any], svc_def: GCPService):
    """ Create CustomDevice instanace from google api response."""
    items = page.get("items", [])
    if not items:
        return []

    page_id = page.get("id", None)
    if page_id is None:
        return []
    project_id = _extract_label(page_id, 1)
    zone_id = _extract_label(page_id, 2)

    mappings = {
        "resource.labels.instance_id": lambda x: x.get("id", ""),
        "resource.labels.zone": lambda x: zone_id,
        "resource.labels.project_id": lambda x: project_id,
    }

    entities = []
    for cd in items:
        ips = [
            interface.get("networkIP", "")
            for interface
            in cd.get("networkInterfaces", [])
        ]
        tags = cd.get("tags", {}).get("items", [])
        entities.append(Entity(
            id=get_func_create_entity_id(mappings)(cd, svc_def),
            display_name=cd.get("name", ""),
            group=svc_def.technology_name,
            ip_addresses=frozenset(ips),
            listen_ports=frozenset(),
            favicon_url="no-gcp-icon-available",
            dtype=svc_def.technology_name,
            properties=_get_properties(cd),
            tags=frozenset(tags),
            dns_names=frozenset()
        ))

    return entities


@entity_extractor("gce_instance")
async def get_cloud_function_entity(ctx: MetricsContext, project_id: str, svc_def: GCPService) -> Iterable[Entity]:
    """ Retrieve entity info on GCP cloud functions from google api. """
    zones = await fetch_zones(ctx, project_id)

    tasks = []
    for zone in zones:
        url = f"{_GCP_COMPUTE_ENDPOINT}/compute/v1/projects/{project_id}/zones/{zone}/instances"
        mapper_func = partial(_cloud_function_resp_to_monitored_entities, svc_def=svc_def)
        tasks.append(generic_paging(url, ctx, mapper_func))
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    for result in results:
        all_results.extend(result)

    return all_results
