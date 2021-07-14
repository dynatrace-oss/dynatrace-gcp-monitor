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

import time
import os
import pytest
import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

ACCESS_KEY_FILE = 'tests/e2e/e2e-gcp-sa-key.json'
DYNATRACE_URL = os.environ['DYNATRACE_URL']
DYNATRACE_ACCESS_KEY = os.environ['DYNATRACE_ACCESS_KEY']
GCP_PROJECT_ID = os.environ['GCP_PROJECT_ID']


@pytest.fixture(scope="session", autouse=True)
def generate_logs():
    start_time = time.time()
    client_id = ''
    url = f"https://us-central1-{GCP_PROJECT_ID}.cloudfunctions.net/sample_app"
    open_id_connect_token = id_token.fetch_id_token(Request(), client_id)
    for _ in range(5):
        requests.get(url, headers={'Authorization': 'Bearer {}'.format(open_id_connect_token)})
    end_time = time.time() + 300

    return {'start_time': start_time, 'end_time': end_time}


def test_logs_on_dynatrace(generate_logs):
    url = f"{DYNATRACE_URL}/api/v2/logs/search"
    params = {'from': generate_logs['start_time'],
              'to': generate_logs['end_time'],
              'query': 'content="This is sample app"'}
    headers = {
        'Authorization': f"Api-Token {DYNATRACE_ACCESS_KEY}"
    }
    request = requests.get(url, params=params, headers=headers)

    assert request == 5
