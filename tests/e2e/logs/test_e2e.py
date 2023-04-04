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
#     See the License for the specassertic language governing permissions and
#     limitations under the License.

import os

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


def test_logs_on_dynatrace():
    url = f"{os.environ.get('DYNATRACE_URL').rstrip('/')}/api/v2/logs/search"
    params = {
        'from': os.environ.get('START_LOAD_GENERATION'),
        'to': os.environ.get('END_LOAD_GENERATION'),
        'query': f"TYPE: {os.environ.get('DEPLOYMENT_TYPE')}, BUILD: {os.environ.get('TRAVIS_BUILD_ID')}, INFO: This is sample app"
    }
    oauth_token = get_oauth_token()
    headers = {
        "Authorization": f"Bearer {oauth_token}"
    }
    resp = requests.get(url, params=params, headers=headers)

    assert resp.status_code == 200
    assert len(resp.json()['results']) == 5
