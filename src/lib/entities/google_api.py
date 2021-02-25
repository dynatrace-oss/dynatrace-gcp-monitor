"""This module contains generic way of paging through GCP Apis."""
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

from typing import Any, Callable, Dict, List, Text

from lib.context import Context
from lib.entities.model import Entity


async def fetch_zones(
        context: Context,
        project_id: str
) -> List[str]:
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer {token}".format(token=context.token)
    }

    resp = await context.gcp_session.request(
        "GET",
        params={},
        url=f"https://compute.googleapis.com/compute/v1/projects/{project_id}/zones",
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
        ctx: Context,
        mapper: Callable[[Dict[Any, Any]], List[Entity]]
) -> List[Entity]:
    """Apply mapper function on any page returned by gcp api url."""
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer {token}".format(token=ctx.token)
    }

    get_page = True
    params: Dict[Text, Text] = {}
    entities: List[Entity] = []
    while get_page:
        resp = await ctx.gcp_session.request(
            "GET",
            params=params,
            url=url,
            headers=headers
        )

        try:
            page = await resp.json()
        except Exception:
            error_message = await resp.text()
            error_message = ' '.join(error_message.split())
            ctx.log(f'Failed to decode JSON. {url} {error_message}')
            return entities

        if resp.status >= 400:
            ctx.log(f'Failed to retrieve information from googleapis. {url} {page}')
            return entities

        try:
            entities.extend(mapper(page))
        except Exception as ex:
            ctx.log(f"Failed to map response from googleapis. {url} {ex}")
            return entities

        get_page = "nextPageToken" in page
        if get_page:
            params["pageToken"] = page.get("nextPageToken", None)

    return entities
