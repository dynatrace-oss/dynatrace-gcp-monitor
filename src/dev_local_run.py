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

env_vars = {
    "ACTIVATION_CONFIG":
        '''
        {"services":[{"service": "api", "featureSets": ["default_metrics"], "vars": {"filter_conditions": ""}} ]}
        ''',
    "DYNATRACE_ACCESS_KEY": "<REPLACE_ME>",
    "DYNATRACE_URL": "<REPLACE_ME>",
    "GCP_PROJECT": "<REPLACE_ME>",
    "HEALTH_CHECK_PORT": "7070",
    "OPERATION_MODE": "Metrics",
    "REQUIRE_VALID_CERTIFICATE": "false",
    "SERVICE_USAGE_BOOKING": "false",
    "SELF_MONITORING_ENABLED": "false",
    "GOOGLE_APPLICATION_CREDENTIALS":  "<REPLACE_ME>",
    "PRINT_METRIC_INGEST_INPUT": "FALSE",
}

for key, value in env_vars.items():
    os.environ[key] = value

import run_docker


# THINGS YOU NEED TO PROVIDE

# 1) GOOGLE_APPLICATION_CREDENTIALS
# Go to Service Account for metrics in GCP console, create key, download and put proper filepath as value above

# 2) DYNATRACE_ACCESS_KEY
# Normal DT token for GCP Monitor metrics

if __name__ == '__main__':
    run_docker.main()
