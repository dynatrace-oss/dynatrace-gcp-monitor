#!/bin/bash
set -eu

docker build -f dockerfile -t dynatrace-gcp-function .        

if [[ "${PUSH:-}" == "true" ]]; then
    docker tag dynatrace-gcp-function dynatrace/dynatrace-gcp-function:$TAG
    docker push dynatrace/dynatrace-gcp-function:$TAG
fi