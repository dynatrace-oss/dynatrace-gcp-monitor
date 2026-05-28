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

import os
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests


def test_environment_vars():
    assert "DYNATRACE_URL" in os.environ
    assert "DYNATRACE_ACCESS_KEY" in os.environ
    assert "DEPLOYMENT_TYPE" in os.environ
    assert "TRAVIS_BUILD_ID" in os.environ
    assert "START_LOAD_GENERATION" in os.environ
    assert "END_LOAD_GENERATION" in os.environ
    assert "OAUTH_URL_E2E" in os.environ
    assert "OAUTH_CLIENT_SECRET_E2E" in os.environ
    assert "OAUTH_CLIENT_ID_E2E" in os.environ
    assert "OAUTH_CLIENT_SCOPE_E2E" in os.environ
    assert "OAUTH_GRANT_TYPE_E2E" in os.environ


def get_oauth_token():
    oauth_url = str(os.environ.get('OAUTH_URL_E2E'))
    data = {
        "grant_type": str(os.environ.get("OAUTH_GRANT_TYPE_E2E")),
        "client_id": str(os.environ.get("OAUTH_CLIENT_ID_E2E")),
        "client_secret": str(os.environ.get("OAUTH_CLIENT_SECRET_E2E")),
        "scope": str(os.environ.get("OAUTH_CLIENT_SCOPE_E2E"))
    }
    headers = {
        "Content-type": "application/x-www-form-urlencoded"
    }

    resp = requests.post(oauth_url, data=data, headers=headers)

    return resp.json()['access_token']


def get_platform_url():
    """Derive the Dynatrace Platform (apps) URL from the environment URL.

    The Grail Query API lives on the Platform/apps domain, not the classic
    environment domain.  For example:
      - Environment URL: https://abc12345.dev.dynatracelabs.com
      - Platform  URL:  https://abc12345.dev.apps.dynatracelabs.com

    The env var DYNATRACE_PLATFORM_URL can override the derivation.

    The OAuth client used for authentication must have the following scopes
    granted via IAM policies:
      - storage:logs:read
      - storage:buckets:read
    """
    override = os.environ.get('DYNATRACE_PLATFORM_URL')
    if override:
        return override.rstrip('/')

    env_url = os.environ.get('DYNATRACE_URL').rstrip('/')
    parsed = urlparse(env_url)
    parts = parsed.hostname.split('.')
    # Insert 'apps' before the base domain (e.g. before 'dynatracelabs.com')
    parts.insert(-2, 'apps')
    platform_host = '.'.join(parts)
    return f"{parsed.scheme}://{platform_host}"


def test_logs_on_dynatrace():
    # The classic /api/v2/logs/search endpoint is deprecated and returns HTTP 500
    # on Grail-enabled tenants. Use the Grail Query API with DQL instead.
    # The Platform API lives on the apps domain, not the environment domain.
    # More info: https://developer.dynatrace.com/develop/platform-services/services/grail-service/
    platform_url = get_platform_url()
    url = f"{platform_url}/platform/storage/query/v1/query:execute"

    start_ms = os.environ.get('START_LOAD_GENERATION')
    end_ms = os.environ.get('END_LOAD_GENERATION')
    deployment_type = os.environ.get('DEPLOYMENT_TYPE')
    build_id = os.environ.get('TRAVIS_BUILD_ID')

    dql_query = (
        'fetch logs'
        f' | filter contains(content, "TYPE: {deployment_type}")'
        f' | filter contains(content, "BUILD: {build_id}")'
        f' | filter contains(content, "This is sample app")'
    )

    # Convert epoch milliseconds to ISO 8601 for Grail timeframe
    start_iso = datetime.fromtimestamp(int(start_ms) / 1000, tz=timezone.utc).isoformat()
    end_iso = datetime.fromtimestamp(int(end_ms) / 1000, tz=timezone.utc).isoformat()

    body = {
        "query": dql_query,
        "defaultTimeframeStart": start_iso,
        "defaultTimeframeEnd": end_iso,
        "requestTimeoutMilliseconds": 60000,
        "maxResultRecords": 100
    }

    oauth_token = get_oauth_token()
    headers = {
        "Authorization": f"Bearer {oauth_token}",
        "Content-Type": "application/json"
    }

    resp = requests.post(url, json=body, headers=headers)
    assert resp.status_code == 200, (
        f"Grail query failed with {resp.status_code}: {resp.text}. "
        f"URL: {url}. "
        f"Ensure the OAuth client has scopes: storage:logs:read, storage:buckets:read"
    )

    result = resp.json()

    # Poll if query is still running (async execution)
    if result.get('state') == 'RUNNING':
        poll_url = f"{platform_url}/platform/storage/query/v1/query:poll"
        request_token = result['requestToken']
        for _ in range(30):
            time.sleep(2)
            poll_resp = requests.post(
                poll_url,
                json={'requestToken': request_token, 'requestTimeoutMilliseconds': 5000},
                headers=headers
            )
            assert poll_resp.status_code == 200, f"Poll failed: {poll_resp.status_code}: {poll_resp.text}"
            result = poll_resp.json()
            if result.get('state') != 'RUNNING':
                break

    assert result['state'] == 'SUCCEEDED', f"Query state: {result.get('state')}, result: {result}"
    records = result.get('result', {}).get('records', [])
    assert len(records) == 5, f"Expected 5 log records, got {len(records)}"
