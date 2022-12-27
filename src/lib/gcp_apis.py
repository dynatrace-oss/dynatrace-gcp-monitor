#     Copyright 2021 Dynatrace LLC
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
import os

from aiohttp import ClientResponseError
from typing import Set, List, Dict, Tuple

from lib.context import MetricsContext

_GCP_SERVICE_USAGE_URL = "https://serviceusage.googleapis.com/v1"

REQUIRED_SERVICES = [
    "monitoring.googleapis.com",
    "cloudresourcemanager.googleapis.com"
]


async def _get_all_disabled_apis(context: MetricsContext, project_id: str):
    fetch_next_page = True
    next_token = None
    url = _GCP_SERVICE_USAGE_URL + f'/projects/{project_id}/services'
    headers = context.create_gcp_request_headers(project_id)
    params = {"filter": "state:DISABLED", "pageSize": 200}
    disabled_apis = []
    try:
        while fetch_next_page:
            if next_token:
                params["pageToken"] = next_token
            response = await context.gcp_session.get(
                url=url,
                headers=headers,
                params=params)
            if response.status != 200:
                context.log(f'Http error: {response.status}, url: {response.url}, reason: {response.reason}')
                return disabled_apis
            response = await response.json()
            disabled_apis.extend(map(lambda s: s["config"]["name"], response.get('services', [])))
            next_token = response.get('nextPageToken', None)
            fetch_next_page = next_token is not None
        return disabled_apis
    except ClientResponseError as e:
        context.log(project_id, f'Disabled APIs call returned failed status code. {e}')
        return disabled_apis
    except Exception as e:
        context.log(project_id, f'Cannot get disabled APIs: {_GCP_SERVICE_USAGE_URL}/projects/{project_id}/services?filter=state:DISABLED. {e}')
        return disabled_apis


# This function return all the disabled projects that Service Account has access to and all disabled apis of the enabled projects
async def get_disabled_projects_and_disabled_apis_by_project_id(context, projects_ids) -> Tuple[List[str], Dict[str, Set[str]]]:
    disabled_projects = []
    disabled_apis = {}
    tasks_to_check_if_project_is_disabled = []

    for project_id in projects_ids:
        tasks_to_check_if_project_is_disabled.append(
            _check_if_project_is_disabled_and_get_disabled_api_set(context, project_id))
    results = await asyncio.gather(*tasks_to_check_if_project_is_disabled)
    for project_id, is_project_disabled, disabled_api_set in results:
        if is_project_disabled:
            disabled_projects.append(project_id)
        else:
            disabled_apis[project_id] = disabled_api_set

    return disabled_projects, disabled_apis


async def _check_if_project_is_disabled_and_get_disabled_api_set(context: MetricsContext, project_id: str) -> Tuple[str, bool, Set[str]]:
    try:
        await _check_x_goog_user_project_header_permissions(context, project_id)
    except Exception as e:
        context.log(project_id, f"Unexpected exception when checking 'x-goog-user-project' header: {e}")

    disabled_apis = await _get_all_disabled_apis(context, project_id)
    is_project_disabled = False
    if any(required_service in disabled_apis for required_service in REQUIRED_SERVICES):
        is_project_disabled = True
        context.log(project_id, f"Cannot monitor project. Enable required services to do so: {REQUIRED_SERVICES}")
    return project_id, is_project_disabled, disabled_apis


async def _check_x_goog_user_project_header_permissions(context: MetricsContext, project_id: str):
    if project_id in context.use_x_goog_user_project_header:
        return

    service_usage_booking = os.environ['SERVICE_USAGE_BOOKING'] if 'SERVICE_USAGE_BOOKING' in os.environ.keys() \
        else 'source'
    if service_usage_booking.casefold().strip() != 'destination':
        context.log(project_id, "Using SERVICE_USAGE_BOOKING = source")
        context.use_x_goog_user_project_header[project_id] = False
        return

    url = f"https://monitoring.googleapis.com/v3/projects/{project_id}/metricDescriptors"
    params = [('pageSize', 1)]
    headers = {
        "Authorization": "Bearer {token}".format(token=context.token),
        "x-goog-user-project": project_id
    }
    resp = await context.gcp_session.get(url=url, params=params, headers=headers)
    page = await resp.json()

    if resp.status == 200:
        context.use_x_goog_user_project_header[project_id] = True
        context.log(project_id, "Using SERVICE_USAGE_BOOKING = destination")
    elif resp.status == 403 and 'serviceusage.services.use' in page['error']['message']:
        context.use_x_goog_user_project_header[project_id] = False
        context.log(project_id, "Ignoring destination SERVICE_USAGE_BOOKING. Missing permission: 'serviceusage.services.use'")
    else:
        context.log(project_id, f"Unexpected response when checking 'x-goog-user-project' header: {str(page)}")