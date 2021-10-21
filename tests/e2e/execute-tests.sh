#!/usr/bin/env bash
#     Copyright 2021 Dynatrace LLC
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

function run_deploy_and_tests() {
    TEST_TYPE=$1

    export START_LOAD_GENERATION=$(date -u +%s%3N)
    export DEPLOYMENT_TYPE=$TEST_TYPE

    ./tests/e2e/deployment-test.sh "--${TEST_TYPE}"

    echo waiting 300sec
    sleep 300
    export END_LOAD_GENERATION=$(date -u +%s%3N)

    if [[ $TEST_TYPE == 'all' ]]; then
        TEST_TYPE=''
    fi

    set -e
    pytest "tests/e2e/${TEST_TYPE}" -v

    helm -n dynatrace ls --all --short | grep dynatrace-gcp-function | xargs -L1 helm -n dynatrace delete
}

if [[ $TRAVIS_EVENT_TYPE == 'cron' ]] || [[ $1 == 'separate' ]]; then
    run_deploy_and_tests 'logs'
    run_deploy_and_tests 'metrics'
    run_deploy_and_tests 'all'
else
    run_deploy_and_tests 'all'
fi
