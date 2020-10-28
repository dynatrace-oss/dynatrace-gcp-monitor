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

from lib.context import LoggingContext, Context

_METADATA_ROOT = "http://metadata.google.internal/computeMetadata/v1"
_METADATA_FLAVOR_HEADER = "metadata-flavor"
_METADATA_FLAVOR_VALUE = "Google"
_METADATA_HEADERS = {_METADATA_FLAVOR_HEADER: _METADATA_FLAVOR_VALUE}

_DYNATRACE_ACCESS_KEY_SECRET_NAME = os.environ.get("DYNATRACE_ACCESS_KEY_SECRET_NAME", "DYNATRACE_ACCESS_KEY")
_DYNATRACE_URL_SECRET_NAME = os.environ.get("DYNATRACE_URL_SECRET_NAME","DYNATRACE_URL")


async def fetch_dynatrace_api_key(session: ClientSession, project_id: str, token: str,):
    return await fetch_secret(session, project_id, token, _DYNATRACE_ACCESS_KEY_SECRET_NAME)


async def fetch_dynatrace_url(session: ClientSession, project_id: str, token: str,):
    return await fetch_secret(session, project_id, token, _DYNATRACE_URL_SECRET_NAME)


async def fetch_secret(session: ClientSession, project_id: str, token: str, secret_name: str):
    env_secret_value = os.environ.get(secret_name, None)
    if env_secret_value:
        return env_secret_value

    url = "https://secretmanager.googleapis.com/v1/projects/{project_id}/secrets/{secret_name}/versions/latest:access"\
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
    return os.environ.get("GCP_PROJECT")


async def create_token(context: LoggingContext, session: ClientSession):
    credentials_path = os.environ[
        'GOOGLE_APPLICATION_CREDENTIALS'] if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ.keys() else ""

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
    assertion_signed = jwt.encode(assertion, key, 'RS256').decode('utf-8')
    request = {'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': assertion_signed}

    async with session.post(uri, data=request) as resp:
        response = await resp.json()
        return response["access_token"]


async def get_all_accessible_projects(context: Context, session: ClientSession):
        url = "https://cloudresourcemanager.googleapis.com/v1/projects"
        headers = {"Authorization": "Bearer {token}".format(token=context.token)}
        response = await session.get(url, headers=headers)
        response_json = await response.json()
        all_projects = [project["projectId"] for project in response_json.get("projects", [])]
        context.log("Access to following projects: " + ", ".join(all_projects))
        return all_projects
