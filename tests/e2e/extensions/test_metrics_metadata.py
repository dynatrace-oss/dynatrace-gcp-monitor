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
import json
from pathlib import Path
import requests
import time

TEST_DATA_DIR = Path(__file__).resolve().parent / 'data'

with open(TEST_DATA_DIR / 'metadata.json', 'r') as res_file:
    testdata = json.loads(res_file.read())


@pytest.fixture(scope="class")
def test_environment_vars():
    assert "DYNATRACE_URL" in os.environ
    assert "DYNATRACE_ACCESS_KEY" in os.environ


@pytest.mark.parametrize("metric_selector", testdata, ids=[i['key'] for i in testdata])
def test_metrics_on_dynatrace(metric_selector):
    time.sleep(100)
    url = f"{os.environ['DYNATRACE_URL'].rstrip('/')}/api/v2/settings/objects"
    params = {
        'schemaIds': 'builtin:metric.metadata',
        'scopes': f"metric-{metric_selector['key']}",
        'fields': 'objectId,value'
    }
    headers = {
        'Authorization': f"Api-Token {os.environ['DYNATRACE_ACCESS_KEY']}"
    }
    response = requests.get(url, params=params, headers=headers)
    assert response.status_code == 200
    api_response = response.json()
    print(api_response)
    assert 'totalCount' in api_response
    assert api_response['totalCount'] >= 1
    assert api_response['items'][0]['value']['displayName'] == metric_selector['metadata']['displayName']
    assert api_response['items'][0]['value']['unit'] == metric_selector['metadata']['unit']
