#!/usr/bin/env bash

function run_deploy_and_tests() {
    TEST_TYPE=$1

    export START_LOAD_GENERATION=$(date -u +%s%3N)
    export DEPLOYMENT_TYPE=$TEST_TYPE

    ./tests/e2e/deployment-test.sh "--${TEST_TYPE}"

    sleep 300
    export END_LOAD_GENERATION=$(date -u +%s%3N)

    if [[ $TEST_TYPE == 'all' ]]; then
        TEST_TYPE=''
    fi

    pytest "tests/e2e/${TEST_TYPE}" -v

    helm -n dynatrace ls --all --short | grep dynatrace-gcp-function | xargs -L1 helm -n dynatrace delete
}

if [[ $TRAVIS_EVENT_TYPE == 'cron' ]] || [[ $1 == 'separate' ]]; then
    run_deploy_and_tests 'logs'
    run_deploy_and_tests 'metrics'
else
    run_deploy_and_tests 'all'
fi
