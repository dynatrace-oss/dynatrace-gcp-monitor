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
import requests

DYNATRACE_URL = os.environ['DYNATRACE_URL']
DYNATRACE_ACCESS_KEY = os.environ['DYNATRACE_ACCESS_KEY']
START_TIME = os.environ['START_LOAD_GENERATION']
END_TIME = os.environ['END_LOAD_GENERATION']


def test_logs_on_dynatrace():
    url = f"{DYNATRACE_URL}api/v2/logs/search"
    params = {
        'from': START_TIME,
        'to': END_TIME,
        'query': 'content="This is sample app"'
    }
    headers = {
        'Authorization': f"Api-Token {DYNATRACE_ACCESS_KEY}"
    }
    resp = requests.get(url, params=params, headers=headers)

    assert resp.status_code == 200
    assert len(resp.json()['results']) == 5
    assert resp.json()['results'][0]['content'] == "This is sample app"
