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

from lib.context import Context
from lib.entities.decorator import entity_extractor
from lib.entities.google_api import generic_paging
from lib.entities.ids import get_func_create_entity_id, LabelToApiRspMapping
from lib.entities.model import CdProperty, Entity
from lib.metrics import GCPService


export_labels_regex = re.compile(
    r"^projects\/([\w,-]*)\/subscriptions\/([\w,-.]*)$"
)


def _extract_label(gfun_name: Text, group_index: int) -> Text:
    """Attempt to extract part of gcp function name.
    
    0 -> Full name
    1 -> project_id
    2 -> name
    """
    if (group_index < 0) or (group_index > 2):
        raise ValueError("Expected group_index <0,2>")

    match = export_labels_regex.match(gfun_name)
    if not match:
        raise ValueError("Pubsub name should adhere to expected schema")

    return match.group(group_index)


LabelToApiResponseMapping: LabelToApiRspMapping = {
    "resource.labels.subscription_id": lambda x: _extract_label(x.get("name", ""), 2),
    "resource.labels.project_id": lambda x: _extract_label(x.get("name", ""), 1),
}
create_entity_id = get_func_create_entity_id(LabelToApiResponseMapping)


def _get_properties(rsp: Dict[Text, Any]) -> Iterable[CdProperty]:
    """ Retrieve key properties to be passed onto dynatrace server. """
    return [
        CdProperty("Topic", rsp.get("topic", "N/A")),
        CdProperty("Ack Deadline Seconds", rsp.get("ackDeadlineSeconds", "N/A")),
    ]


def _cloud_function_resp_to_monitored_entities(page: Dict[Text, Any], svc_def: GCPService):
    """ Create CustomDevice instanace from google api response."""
    return [
        Entity(
            id=create_entity_id(cd, svc_def),
            display_name=_extract_label(cd.get("name", ""), 2),
            group=svc_def.technology_name,
            ip_addresses=frozenset(),
            listen_ports=frozenset(),
            favicon_url="no-gcp-icon-available",
            dtype=svc_def.technology_name,
            properties=_get_properties(cd),
            tags=frozenset(),
            dns_names=frozenset()
        ) for cd in page.get("subscriptions", [])
    ]


@entity_extractor("pubsub_subscription")
async def get_cloud_function_entity(ctx: Context, svc_def: GCPService) -> Iterable[Entity]:
    """ Retrieve entity info on GCP cloud functions from google api. """
    url = "https://pubsub.googleapis.com/v1/projects/{project_id}/subscriptions/".format(
        project_id=ctx.project_id
    )
    mapper_func = partial(_cloud_function_resp_to_monitored_entities, svc_def=svc_def)
    return await generic_paging(url, ctx, mapper_func)
