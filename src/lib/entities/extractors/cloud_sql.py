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

from functools import partial
from typing import Any, Dict, Iterable, Text

from lib.context import MetricsContext
from lib.entities.decorator import entity_extractor
from lib.entities.google_api import generic_paging
from lib.entities.ids import get_func_create_entity_id, LabelToApiRspMapping
from lib.entities.model import CdProperty, Entity
from lib.metrics import GCPService

_SQL_ENDPOINT = "https://sqladmin.googleapis.com"

LabelToApiResponseMapping: LabelToApiRspMapping = {
    "resource.labels.project_id": lambda x: str(x["project"]),
    "resource.labels.region": lambda x: str(x["region"]),
    "resource.labels.database_id": lambda x: str(x["project"]) + ":" + str(x["name"])
}
create_entity_id = get_func_create_entity_id(LabelToApiResponseMapping)


def _get_properties(rsp: Dict[Text, Any]) -> Iterable[CdProperty]:
    """ Retrieve key properties to be passed onto dynatrace server. """
    return [
        CdProperty("Project", rsp.get("project", "N/A")),
        CdProperty("Connection Name", rsp.get("connectionName", "N/A")),
        CdProperty("Region", rsp.get("region", "N/A")),
        CdProperty("Pricing Tier", rsp.get("settings", {}).get("tier", "N/A"))
    ]


def _cloud_sql_resp_to_monitored_entities(page: Dict[Text, Any], svc_def: GCPService):
    """ Create CustomDevice instanace from google api response."""
    return [
        Entity(
            id=create_entity_id(cd, svc_def),
            display_name=cd.get("name", "N/A"),
            group=svc_def.technology_name,
            ip_addresses=[x["ipAddress"] for x in cd.get("ipAddresses", [])],
            listen_ports=[],
            favicon_url="no-gcp-icon-available",
            dtype=svc_def.technology_name,
            properties=_get_properties(cd),
            tags=[],
            dns_names=[]
        ) for cd in page.get("items", [])
    ]


@entity_extractor("cloudsql_database")
async def get_cloud_sql_entity(ctx: MetricsContext, project_id: str, svc_def: GCPService) -> Iterable[Entity]:
    """ Retrieve entity info on GCP Cloud SQL from google api. """

    url = f"{_SQL_ENDPOINT}/sql/v1beta4/projects/{project_id}/instances"
    mapper_func = partial(_cloud_sql_resp_to_monitored_entities, svc_def=svc_def)
    return await generic_paging(project_id, url, ctx, mapper_func)
