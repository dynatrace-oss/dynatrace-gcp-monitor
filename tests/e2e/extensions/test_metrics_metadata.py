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
    'cloud.gcp.cloudfunctions_googleapis_com.function',
    'cloud.gcp.logging.googleapis.com',
    'cloud.gcp.kubernetes_io.node',
    'cloud.gcp.kubernetes_io.pod',
    'cloud.gcp.kubernetes_io.container',
    'cloud.gcp.agent_googleapis_com.agent',
    'cloud.gcp.storage_googleapis_com.api',
    'cloud.gcp.storage_googleapis_com.authn',
    'cloud.gcp.storage_googleapis_com.authz',
    'cloud.gcp.storage_googleapis_com.network',
    'cloud.gcp.storage_googleapis_com.storage',
    'cloud.gcp.compute_googleapis_com.instance'
    ]

@pytest.fixture(scope="class")
def test_environment_vars():
    assert "DYNATRACE_URL" in os.environ
    assert "DYNATRACE_ACCESS_KEY" in os.environ

@pytest.mark.parametrize("metric_selector", testdata)
def test_metrics_on_dynatrace(metric_selector):
    url = f"{os.environ['DYNATRACE_URL'].rstrip('/')}/api/v2/metrics"
    params = {
        'metricSelector': f"{metric_selector}.*",
        'fields': 'displayName'
        }
    headers = {
        'Authorization': f"Api-Token {os.environ['DYNATRACE_ACCESS_KEY']}"
    }
    response = requests.get(url, params=params, headers=headers)
    assert response.status_code == 200
    api_response = response.json()
    assert 'totalCount' in api_response
    assert api_response['totalCount'] >= 1
    assert 'metrics' in api_response
