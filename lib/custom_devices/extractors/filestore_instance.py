"""This module contains logic responsible for retrieving custom device info of filestore instances. """

import itertools
import re
from functools import partial
from typing import Any, Dict, Iterable, Text

from lib.context import Context
from lib.custom_devices.decorator import custom_device_extractor
from lib.custom_devices.google_api import generic_paging
from lib.custom_devices.ids import get_func_create_custom_device_id, LabelToApiRspMapping
from lib.custom_devices.model import CdProperty, CustomDevice
from lib.metrics import GCPService


export_labels_regex = re.compile(
    r"^projects\/([\w,-]*)\/locations\/([\w,-]*)\/instances\/([\w,-]*)$"
)


def _extract_label(gfun_name: Text, group_index: int) -> Text:
    """Attempt to extract part of gcp filestore instance name.

    0 -> full name
    1 -> project_id
    2 -> region
    3 -> name
    """
    if (group_index < 0) or (group_index > 3):
        raise ValueError("Expected group_index <0,3>")

    match = export_labels_regex.match(gfun_name)
    if not match:
        raise ValueError("Filestore instance name should adhere to expected schema")

    return match.group(group_index)


LabelToApiResponseMapping: LabelToApiRspMapping = {
    "resource.labels.project_id": lambda x: _extract_label(x.get("name", ""), 1),
    "resource.labels.location": lambda x: _extract_label(x.get("name", ""), 2),
    "resource.labels.instance_name": lambda x: _extract_label(x.get("name", ""), 3)
}
create_custom_device_id = get_func_create_custom_device_id(LabelToApiResponseMapping)


def _get_properties(rsp: Dict[Text, Any]) -> Iterable[CdProperty]:
    """ Retrieve key properties to be passed onto dynatrace server. """
    return [
        CdProperty("State", rsp.get("state", "N/A")),
        CdProperty("Tier", rsp.get("tier", "N/A"))
    ]


def _filestore_instance_resp_to_monitored_entities(page: Dict[Text, Any], svc_def: GCPService):
    """ Create CustomDevice instance from google api response."""
    return [
        CustomDevice(
            custom_device_id=create_custom_device_id(cd, svc_def),
            display_name=_extract_label(cd.get("name", ""), 3),
            group=svc_def.technology_name,
            ip_addresses=frozenset(
                itertools.chain.from_iterable([
                    x.get("ipAddresses", []) for x in cd.get("networks", [])
                ])
            ),
            listen_ports=frozenset(),
            favicon_url="no-gcp-icon-available",
            dtype=svc_def.technology_name,
            properties=_get_properties(cd),
            tags=frozenset(),
            dns_names=frozenset()
        ) for cd in page.get("instances", [])
    ]


@custom_device_extractor("filestore_instance")
async def get_filestore_instance_custom_device(ctx: Context, svc_def: GCPService) -> Iterable[CustomDevice]:
    """ Retrieve custom device info on GCP filestore instance from google api. """
    url = "https://file.googleapis.com/v1/projects/{project_id}/locations/-/instances".format(
        project_id=ctx.project_id
    )
    mapper_func = partial(_filestore_instance_resp_to_monitored_entities, svc_def=svc_def)
    return await generic_paging(url, ctx.token, ctx.session, mapper_func)
