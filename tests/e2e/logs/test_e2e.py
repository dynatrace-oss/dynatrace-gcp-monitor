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
import pytest

def test_environment_vars():
    assert "DYNATRACE_URL" in os.environ
    assert "DYNATRACE_ACCESS_KEY" in os.environ
    assert "DEPLOYMENT_TYPE" in os.environ
    assert "TRAVIS_BUILD_ID" in os.environ
    assert "START_LOAD_GENERATION" in os.environ
    assert "END_LOAD_GENERATION" in os.environ

@pytest.fixture
def get_environments_values():
    return { 
        'DYNATRACE_URL': os.environ.get('DYNATRACE_URL'),
        'DYNATRACE_ACCESS_KEY': os.environ.get('DYNATRACE_ACCESS_KEY'),
        'DEPLOYMENT_TYPE': os.environ.get('DEPLOYMENT_TYPE'),
        'BUILD_ID': os.environ.get('TRAVIS_BUILD_ID'),
        'START_TIME': os.environ.get('START_LOAD_GENERATION'),
        'END_TIME': os.environ.get('END_LOAD_GENERATION'),
    }

def test_logs_on_dynatrace(get_environments_values):
    url = f"{get_environments_values['DYNATRACE_URL']}api/v2/logs/search"
    params = {
        'from': get_environments_values['START_TIME'],
        'to': get_environments_values['END_TIME'],
        'query': f"content='TYPE: {get_environments_values['DEPLOYMENT_TYPE']}, BUILD: {get_environments_values['BUILD_ID']}, INFO: This is sample app'"
    }
    headers = {
        'Authorization': f"Api-Token {get_environments_values['DYNATRACE_ACCESS_KEY']}"
    }
    resp = requests.get(url, params=params, headers=headers)

    assert resp.status_code == 200
    assert len(resp.json()['results']) == 5
