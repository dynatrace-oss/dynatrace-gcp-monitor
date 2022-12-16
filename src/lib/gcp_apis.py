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
import os

from aiohttp import ClientResponseError

from lib.context import MetricsContext

GCP_SERVICE_USAGE_URL = os.environ.get("GCP_SERVICE_USAGE_URL", "https://serviceusage.googleapis.com/v1")


async def get_all_enabled_apis(context: MetricsContext, project_id: str):
    fetch_next_page = True
    next_token = None
    services = []
    try:
        while fetch_next_page:
            query_params = {"filter": "state:ENABLED"}
            if next_token:
                query_params["pageToken"] = next_token
            response = await context.gcp_session.get(
                GCP_SERVICE_USAGE_URL + f'/projects/{project_id}/services',
                headers={
                    "Authorization": f'Bearer {context.token}'
                },
                params=query_params)
            if response.status != 200:
                context.logging_context.log(
                    f'Http error: {response.status}, url: {response.url}, reason: {response.reason}')
                return None

            response = await response.json()
            services.extend(map(lambda s: s["config"]["name"], response.get('services', [])))
            next_token = response.get('nextPageToken', None)
            fetch_next_page = next_token is not None
        return services
    except Exception as e:
        context.logging_context.log(f'Unable to get project: {project_id} services list. Error details: {e}')
        return None


async def get_all_disabled_apis(context: MetricsContext, project_id: str):
    base_url = f"{GCP_SERVICE_USAGE_URL}/projects/{project_id}/services?filter=state:DISABLED"
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
