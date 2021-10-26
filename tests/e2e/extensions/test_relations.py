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
import pytest

import requests

testdata = [
    'cloud:gcp:k8s_pod',
    'cloud:gcp:k8s_cluster'
    ] 

@pytest.fixture(scope="class")
def test_environment_vars():
    assert "DYNATRACE_URL" in os.environ
    assert "DYNATRACE_ACCESS_KEY" in os.environ

@pytest.fixture
def api_response():
    url = f"{os.environ['DYNATRACE_URL'].rstrip('/')}/api/v2/settings/objects"
    params = {
        'schemaIds': 'builtin:monitoredentities.generic.relation',
        'scopes': 'environment',
        'fields': 'value'
        }
    headers = {
        'Authorization': f"Api-Token {os.environ['DYNATRACE_ACCESS_KEY']}"
    }
    response = requests.get(url, params=params, headers=headers)
    assert response.status_code == 200
    return response.json()

@pytest.mark.parametrize("generic_relation", testdata)
def test_generic_relation_on_dynatrace(generic_relation, api_response):
    assert 'totalCount' in api_response
    assert api_response['totalCount'] >= 1
    assert 'items' in api_response
    createdByList = [item['value']['toType'] for item in api_response['items'] if 'com.dynatrace.extension.' in item['value']['createdBy']]
    assert generic_relation in createdByList
