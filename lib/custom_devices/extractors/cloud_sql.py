"""This module contains logic responsible for retrieving custom device info of GCP Cloud SQL. """

from functools import partial
from typing import Any, Dict, Iterable, Text

from lib.context import Context
from lib.custom_devices.decorator import custom_device_extractor
from lib.custom_devices.google_api import generic_paging
from lib.custom_devices.ids import get_func_create_custom_device_id, LabelToApiRspMapping
from lib.custom_devices.model import CdProperty, CustomDevice
from lib.metrics import GCPService


LabelToApiResponseMapping: LabelToApiRspMapping = {
    "resource.labels.project_id": lambda x: str(x["project"]),
    "resource.labels.region": lambda x: str(x["region"]),
    "resource.labels.database_id": lambda x: str(x["project"]) + ":" + str(x["name"])
}
create_custom_device_id = get_func_create_custom_device_id(LabelToApiResponseMapping)


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
        CustomDevice(
            custom_device_id=create_custom_device_id(cd, svc_def),
            display_name=cd.get("name", "N/A"),
            group=svc_def.technology_name,
            ip_addresses=frozenset(x["ipAddress"] for x in cd.get("ipAddresses", [])),
            listen_ports=frozenset(),
            favicon_url="no-gcp-icon-available",
            dtype=svc_def.technology_name,
            properties=_get_properties(cd),
            tags=frozenset(),
            dns_names=frozenset()
        ) for cd in page.get("items", [])
    ]


@custom_device_extractor("cloudsql_database")
async def get_cloud_sql_custom_device(ctx: Context, svc_def: GCPService) -> Iterable[CustomDevice]:
    """ Retrieve custom device info on GCP Cloud SQL from google api. """
    url = "https://sqladmin.googleapis.com/sql/v1beta4/projects/{project_id}/instances".format(
        project_id=ctx.project_id
    )
    mapper_func = partial(_cloud_sql_resp_to_monitored_entities, svc_def=svc_def)
    return await generic_paging(url, ctx.token, ctx.session, mapper_func)
