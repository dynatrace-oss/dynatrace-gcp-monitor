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

import requests


def test_environment_vars():
    assert "GCP_PROJECT_ID" in os.environ
    assert "CLOUD_FUNCTION_NAME" in os.environ
    assert "DYNATRACE_URL" in os.environ
    assert "DYNATRACE_ACCESS_KEY" in os.environ
    assert "START_LOAD_GENERATION" in os.environ
    assert "END_LOAD_GENERATION" in os.environ


def test_metrics_on_dynatrace():
    # Cloud Function might record audit operations, so execution count could be more than 5 (depending on timeframe).
    # Also, it happened that those extra operations differed in labels (different data, different total count).
    print(f"Try to receive execution_count metric from Dynatrace in 5 min (start_time={os.environ['START_LOAD_GENERATION']} ,end_time={os.environ['END_LOAD_GENERATION']})")
    time.sleep(5*60)

    url = f"{os.environ['DYNATRACE_URL'].rstrip('/')}/api/v2/metrics/query"
    params = {'from': os.environ['START_LOAD_GENERATION'],
              'to': os.environ['END_LOAD_GENERATION'],
              'metricSelector': f"cloud.gcp.cloudfunctions_googleapis_com.function.execution_count:filter(eq(gcp.instance.name, {os.environ['CLOUD_FUNCTION_NAME']}),eq(gcp.project.id, {os.environ['GCP_PROJECT_ID']}))",
              'resolution': 'Inf'
              }
    headers = {
        'Authorization': f"Api-Token {os.environ['DYNATRACE_ACCESS_KEY']}"
    }
    response = requests.get(url, params=params, headers=headers)
    assert response.status_code == 200
    response_json = response.json()
    assert 'totalCount' in response_json
    assert response_json['totalCount'] >= 1
    # show full response on test fail
    print(response_json)
    execution_count_values = response_json['result'][0]['data'][0]['values']
    execution_count_value = max(execution_count_values)
    assert execution_count_value >= 5


def test_metrics_from_different_project_on_dynatrace():
    # Cloud Run revision already existing in project dynatrace-gcp-extension-2,
    # with a scheduler job querying it every 5 minutes.
    # request_count metric should return at least 1
    print(f"Try to receive request_count metric of Cloud Run revision from Dynatrace (start_time={os.environ['START_LOAD_GENERATION']} ,end_time={os.environ['END_LOAD_GENERATION']})")

    url = f"{os.environ['DYNATRACE_URL'].rstrip('/')}/api/v2/metrics/query"
    params = {'from': os.environ['START_LOAD_GENERATION'],
              'to': os.environ['END_LOAD_GENERATION'],
              'metricSelector': f"cloud.gcp.run_googleapis_com.request_count:filter(eq(gcp.instance.name, {os.environ['CLOUD_RUN_REVISION_NAME']}),eq(gcp.project.id, {os.environ['GCP_PROJECT_2_ID']}))",
              'resolution': 'Inf'
              }
    headers = {
        'Authorization': f"Api-Token {os.environ['DYNATRACE_ACCESS_KEY']}"
    }
    response = requests.get(url, params=params, headers=headers)
    assert response.status_code == 200
    response_json = response.json()
    assert 'totalCount' in response_json
    assert response_json['totalCount'] >= 1
    # show full response on test fail
    print(response_json)
    request_count_values = response_json['result'][0]['data'][0]['values']
    request_count_value = max(request_count_values)
    assert request_count_value >= 1
