"""This module contains generic way of paging through GCP Apis."""
from typing import Any, Callable, Dict, List, Text

from aiohttp import ClientSession

from lib.context import Context
from lib.custom_devices.model import CustomDevice


async def fetch_zones(
        context: Context,
) -> List[str]:
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer {token}".format(token=context.token)
    }

    resp = await context.session.request(
        "GET",
        params={},
        url=f"https://compute.googleapis.com/compute/v1/projects/{context.project_id}/zones",
        headers=headers,
        raise_for_status=True
    )

    response_json = await resp.json()
    if resp.status != 200:
        raise Exception(f"Failed to fetch available zones, response is {response_json}")

    zone_items = response_json.get("items", [])
    return [zone["name"] for zone in zone_items]


async def generic_paging(
        url: Text,
        auth_token: Text,
        session: ClientSession,
        mapper: Callable[[Dict[Any, Any]], List[CustomDevice]]
) -> List[CustomDevice]:
    """Apply mapper function on any page returned by gcp api url."""
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer {token}".format(token=auth_token)
    }

    get_page = True
    params: Dict[Text, Text] = {}
    custom_devices: List[CustomDevice] = []
    while get_page:
        try:
            resp = await session.request(
                "GET",
                params=params,
                url=url,
                headers=headers,
                raise_for_status=True
            )
            page = await resp.json()
        except Exception as ex:
            print("Failed to retrieve information from googleapis. {0}".format(ex))
            return custom_devices

        try:
            custom_devices.extend(mapper(page))
        except Exception as ex:
            print("Failed to map response from googleapis. {0}".format(ex))
            return custom_devices

        get_page = "nextPageToken" in page
        if get_page:
            params["pageToken"] = page.get("nextPageToken", None)

    return custom_devices
