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

import asyncio
import base64
import json
import os
import time
from urllib.parse import urlparse

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

_DYNATRACE_ACCESS_KEY_SECRET_NAME = config.dynatrace_access_key_secret_name() or "DYNATRACE_ACCESS_KEY"
_DYNATRACE_URL_SECRET_NAME = config.dynatrace_url_secret_name() or "DYNATRACE_URL"
_DYNATRACE_LOG_INGEST_URL_SECRET_NAME = config.dynatrace_log_ingest_url_secret_name()


async def _read_json_file_async(file_path: str) -> dict:
    """Asynchronously read and parse a JSON file."""
    loop = asyncio.get_event_loop()
    
    def read_file():
        with open(file_path) as f:
            return json.load(f)
    
    return await loop.run_in_executor(None, read_file)


async def fetch_dynatrace_api_key(gcp_session: ClientSession, project_id: str, token: str) -> str:
    return (
        config.get_dynatrace_api_key_from_env()
        or await fetch_secret(
            _DYNATRACE_ACCESS_KEY_SECRET_NAME,
            gcp_session,
            project_id,
            token,
        )
    )


async def fetch_dynatrace_url(gcp_session: ClientSession, project_id: str, token: str) -> str:
    return (
        config.get_dynatrace_url_from_env()
        or await fetch_secret(
            _DYNATRACE_URL_SECRET_NAME,
            gcp_session,
            project_id,
            token,
        )
    )

async def fetch_dynatrace_log_ingest_url(gcp_session: ClientSession, project_id: str, token: str) -> str:
    dynatrace_log_ingest_url = config.get_dynatrace_log_ingest_url_from_env()

    if not dynatrace_log_ingest_url and _DYNATRACE_LOG_INGEST_URL_SECRET_NAME:
        dynatrace_log_ingest_url = await fetch_secret(
            _DYNATRACE_LOG_INGEST_URL_SECRET_NAME,
            gcp_session,
            project_id,
            token
        )

    if not dynatrace_log_ingest_url:
        dynatrace_log_ingest_url = await fetch_dynatrace_url(
            gcp_session=gcp_session,
            project_id=project_id,
            token=token,
        )

    return urlparse(dynatrace_log_ingest_url.rstrip("/") + "/api/v2/logs/ingest").geturl()

async def fetch_secret(secret_name: str, session: ClientSession, project_id: str, token: str) -> str:
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
    :return: access_token string, or None if failed
    """
    url = _METADATA_ROOT + "/instance/service-accounts/{0}/token".format("default")
    try:
        response = await session.get(url, headers=_METADATA_HEADERS)
        if response.status >= 300:
            body = await response.text()
            context.log(f"Failed to authorize with Service Account from Metadata Service, "
                        f"response is {response.status} => {body}")
            return None
        response_json = await response.json()
        return response_json["access_token"]
    except Exception as e:
        context.log(f"Failed to authorize with Service Account from Metadata Service due to '{e}'")
        return None


async def create_default_service_account_token_with_expiry(context: LoggingContext, session: ClientSession):
    """
    Enhanced version that returns token with expiration information for proactive refresh
    :param session:
    :return: dictionary with access_token and expires_at timestamp, or None if failed
    """
    url = _METADATA_ROOT + "/instance/service-accounts/{0}/token".format("default")
    try:
        response = await session.get(url, headers=_METADATA_HEADERS)
        if response.status >= 300:
            body = await response.text()
            context.log(f"Failed to authorize with Service Account from Metadata Service, "
                        f"response is {response.status} => {body}")
            return None
        response_json = await response.json()
        
        # Validate response structure
        if "access_token" not in response_json:
            context.log("Invalid response from Metadata Service: missing access_token")
            return None
            
        # Calculate expiration time with robust fallback
        expires_in = response_json.get("expires_in", 3600)
        if not isinstance(expires_in, (int, float)) or expires_in <= 0:
            context.log(f"Invalid expires_in value: {expires_in}, using default 3600 seconds")
            expires_in = 3600
            
        # Use 10 minutes buffer for safety, but ensure we don't set negative expiration
        buffer = min(600, expires_in // 2)  # Max 10 min buffer, but no more than half the token lifetime
        expires_at = time.time() + expires_in - buffer

        context.log(f"Using service account token with expiry info, expires at: {expires_at}")
        return {
            "access_token": response_json["access_token"],
            "expires_at": expires_at
        }
    except Exception as e:
        context.log(f"Failed to authorize with Service Account from Metadata Service due to '{e}'")
        return None


async def create_token(context: LoggingContext, session: ClientSession, validate: bool = False):
    credentials_path = config.credentials_path()

    if credentials_path:
        context.log(f"Using credentials from {credentials_path}")
        credentials_data = await _read_json_file_async(credentials_path)

        gcp_token = await get_token(
            key=credentials_data['private_key'],
            service=credentials_data['client_email'],
            uri=credentials_data['token_uri'],
            session=session
        )
    else:
        context.log("Trying to use default service account")
        gcp_token = await create_default_service_account_token(context, session)

    if validate:
        if gcp_token is None:
            raise Exception("Failed to fetch access token. No value")
        if not isinstance(gcp_token, str):
            raise Exception(f"Failed to fetch access token. Got non string value: {gcp_token}")

    return gcp_token


async def create_token_with_expiry(context: LoggingContext, session: ClientSession, validate: bool = False):
    # Enhanced version that returns token with expiration information for proactive refresh.
    # Only used by components that need proactive token refresh.
    credentials_path = config.credentials_path()

    if credentials_path:
        context.log(f"Using credentials from {credentials_path}")
        credentials_data = await _read_json_file_async(credentials_path)

        # Service account tokens from files typically last 1 hour
        token = await get_token(
            key=credentials_data['private_key'],
            service=credentials_data['client_email'],
            uri=credentials_data['token_uri'],
            session=session
        )
        expires_at = time.time() + 3000  # 50 minutes for safety
        context.log(f"Using service account token with expiry info, expires at: {expires_at}")
        return {
            "access_token": token,
            "expires_at": expires_at
        }

    else:
        context.log("Trying to use default service account")
        token_info = await create_default_service_account_token_with_expiry(context, session)
        
        if validate:
            if token_info is None:
                raise Exception("Failed to fetch access token. No value")
            if not isinstance(token_info, dict) or 'access_token' not in token_info:
                raise Exception(f"Failed to fetch access token. Got invalid token info: {token_info}")
        
        return token_info


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
        context.log(f"There is no access to any projects. Check service account configuration. "
                    f"Response from server: {response_json}.")
    return all_projects
