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

import base64
import json
import os
import time

import jwt
from aiohttp import ClientSession

from lib.configuration import config
from lib.context import LoggingContext


_METADATA_ROOT = config.gcp_metadata_url()
_METADATA_FLAVOR_HEADER = "metadata-flavor"
_METADATA_FLAVOR_VALUE = "Google"
_METADATA_HEADERS = {_METADATA_FLAVOR_HEADER: _METADATA_FLAVOR_VALUE}

_SECRET_ROOT = 'https://secretmanager.googleapis.com/v1'
_CLOUD_RESOURCE_MANAGER_ROOT = config.gcp_cloud_resource_manager_url()

_DYNATRACE_ACCESS_KEY_SECRET_NAME = config.dynatrace_access_key_secret_name()
_DYNATRACE_URL_SECRET_NAME = config.dynatrace_url_secret_name()
_DYNATRACE_LOG_INGEST_URL_SECRET_NAME = config.dynatrace_log_ingest_url_secret_name()


async def fetch_dynatrace_api_key(gcp_session: ClientSession, project_id: str, token: str, ):
    return await fetch_secret(gcp_session, project_id, token, _DYNATRACE_ACCESS_KEY_SECRET_NAME)


async def fetch_dynatrace_url(gcp_session: ClientSession, project_id: str, token: str, ):
    return await fetch_secret(gcp_session, project_id, token, _DYNATRACE_URL_SECRET_NAME)


def get_dynatrace_api_key_from_env():
    return os.environ.get(_DYNATRACE_ACCESS_KEY_SECRET_NAME, None)


def get_dynatrace_log_ingest_url_from_env():
    url = os.environ.get(_DYNATRACE_LOG_INGEST_URL_SECRET_NAME, None)
    if url is None:
        raise Exception("{env_var} environment variable is not set".format(env_var=_DYNATRACE_LOG_INGEST_URL_SECRET_NAME))
    return url.rstrip('/')


async def fetch_secret(session: ClientSession, project_id: str, token: str, secret_name: str):
    env_secret_value = os.environ.get(secret_name, None)
    if env_secret_value:
        return env_secret_value

    url = _SECRET_ROOT + "/projects/{project_id}/secrets/{secret_name}/versions/latest:access" \
        .format(project_id=project_id, secret_name=secret_name)

    headers = {"Authorization": "Bearer {token}".format(token=token)}
    response = await session.get(url, headers=headers)
    response_json = await response.json()

    if response.status == 200:
        return base64.b64decode(response_json['payload']['data']).decode('utf-8')
    else:
        raise Exception("Failed to fetch secret {name}, cause: {response_json}"
                        .format(name=secret_name, response_json=response_json))


async def create_default_service_account_token(context: LoggingContext, session: ClientSession):
    """
    For reference check out https://github.com/googleapis/google-auth-library-python/tree/master/google/auth/compute_engine
    :param session:
    :return:
    """
    url = _METADATA_ROOT + "/instance/service-accounts/{0}/token".format("default")
    try:
        response = await session.get(url, headers=_METADATA_HEADERS)
        if response.status >= 300:
            body = await response.text()
            context.log(f"Failed to authorize with Service Account from Metadata Service, response is {response.status} => {body}")
            return None
        response_json = await response.json()
        return response_json["access_token"]
    except Exception as e:
        context.log(f"Failed to authorize with Service Account from Metadata Service due to '{e}'")
        return None


def get_project_id_from_environment():
    return config.project_id()


async def create_token(context: LoggingContext, session: ClientSession):
    credentials_path = config.credentials_path()

    if credentials_path:
        context.log(f"Using credentials from {credentials_path}")
        with open(credentials_path) as key_file:
            credentials_data = json.load(key_file)

        return await get_token(
            key=credentials_data['private_key'],
            service=credentials_data['client_email'],
            uri=credentials_data['token_uri'],
            session=session
        )
    else:
        context.log("Trying to use default service account")
        return await create_default_service_account_token(context, session)


async def get_token(key: str, service: str, uri: str, session: ClientSession):
    now = int(time.time())

    assertion = {
        "iss": service,
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "aud": uri,
        "exp": str(now + 60 * 60),
        "iat": str(now)
    }
    assertion_signed = jwt.encode(assertion, key, 'RS256')
    request = {'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': assertion_signed}
    async with session.post(uri, data=request) as resp:
        response = await resp.json()
        return response["access_token"]


async def get_all_accessible_projects(context: LoggingContext, session: ClientSession, token: str):
    url = _CLOUD_RESOURCE_MANAGER_ROOT + "/projects"
    headers = {"Authorization": "Bearer {token}".format(token=token)}
    all_projects = []
    params = {"filter": "lifecycleState:ACTIVE"}

    while True:
        response = await session.get(url, headers=headers, params=params)
        response_json = await response.json()
        all_projects.extend([project["projectId"] for project in response_json.get("projects", [])])
        page_token = response_json.get("nextPageToken", "")
        params["pageToken"] = page_token
        if page_token == "":
            break

    if all_projects:
        context.log("Access to following projects: " + ", ".join(all_projects))
    else:
        context.log("There is no access to any projects. Check service account configuration.")
    return all_projects
