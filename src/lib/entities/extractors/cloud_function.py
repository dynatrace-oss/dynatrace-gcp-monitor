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
from functools import partial
from typing import Any, Dict, Iterable, Text

from lib.context import MetricsContext
from lib.entities.decorator import entity_extractor
from lib.entities.google_api import generic_paging
from lib.entities.ids import get_func_create_entity_id, LabelToApiRspMapping
from lib.entities.model import CdProperty, Entity
from lib.metrics import GCPService

export_labels_regex = re.compile(
    r"^projects\/([\w,-]*)\/locations\/([\w,-]*)\/functions\/([\w,-]*)$"
)


def _extract_label(gfun_name: Text, group_index: int) -> Text:
    """Attempt to extract part of gcp function name.
    
    0 -> Full name
    1 -> project_id
    2 -> region
    3 -> name
    """
    if (group_index < 0) or (group_index > 3):
        raise ValueError("Expected group_index <0,3>")

    match = export_labels_regex.match(gfun_name)
    if not match:
        raise ValueError("Function name should adhere to expected schema")

    return match.group(group_index)


LabelToApiResponseMapping: LabelToApiRspMapping = {
    "resource.labels.function_name": lambda x: _extract_label(x.get("name", ""), 3),
    "resource.labels.project_id": lambda x: _extract_label(x.get("name", ""), 1),
    "resource.labels.region": lambda x: _extract_label(x.get("name", ""), 2)
}
create_entity_id = get_func_create_entity_id(LabelToApiResponseMapping)


def _get_properties(rsp: Dict[Text, Any]) -> Iterable[CdProperty]:
    """ Retrieve key properties to be passed onto dynatrace server. """
    return [
        CdProperty("Status", rsp.get("status", "N/A")),
        CdProperty("Entry point", rsp.get("entryPoint", "N/A")),
        CdProperty("Available memory Mb", rsp.get("availableMemoryMb", "N/A")),
        CdProperty("Runtime", rsp.get("runtime", "")),
        CdProperty("Ingress settings", rsp.get("ingressSettings", "")),
    ]


def _cloud_function_resp_to_monitored_entities(page: Dict[Text, Any], svc_def: GCPService):
    """ Create CustomDevice instanace from google api response."""
    return [
        Entity(
            id=create_entity_id(cd, svc_def),
            display_name=_extract_label(cd.get("name", ""), 3),
            group=svc_def.technology_name,
            ip_addresses=[],
            listen_ports=[],
            favicon_url="no-gcp-icon-available",
            dtype=svc_def.technology_name,
            properties=_get_properties(cd),
            tags=[],
            dns_names=[]
        ) for cd in page.get("functions", [])
    ]


@entity_extractor("cloud_function", "cloudfunctions.googleapis.com")
async def get_cloud_function_entity(ctx: MetricsContext, project_id: str, svc_def: GCPService) -> Iterable[Entity]:
    """ Retrieve entity info on GCP cloud functions from google api. """
    url = f"https://cloudfunctions.googleapis.com/v1/projects/{project_id}/locations/-/functions"
    mapper_func = partial(_cloud_function_resp_to_monitored_entities, svc_def=svc_def)
    return await generic_paging(project_id, url, ctx, mapper_func)
