#!/bin/bash
set -eu

docker build -f dockerfile -t dynatrace-gcp-function .        
docker tag dynatrace-gcp-function dynatrace/dynatrace-gcp-function:$TAG

if [[ "${PUSH:-}" == "true" ]]; then
    docker push dynatrace/dynatrace-gcp-function:$TAG
fi