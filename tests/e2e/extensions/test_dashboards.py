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
import jq
import pytest

import requests

testdata = ['Google Cloud Function', 'Google Cloud Storage', 'Google Cloud Datastore', 'Google Cloud Filestore', 'Google Cloud HTTPs Load Balancing', 'Google Cloud TCP Load Balancing', 'Google Cloud SQL', 'Google Cloud Pub/Sub'] 


def test_environment_vars():
    assert "DYNATRACE_URL" in os.environ
    assert "DYNATRACE_ACCESS_KEY" in os.environ

@pytest.mark.parametrize("dashboard", testdata)
def test_metrics_on_dynatrace(dashboard):
    url = f"{os.environ['DYNATRACE_URL'].rstrip('/')}/api/config/v1/dashboards"
    params = {
        'owner': 'Dynatrace'
        }
    headers = {
        'Authorization': f"Api-Token {os.environ['DYNATRACE_ACCESS_KEY']}"
    }
    response = requests.get(url, params=params, headers=headers)
    assert response.status_code == 200
    response_json = response.json()
    print(response_json)
    assert 'dashboards' in response_json
    assert dashboard in jq.compile(".dashboards[].name").input(response_json).all()
