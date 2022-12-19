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

from lib.context import MetricsContext

GCP_SERVICE_USAGE_URL = "https://serviceusage.googleapis.com/v1/projects/"


async def _get_all_disabled_apis(context: MetricsContext, project_id: str):
    base_url = f"{GCP_SERVICE_USAGE_URL}{project_id}/services?filter=state:DISABLED"
    headers = context.create_gcp_request_headers(project_id)
    disabled_apis = set()
    try:
        response = await context.gcp_session.get(base_url, headers=headers, raise_for_status=True)
        disabled_services_json = await response.json()
        disabled_services = disabled_services_json.get("services", [])
        disabled_apis.update({disable_service.get("config", {}).get("name", "") for disable_service in disabled_services})
        while disabled_services_json.get("nextPageToken"):
            url = f"{base_url}&pageToken={disabled_services_json['nextPageToken']}"
            response = await context.gcp_session.get(url, headers=headers, raise_for_status=True)
            disabled_services_json = await response.json()
            disabled_services = disabled_services_json.get("services", [])
            disabled_apis.update({disable_service.get("config", {}).get("name", "") for disable_service in disabled_services})
        return disabled_apis
    except ClientResponseError as e:
        context.log(project_id, f'Disabled APIs call returned failed status code. {e}')
        return disabled_apis
    except Exception as e:
        context.log(project_id, f'Cannot get disabled APIs: {GCP_SERVICE_USAGE_URL}/projects/{project_id}/services?filter=state:DISABLED. {e}')
        return disabled_apis


# This function return all the disabled projects that Service Account has access to and all disabled apis of the enabled projects
async def get_disabled_projects_and_disabled_apis_by_project_id(context, projects_ids) -> [list, dict]:
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


async def _check_if_project_is_disabled_and_get_disabled_api_set(context: MetricsContext, project_id: str) -> [str, bool, set]:
    try:
        await _check_x_goog_user_project_header_permissions(context, project_id)
    except Exception as e:
        context.log(project_id, f"Unexpected exception when checking 'x-goog-user-project' header: {e}")

    disabled_api_set = await _get_all_disabled_apis(context, project_id)
    is_project_disabled = False
    if 'monitoring.googleapis.com' in disabled_api_set:
        is_project_disabled = True
    return project_id, is_project_disabled, disabled_api_set


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